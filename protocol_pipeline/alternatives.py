# SPDX-License-Identifier: MPL-2.0
"""Compare multiple apparatus concepts with shared boundaries and explicit evidence.

Pairwise economics use the existing investment comparator. Conditional arithmetic
never bypasses its acceptance, capacity, or measurement gates.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .design import write_json
from .evaluation import evaluate_process
from .investment import InvestmentComparisonInput, InvestmentOption, check_quantity, compare_investment
from .models import EngineeringValue, StrictModel


class ApparatusAlternative(StrictModel):
    """Candidate equipment/controls and one disjoint investment cost model."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    equipment: list[str] = Field(min_length=1)
    controls: list[str] = Field(min_length=1)
    measurement_gaps: list[str] = Field(min_length=1)
    option: InvestmentOption


class AlternativeScenario(StrictModel):
    """Shared demand and optional shared price assumptions applied to every option."""

    name: str = Field(min_length=1)
    annual_demand: EngineeringValue
    loaded_labor_rate: EngineeringValue | None = None
    electricity_rate: EngineeringValue | None = None

    @model_validator(mode="after")
    def units(self) -> AlternativeScenario:
        """Validate scenario units/ranges before applying shared overrides."""
        check_quantity(self.annual_demand, "accepted outputs/year")
        if self.loaded_labor_rate is not None:
            check_quantity(self.loaded_labor_rate, "USD/operator-hour")
        if self.electricity_rate is not None:
            check_quantity(self.electricity_rate, "USD/kWh")
        return self


class AlternativeSet(StrictModel):
    """Three or more options sharing one declared output and process boundary."""

    schema_version: Literal[1] = 1
    evidence_kind: Literal["unmeasured_concepts", "illustrative_assumptions"]
    description: str
    options: list[ApparatusAlternative] = Field(min_length=2)
    horizon_years: EngineeringValue
    equivalence_verified: bool = False
    equivalence_source: str | None = None
    scenarios: list[AlternativeScenario] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def comparable(self) -> AlternativeSet:
        """Reject mismatched boundaries/IDs and synthetic verification claims."""
        ids = [item.id for item in self.options]
        configurations = [item.option.process.configuration_id for item in self.options]
        if len(ids) != len(set(ids)) or len(configurations) != len(set(configurations)):
            raise ValueError("Alternative IDs and configuration IDs must be unique")
        first = self.options[0].option.process
        for item in self.options:
            process = item.option.process
            if process.functional_unit != first.functional_unit or process.boundary != first.boundary:
                raise ValueError("All alternatives require identical functional units and full-process boundaries")
        if len({scenario.name for scenario in self.scenarios}) != len(self.scenarios):
            raise ValueError("Scenario names must be unique")
        check_quantity(self.horizon_years, "years", positive=True)
        if self.equivalence_verified and not self.equivalence_source:
            raise ValueError("Verified equivalence needs evidence")
        if self.evidence_kind == "illustrative_assumptions" and (
            self.equivalence_verified or any(item.option.process.acceptance_verified for item in self.options)
        ):
            raise ValueError("Illustrative assumptions cannot assert verified physical acceptance/equivalence")
        return self


def scenario_option(option: InvestmentOption, scenario: AlternativeScenario) -> InvestmentOption:
    """Apply shared rates to a detached option without mutating the input."""
    payload = option.model_dump()
    for key in ("loaded_labor_rate", "electricity_rate"):
        value = getattr(scenario, key)
        if value is not None:
            payload["process"]["inputs"][key] = value.model_dump()
    return InvestmentOption.model_validate(payload)


def evaluate_alternatives(data: AlternativeSet) -> dict[str, Any]:
    """Evaluate all pairs and resources under each shared scenario.

    No overall winner is declared when acceptance/equivalence is unresolved.
    Finite conditional costs are exposed for exploration alongside comparator
    decisions; missing inputs and capacity limitations remain explicit.
    """
    data = AlternativeSet.model_validate(data.model_dump())
    scenarios: dict[str, Any] = {}
    for scenario in data.scenarios:
        options = {item.id: scenario_option(item.option, scenario) for item in data.options}
        resources = {key: evaluate_process(option.process).model_dump() for key, option in options.items()}
        comparisons: list[dict[str, Any]] = []
        for first, second in itertools.combinations(data.options, 2):
            comparison = InvestmentComparisonInput(
                baseline=options[first.id], candidate=options[second.id],
                equivalence_verified=data.equivalence_verified,
                equivalence_source=data.equivalence_source,
                annual_demand=scenario.annual_demand, horizon_years=data.horizon_years,
            )
            result = compare_investment(comparison)
            comparisons.append({"baseline": first.id, "candidate": second.id, "result": result.base.model_dump()})
        scenarios[scenario.name] = {"shared_inputs": scenario.model_dump(), "resources": resources,
                                    "comparisons": comparisons}
    return {"schema_version": 1, "evidence_kind": data.evidence_kind,
            "input_snapshot": data.model_dump(), "scenarios": scenarios,
            "overall_recommendation": "undetermined", "physical_validation": False,
            "note": "Pairwise decisions retain evidence/capacity gates. Conditional costs do not establish actual apparatus performance."}


def alternative_report(summary: dict[str, Any]) -> str:
    """Render controls, conditional economics, capacity and missing evidence."""
    data = AlternativeSet.model_validate(summary["input_snapshot"])

    def cell(value: str) -> str:
        """Prevent source strings from breaking Markdown table cells."""
        return value.replace("|", "\\|").replace("\n", " ")

    def metric(value: dict[str, Any]) -> str:
        """Preserve unknowns/undefined results instead of showing invented zeros."""
        return value["status"] if value["value"] is None else f"{value['value']:,.4f}".rstrip("0").rstrip(".")

    lines = ["# Apparatus alternatives: manual fixture, motorized winder, CW-02", "",
             f"**Evidence: {data.evidence_kind}. Physical validation: false. Recommendation: undetermined.**", "",
             data.description, "", "## Shared comparison boundary", "",
             data.options[0].option.process.functional_unit, "",
             data.options[0].option.process.boundary, "",
             "## Proposed architectures", "",
             "| Alternative | Candidate equipment | Control / operator responsibilities |",
             "| --- | --- | --- |"]
    for option in data.options:
        lines.append(f"| {cell(option.label)} | {cell('; '.join(option.equipment))} | {cell('; '.join(option.controls))} |")
    lines += ["", "## Supplied model inputs", "",
              "Known numeric inputs below retain their basis; illustrative inputs are hypothetical and unmeasured.", "",
              "| Alternative | Equipment USD | Other deployment USD | Annual fixed USD | Batch attempts / accepted | Elapsed / attended seconds | Batch Wh |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    def supplied(value: EngineeringValue | None) -> str:
        """Show input evidence basis instead of silently treating budgets as facts."""
        if value is None or value.value is None:
            return "unknown"
        return f"{value.value:g} ({value.basis})"

    for option in data.options:
        inputs = option.option.process.inputs
        upfront = option.option.upfront
        other = "; ".join(key + ": " + supplied(upfront.get(key)) for key in ("installation", "integration", "training"))
        values = [supplied(upfront.get("equipment")), other, supplied(option.option.annual_fixed_cost),
                  supplied(inputs.get("attempted_count")) + " / " + supplied(inputs.get("accepted_count")),
                  supplied(inputs.get("elapsed_s")) + " / " + supplied(inputs.get("labor_s")), supplied(inputs.get("electricity_wh"))]
        lines.append("| " + cell(option.label) + " | " + " | ".join(values) + " |")
    lines += ["", "## Scenario results", "",
              "Costs below are conditional arithmetic. All options retain unverified output acceptance/equivalence; none is an approved investment choice.", "",
              "Variable unit cost excludes upfront and annual fixed allocations, which appear in horizon cost. Resource values use supplied full-batch inputs, not summed preparation ranges."]
    for name, scenario in summary["scenarios"].items():
        lines += ["", "### " + name, "",
                  "| Alternative | Variable USD/coil | Labor s/coil | Wh/coil | Waste g/coil | Accepted/h | Annual capacity | Horizon cost USD |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for option in data.options:
            resources = scenario["resources"][option.id]["metrics"]
            pair = next(pair for pair in scenario["comparisons"] if option.id in (pair["baseline"], pair["candidate"]))
            prefix = "baseline" if pair["baseline"] == option.id else "candidate"
            economics = pair["result"]["metrics"]
            keys = ("cost_usd_per_accepted", "labor_s_per_accepted", "electricity_wh_per_accepted",
                    "unrecovered_waste_g_per_accepted", "accepted_outputs_per_hour")
            values = [metric(resources[key]) for key in keys]
            values += [metric(economics[prefix + ".annual_capacity"]), metric(economics[prefix + ".horizon_total_cost"])]
            lines.append("| " + cell(option.label) + " | " + " | ".join(values) + " |")
        lines += ["", "| Comparison | Evidence/capacity status | Decision | Break-even annual volume (direction)* | Payback years* |", "| --- | --- | --- | ---: | ---: |"]
        for pair in scenario["comparisons"]:
            result = pair["result"]
            direction = result["horizon_break_even_direction"]
            threshold = metric(result["metrics"]["horizon_break_even_annual_volume"])
            lines.append(f"| {cell(pair['baseline'])} → {cell(pair['candidate'])} | {result['status']} | {result['decision']} | {threshold} ({direction}) | {metric(result['metrics']['simple_payback_years'])} |")
        lines += ["", "*Threshold and payback are conditional and require checking capacity, output equivalence, and all supplied assumptions."]
        issues = sorted({issue for pair in scenario["comparisons"] for issue in pair["result"]["issues"]})
        lines += ["", "Blocking issues:", ""] + ["- " + cell(issue) for issue in issues]
    lines += ["", "## Measurements needed", ""]
    for option in data.options:
        lines += ["- " + cell(option.label) + ": " + cell("; ".join(option.measurement_gaps))]
    lines += ["", "## Limits and assumptions", ""] + ["- " + cell(item) for item in data.limitations]
    return "\n".join(lines) + "\n"


def run_alternatives(input_path: Path, output: Path) -> dict[str, Any]:
    """Create reproducible comparison reports without inference or overwrites."""
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    raw = input_path.read_bytes()
    data = AlternativeSet.model_validate_json(raw)
    summary = evaluate_alternatives(data)
    summary["source_sha256"] = hashlib.sha256(raw).hexdigest()
    markdown = alternative_report(summary)
    output.mkdir(parents=True)
    write_json(output / "summary.json", summary)
    (output / "input.json").write_bytes(raw)
    (output / "report.md").write_text(markdown, encoding="utf-8")
    return summary
