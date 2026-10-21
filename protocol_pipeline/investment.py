# SPDX-License-Identifier: MPL-2.0
"""Deterministic, undiscounted comparison of two process infrastructure options.

Costs are modeled as variable USD/accepted output plus explicit annual fixed
costs and deployment capital. Replacement, financing, tax and residual value
are outside this first comparison model.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .evaluation import Metric, ProcessEvaluationInput, evaluate_process
from .models import EngineeringValue, StrictModel

UPFRONT_KEYS = ("equipment", "installation", "integration", "training")
FIXED_BATCH_KEYS = ("allocated_tooling_cost", "facility_cost", "paid_coverage_cost", "maintenance_cost")
OPTION_UNITS = {
    "annual_fixed_cost": "USD/year", "scheduled_hours": "h/year",
    "utilization": "fraction", "downtime": "fraction", "useful_life": "years",
}


def check_quantity(item: EngineeringValue, unit: str, positive: bool = False,
                   fraction: bool = False) -> None:
    """Enforce units and physical ranges without treating unknowns as zero."""
    if item.unit != unit:
        raise ValueError(f"Expected unit {unit}")
    if item.value is not None:
        if item.value < 0 or (positive and item.value == 0):
            raise ValueError("Quantity is outside its allowed range")
        if fraction and item.value > 1:
            raise ValueError("Fractions must lie in [0, 1]")


class InvestmentOption(StrictModel):
    """A process option with disjoint variable, fixed and upfront cost boundaries."""

    process: ProcessEvaluationInput
    cost_model_source: str = Field(min_length=1)
    capacity_model_source: str = Field(min_length=1)
    upfront: dict[str, EngineeringValue] = Field(default_factory=dict)
    annual_fixed_cost: EngineeringValue
    scheduled_hours: EngineeringValue
    utilization: EngineeringValue
    downtime: EngineeringValue
    useful_life: EngineeringValue

    @model_validator(mode="after")
    def disjoint_accounting(self) -> InvestmentOption:
        """Validate capital/ranges and reject duplicate fixed/capital allocations."""
        for key, item in self.upfront.items():
            if key not in UPFRONT_KEYS:
                raise ValueError(f"Unsupported upfront category {key}")
            check_quantity(item, "USD")
        for key, unit in OPTION_UNITS.items():
            check_quantity(getattr(self, key), unit, positive=key == "useful_life",
                           fraction=key in ("utilization", "downtime"))
        for key in FIXED_BATCH_KEYS:
            item = self.process.inputs.get(key)
            if item and item.value is not None and item.value != 0:
                raise ValueError(f"{key} must be explicitly zero in variable-cost batch; allocate it to annual_fixed_cost or upfront")
        return self


class SensitivityScenario(StrictModel):
    """Named, sourced overrides to the same underlying investment comparison."""

    name: str = Field(min_length=1)
    overrides: dict[str, EngineeringValue] = Field(min_length=1)


class InvestmentComparisonInput(StrictModel):
    """Comparable outputs, annual demand and a no-replacement analysis horizon."""

    schema_version: Literal[1] = 1
    baseline: InvestmentOption
    candidate: InvestmentOption
    equivalence_verified: bool = False
    equivalence_source: str | None = None
    annual_demand: EngineeringValue
    horizon_years: EngineeringValue
    scenarios: list[SensitivityScenario] = Field(default_factory=list)

    @model_validator(mode="after")
    def comparable_boundary(self) -> InvestmentComparisonInput:
        """Require matching declared outputs/boundaries and sourced equivalence."""
        if self.baseline.process.configuration_id == self.candidate.process.configuration_id:
            raise ValueError("Baseline and candidate must have distinct configuration IDs")
        if self.baseline.process.functional_unit != self.candidate.process.functional_unit:
            raise ValueError("Functional units must match")
        if self.baseline.process.boundary != self.candidate.process.boundary:
            raise ValueError("Process boundaries must match")
        if self.equivalence_verified and not self.equivalence_source:
            raise ValueError("Verified equivalence requires a source")
        check_quantity(self.annual_demand, "accepted outputs/year")
        check_quantity(self.horizon_years, "years", positive=True)
        names = [scenario.name for scenario in self.scenarios]
        if len(set(names)) != len(names):
            raise ValueError("Sensitivity scenario names must be unique")
        for scenario in self.scenarios:
            apply_scenario(self, scenario)
        return self


class ComparisonResult(StrictModel):
    """Conditional economics with explicit evidence and capacity gates."""

    status: Literal["calculated", "insufficient_evidence", "infeasible_capacity", "unsupported_horizon"]
    decision: Literal["candidate_lower_cost", "baseline_lower_cost", "equal_cost", "undetermined"]
    metrics: dict[str, Metric]
    horizon_break_even_direction: Literal["above", "below", "all_volumes", "no_volumes", "unknown"]
    issues: list[str]
    assumptions_present: bool


class InvestmentComparisonReport(StrictModel):
    """Versioned base and sensitivity results retaining the complete input snapshot."""

    schema_version: Literal[1] = 1
    comparator_version: Literal["1.0"] = "1.0"
    base: ComparisonResult
    scenarios: dict[str, ComparisonResult]
    input_snapshot: InvestmentComparisonInput
    limitations: list[str]


def apply_scenario(data: InvestmentComparisonInput, scenario: SensitivityScenario) -> InvestmentComparisonInput:
    """Apply only supported sourced demand, capacity, fixed-cost and price overrides."""
    payload = data.model_dump()
    payload["scenarios"] = []
    for path, value in scenario.overrides.items():
        parts = path.split(".")
        if len(parts) == 1 and path in ("annual_demand", "horizon_years"):
            payload[path] = value.model_dump()
        elif len(parts) == 2 and parts[0] in ("baseline", "candidate") and parts[1] in OPTION_UNITS:
            payload[parts[0]][parts[1]] = value.model_dump()
        elif (len(parts) == 4 and parts[0] in ("baseline", "candidate")
              and parts[1:3] == ["process", "inputs"]
              and parts[3] in ("loaded_labor_rate", "electricity_rate", "stock_cost")):
            payload[parts[0]]["process"]["inputs"][parts[3]] = value.model_dump()
        else:
            raise ValueError(f"Unsupported sensitivity path: {path}")
    return InvestmentComparisonInput.model_validate(payload)


def compare_case(data: InvestmentComparisonInput) -> ComparisonResult:
    """Calculate linear cost/capacity tradeoffs for constant annual accepted demand."""
    quantities: dict[str, EngineeringValue] = {"annual_demand": data.annual_demand, "horizon_years": data.horizon_years}
    issues: list[str] = []
    metrics: dict[str, Metric] = {}
    for name, option in (("baseline", data.baseline), ("candidate", data.candidate)):
        report = evaluate_process(option.process)
        for key in OPTION_UNITS:
            quantities[f"{name}.{key}"] = getattr(option, key)
        for key in UPFRONT_KEYS:
            quantities[f"{name}.upfront.{key}"] = option.upfront.get(key, EngineeringValue(unit="USD", basis="unknown"))
        for source_metric, target_key, unit in (
            ("cost_usd_per_accepted", "variable_unit_cost", "USD/accepted output"),
            ("accepted_outputs_per_hour", "nominal_rate", "accepted outputs/hour"),
        ):
            result = report.metrics[source_metric]
            quantities[f"{name}.{target_key}"] = EngineeringValue(
                value=result.value, unit=unit,
                basis="unknown" if result.value is None else "assumed" if result.basis == "includes_assumptions" else "measured",
                source=f"Derived from {name}.process; see input snapshot" if result.value is not None else None,
            )
            if result.value is None:
                issues.append(f"{name}.{source_metric}: {result.reason}; missing {', '.join(result.missing_inputs)}")
        if not option.process.acceptance_verified:
            issues.append(f"{name} output acceptance is unverified")
    if not data.equivalence_verified:
        issues.append("Manual/apparatus output equivalence is unverified")

    def calc(name: str, keys: list[str], unit: str, function: Callable[[list[float]], float]) -> Metric:
        """Resolve and record a calculated dependency for later metrics."""
        missing = [key for key in keys if quantities[key].value is None]
        assumed = any(quantities[key].basis == "assumed" for key in keys)
        metric = Metric(value=None if missing else function([float(quantities[k].value) for k in keys]),
                        unit=unit, status="unknown" if missing else "calculated",
                        basis="unknown" if missing else "includes_assumptions" if assumed else "derived_from_sourced_inputs",
                        dependencies=keys, missing_inputs=missing,
                        reason="Required inputs are unknown" if missing else None)
        metrics[name] = metric
        # Economic differences may be negative; EngineeringValue permits them.
        quantities[name] = EngineeringValue(value=metric.value, unit=unit,
            basis="unknown" if missing else "assumed" if assumed else "measured",
            source=f"Calculated metric {name}" if not missing else None)
        return metric

    for name in ("baseline", "candidate"):
        calc(f"{name}.upfront_total", [f"{name}.upfront.{k}" for k in UPFRONT_KEYS], "USD", sum)
        calc(f"{name}.annual_capacity", [f"{name}.{k}" for k in ("nominal_rate", "scheduled_hours", "utilization", "downtime")],
             "accepted outputs/year", lambda v: v[0] * v[1] * v[2] * (1 - v[3]))
        calc(f"{name}.annual_operating_cost", [f"{name}.variable_unit_cost", "annual_demand", f"{name}.annual_fixed_cost"],
             "USD/year", lambda v: v[0] * v[1] + v[2])
        calc(f"{name}.horizon_total_cost", [f"{name}.upfront_total", f"{name}.annual_operating_cost", "horizon_years"],
             "USD", lambda v: v[0] + v[1] * v[2])
    calc("incremental_upfront", ["candidate.upfront_total", "baseline.upfront_total"], "USD", lambda v: v[0] - v[1])
    calc("unit_variable_saving", ["baseline.variable_unit_cost", "candidate.variable_unit_cost"], "USD/accepted output", lambda v: v[0] - v[1])
    calc("annual_operating_saving", ["baseline.annual_operating_cost", "candidate.annual_operating_cost"], "USD/year", lambda v: v[0] - v[1])
    calc("horizon_net_saving", ["baseline.horizon_total_cost", "candidate.horizon_total_cost"], "USD", lambda v: v[0] - v[1])
    calc("annual_fixed_difference", ["candidate.annual_fixed_cost", "baseline.annual_fixed_cost"], "USD/year", lambda v: v[0] - v[1])

    capital = quantities["incremental_upfront"].value
    saving = quantities["annual_operating_saving"].value
    payback = Metric(value=None, unit="years", status="unknown", basis="unknown",
                     dependencies=["incremental_upfront", "annual_operating_saving"],
                     missing_inputs=[k for k in ("incremental_upfront", "annual_operating_saving") if quantities[k].value is None])
    if capital is not None and saving is not None:
        if saving > 0 or (capital <= 0 and saving == 0):
            payback = calc("simple_payback_years", payback.dependencies, "years", lambda v: max(v[0], 0) / v[1] if v[1] > 0 else 0)
        else:
            payback.status = "undefined"
            payback.reason = "No positive recurring savings; compare horizon cost for lower-upfront/higher-running-cost tradeoffs"
    metrics["simple_payback_years"] = payback

    direction: Literal["above", "below", "all_volumes", "no_volumes", "unknown"] = "unknown"
    # Threshold is annual volume that recovers capital across the analysis horizon.
    keys = ["incremental_upfront", "annual_fixed_difference", "horizon_years", "unit_variable_saving"]
    missing = [k for k in keys if quantities[k].value is None]
    threshold = Metric(value=None, unit="accepted outputs/year", status="unknown", basis="unknown", dependencies=keys, missing_inputs=missing)
    if not missing:
        capital_v, fixed_v, horizon, unit_saving = [float(quantities[k].value) for k in keys]
        burden = capital_v / horizon + fixed_v
        if unit_saving == 0:
            direction = "all_volumes" if burden <= 0 else "no_volumes"
            threshold.status = "undefined"
            threshold.reason = "No unit-cost difference; capital/fixed-cost difference determines all volumes"
        elif unit_saving > 0:
            direction = "above"
            threshold = calc("horizon_break_even_annual_volume", keys, "accepted outputs/year", lambda v: max(0, (v[0] / v[2] + v[1]) / v[3]))
        elif burden <= 0:
            direction = "below"
            threshold = calc("horizon_break_even_annual_volume", keys, "accepted outputs/year", lambda v: max(0, (v[0] / v[2] + v[1]) / v[3]))
        else:
            direction = "no_volumes"
            threshold.status = "undefined"
            threshold.reason = "Candidate has higher variable cost and higher capital/fixed burden"
    metrics["horizon_break_even_annual_volume"] = threshold

    demand = data.annual_demand.value
    capacity_shortfall = False
    horizon_unsupported = False
    for name, option in (("baseline", data.baseline), ("candidate", data.candidate)):
        capacity = metrics[f"{name}.annual_capacity"].value
        if demand is not None and capacity is not None and demand > capacity:
            issues.append(f"{name} capacity cannot meet annual demand")
            capacity_shortfall = True
        if data.horizon_years.value is not None and option.useful_life.value is not None:
            if data.horizon_years.value > option.useful_life.value:
                issues.append(f"{name} useful life is shorter than horizon; replacement costs are not modeled")
                horizon_unsupported = True
        if option.useful_life.value is None:
            issues.append(f"{name}.useful_life is unknown")
    required = ["baseline.annual_capacity", "candidate.annual_capacity", "horizon_net_saving"]
    for key in required:
        if metrics[key].value is None:
            issues.append(f"{key} is unknown: {', '.join(metrics[key].missing_inputs)}")
    status: Literal["calculated", "insufficient_evidence", "infeasible_capacity", "unsupported_horizon"] = (
        "infeasible_capacity" if capacity_shortfall else "unsupported_horizon" if horizon_unsupported
        else "insufficient_evidence" if issues else "calculated")
    decision: Literal["candidate_lower_cost", "baseline_lower_cost", "equal_cost", "undetermined"] = "undetermined"
    if status == "calculated":
        net = metrics["horizon_net_saving"].value
        decision = "equal_cost" if abs(net) < 1e-9 else "candidate_lower_cost" if net > 0 else "baseline_lower_cost"
    return ComparisonResult(status=status, decision=decision, metrics=metrics,
        horizon_break_even_direction=direction, issues=issues,
        assumptions_present=any(q.basis == "assumed" for q in quantities.values()))


def compare_investment(data: InvestmentComparisonInput) -> InvestmentComparisonReport:
    """Evaluate the base case and every sourced sensitivity case independently."""
    data = InvestmentComparisonInput.model_validate(data.model_dump())
    return InvestmentComparisonReport(base=compare_case(data),
        scenarios={s.name: compare_case(apply_scenario(data, s)) for s in data.scenarios},
        input_snapshot=data,
        limitations=[
            "Constant annual demand and linear variable cost; batch-size economies require separate representative inputs.",
            "Undiscounted cost comparison; financing, tax, revenue, resale and replacement are not modeled.",
            "Capacity uses nominal accepted rate × scheduled hours × utilization × (1 − downtime); avoid double-counting losses already in nominal rate.",
            "Thresholds are continuous annual volumes; integer demand must be rounded and checked against both capacities.",
            "Metrics can be calculated conditionally while decision remains blocked by evidence, capacity or horizon gates.",
        ])


def compare_file(input_path: Path, output_path: Path) -> None:
    """Validate comparison JSON and exclusively create a provenance-rich report."""
    report = compare_investment(InvestmentComparisonInput.model_validate_json(input_path.read_text()))
    with output_path.open("x", encoding="utf-8") as destination:
        destination.write(report.model_dump_json(indent=2) + "\n")
