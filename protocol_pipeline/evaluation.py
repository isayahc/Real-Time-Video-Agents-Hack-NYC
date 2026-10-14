"""Deterministic, provenance-preserving production resource accounting.

Inputs describe one consistent batch boundary. This module does not infer missing
measurements, allocate capital automatically, or decide investment viability.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .models import EngineeringValue, StrictModel

UNITS: dict[str, str] = {
    "accepted_count": "count", "attempted_count": "count",
    "elapsed_s": "s", "labor_s": "operator-s", "electricity_wh": "Wh",
    "consumed_stock_g": "g", "recoverable_scrap_g": "g",
    "unrecovered_waste_g": "g", "loaded_labor_rate": "USD/operator-hour",
    "electricity_rate": "USD/kWh", "stock_cost": "USD/batch",
    "consumables_cost": "USD/batch", "allocated_tooling_cost": "USD/batch",
    "maintenance_cost": "USD/batch", "facility_cost": "USD/batch",
    "other_utilities_cost": "USD/batch", "paid_coverage_cost": "USD/batch",
    "recovery_credit": "USD/batch",
}
DIRECT_COSTS = (
    "stock_cost", "consumables_cost", "allocated_tooling_cost",
    "maintenance_cost", "facility_cost", "other_utilities_cost",
    "paid_coverage_cost", "recovery_credit",
)


class AttendanceInterval(StrictModel):
    """Sourced attended labor interval, in seconds from the batch origin."""

    operator_id: str = Field(min_length=1)
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    basis: Literal["measured", "assumed"]
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self) -> AttendanceInterval:
        """Reject negative-duration attendance."""
        if self.end_s < self.start_s:
            raise ValueError("Attendance ends before it starts")
        return self


class ProcessEvaluationInput(StrictModel):
    """One batch with explicit units, boundary and acceptance provenance.

    Missing inputs remain unknown. Attendance intervals or an aggregate labor
    value may be supplied, never both. Rates must match the report's USD currency.
    """

    schema_version: Literal[1] = 1
    configuration_id: str = Field(min_length=1)
    functional_unit: str = Field(min_length=1)
    boundary: str = Field(min_length=1)
    acceptance_verified: bool = False
    acceptance_source: str | None = None
    inputs: dict[str, EngineeringValue] = Field(default_factory=dict)
    attendance: list[AttendanceInterval] | None = None
    attendance_source: str | None = None

    @model_validator(mode="after")
    def accounting_contract(self) -> ProcessEvaluationInput:
        """Require consistent units, counts, timing and exclusive labor inputs."""
        for key, item in self.inputs.items():
            if key not in UNITS:
                raise ValueError(f"Unsupported accounting input: {key}")
            if item.unit != UNITS[key]:
                raise ValueError(f"{key} must use {UNITS[key]}")
            if item.value is not None and item.value < 0:
                raise ValueError(f"{key} cannot be negative")
            if key.endswith("_count") and item.value is not None and not item.value.is_integer():
                raise ValueError("Counts must be integers")
        accepted = self.inputs.get("accepted_count")
        attempted = self.inputs.get("attempted_count")
        if accepted and attempted and accepted.value is not None and attempted.value is not None:
            if accepted.value > attempted.value:
                raise ValueError("Accepted count exceeds attempted count")
        if self.acceptance_verified and not self.acceptance_source:
            raise ValueError("Verified acceptance requires a source")
        if self.attendance is not None:
            if "labor_s" in self.inputs:
                raise ValueError("Supply attendance or aggregate labor_s, never both")
            if not self.attendance_source:
                raise ValueError("Attendance requires a source confirming complete coverage")
            elapsed = self.inputs.get("elapsed_s")
            if elapsed and elapsed.value is not None:
                if any(event.end_s > elapsed.value for event in self.attendance):
                    raise ValueError("Attendance exceeds the batch elapsed boundary")
        return self


class Metric(StrictModel):
    """A calculated value, or an explicit explanation of why it is unknown."""

    value: float | None
    unit: str
    status: Literal["calculated", "unknown", "undefined"]
    basis: Literal["derived_from_sourced_inputs", "includes_assumptions", "unknown"]
    dependencies: list[str]
    missing_inputs: list[str] = Field(default_factory=list)
    reason: str | None = None


class ProcessEvaluationReport(StrictModel):
    """Versioned batch accounting with a detached serialized input snapshot."""

    schema_version: Literal[1] = 1
    evaluator_version: Literal["1.0"] = "1.0"
    configuration_id: str
    status: Literal["complete_for_declared_boundary", "partial"]
    acceptance_verified: bool
    metrics: dict[str, Metric]
    costs_usd_per_batch: dict[str, Metric]
    known_cost_subtotal_usd_per_batch: float
    unknown_cost_components: list[str]
    warnings: list[str]
    input_snapshot: ProcessEvaluationInput


def attendance_seconds(intervals: list[AttendanceInterval]) -> float:
    """Union overlaps per operator; sum labor across distinct operators."""
    by_operator: dict[str, list[tuple[float, float]]] = {}
    for interval in intervals:
        by_operator.setdefault(interval.operator_id, []).append((interval.start_s, interval.end_s))
    total = 0.0
    for events in by_operator.values():
        start, end = sorted(events)[0]
        for next_start, next_end in sorted(events)[1:]:
            if next_start <= end:
                end = max(end, next_end)
            else:
                total += end - start
                start, end = next_start, next_end
        total += end - start
    return total


def evaluate_process(data: ProcessEvaluationInput) -> ProcessEvaluationReport:
    """Calculate resources and recurring cost per accepted output without imputation."""
    data = ProcessEvaluationInput.model_validate(data.model_dump())
    inputs = dict(data.inputs)
    if data.attendance is not None:
        inputs["labor_s"] = EngineeringValue(
            value=attendance_seconds(data.attendance), unit="operator-s",
            basis="assumed" if any(x.basis == "assumed" for x in data.attendance) else "measured",
            source=data.attendance_source,
        )

    def calculate(keys: list[str], unit: str, function: Callable[[list[float]], float],
                  positive: tuple[str, ...] = ()) -> Metric:
        """Resolve dependencies before arithmetic and preserve denominator failures."""
        missing = [key for key in keys if key not in inputs or inputs[key].value is None]
        basis = "includes_assumptions" if any(
            key in inputs and inputs[key].basis == "assumed" for key in keys
        ) else "derived_from_sourced_inputs"
        if missing:
            return Metric(value=None, unit=unit, status="unknown", basis="unknown",
                          dependencies=keys, missing_inputs=missing, reason="Required inputs are unknown")
        for key in positive:
            if inputs[key].value == 0:
                return Metric(value=None, unit=unit, status="undefined", basis=basis,
                              dependencies=keys, reason=f"{key} must be positive")
        values = [float(inputs[key].value) for key in keys]  # Dependencies checked above.
        value = function(values)
        if not math.isfinite(value):
            raise ValueError("Accounting calculation produced a nonfinite value")
        return Metric(value=value, unit=unit, status="calculated", basis=basis, dependencies=keys)

    metrics: dict[str, Metric] = {}
    for key, name, unit in (
        ("labor_s", "labor_s_per_accepted", "operator-s/accepted output"),
        ("electricity_wh", "electricity_wh_per_accepted", "Wh/accepted output"),
        ("consumed_stock_g", "stock_g_per_accepted", "g/accepted output"),
        ("recoverable_scrap_g", "recoverable_scrap_g_per_accepted", "g/accepted output"),
        ("unrecovered_waste_g", "unrecovered_waste_g_per_accepted", "g/accepted output"),
    ):
        metrics[name] = calculate([key, "accepted_count"], unit, lambda v: v[0] / v[1], ("accepted_count",))
    metrics["accepted_outputs_per_hour"] = calculate(
        ["accepted_count", "elapsed_s"], "accepted outputs/hour", lambda v: 3600 * v[0] / v[1], ("elapsed_s",))
    metrics["accepted_fraction"] = calculate(
        ["accepted_count", "attempted_count"], "fraction", lambda v: v[0] / v[1], ("attempted_count",))
    costs = {key: calculate([key], "USD/batch", lambda v: v[0]) for key in DIRECT_COSTS}
    costs["labor_cost"] = calculate(["labor_s", "loaded_labor_rate"], "USD/batch", lambda v: v[0] * v[1] / 3600)
    costs["electricity_cost"] = calculate(["electricity_wh", "electricity_rate"], "USD/batch", lambda v: v[0] * v[1] / 1000)
    unknown = [key for key, metric in costs.items() if metric.value is None]
    subtotal = sum(metric.value * (-1 if key == "recovery_credit" else 1)
                   for key, metric in costs.items() if metric.value is not None)
    cost_keys = list(DIRECT_COSTS) + ["labor_s", "loaded_labor_rate", "electricity_wh", "electricity_rate"]
    signs = [-1 if key == "recovery_credit" else 1 for key in DIRECT_COSTS]

    def total_cost(values: list[float]) -> float:
        """Combine direct batch costs and labor/energy charges with one recovery credit."""
        direct = sum(value * sign for value, sign in zip(values[:len(DIRECT_COSTS)], signs))
        labor, labor_rate, wh, energy_rate = values[len(DIRECT_COSTS):len(DIRECT_COSTS) + 4]
        return direct + labor * labor_rate / 3600 + wh * energy_rate / 1000

    metrics["total_cost_usd_per_batch"] = calculate(cost_keys, "USD/batch", total_cost)
    metrics["cost_usd_per_accepted"] = calculate(
        cost_keys + ["accepted_count"], "USD/accepted output", lambda v: total_cost(v) / v[-1], ("accepted_count",))
    warnings = ["Completeness applies only to the declared boundary; capital investment and payback are not evaluated."]
    if not data.acceptance_verified:
        warnings.append("Output acceptance/equivalence is unverified; results are conditional and not ready for a validated comparison.")
    if unknown:
        warnings.append("Known cost subtotal is partial and is not the total cost or necessarily a lower bound.")
    if any(item.basis == "assumed" for item in inputs.values()):
        warnings.append("Results include planning assumptions, not exclusively measured performance.")
    complete = data.acceptance_verified and all(m.status == "calculated" for m in metrics.values())
    return ProcessEvaluationReport(
        configuration_id=data.configuration_id,
        status="complete_for_declared_boundary" if complete else "partial",
        acceptance_verified=data.acceptance_verified, metrics=metrics, costs_usd_per_batch=costs,
        known_cost_subtotal_usd_per_batch=subtotal, unknown_cost_components=unknown,
        warnings=warnings, input_snapshot=data,
    )


def evaluate_file(input_path: Path, output_path: Path) -> None:
    """Validate an input JSON and exclusively create its deterministic report."""
    data = ProcessEvaluationInput.model_validate_json(input_path.read_text())
    report = evaluate_process(data)
    with output_path.open("x", encoding="utf-8") as destination:
        destination.write(report.model_dump_json(indent=2) + "\n")
