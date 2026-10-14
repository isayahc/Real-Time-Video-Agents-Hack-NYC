"""Offline illustrative failure replay with explicit step and resource evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .alternatives import AlternativeSet
from .design import write_json
from .evaluation import evaluate_process
from .iteration import DeviationTolerance, differences
from .models import EngineeringValue, StrictModel
from .offline import compile_coil


class StepObservation(StrictModel):
    """Explicit reviewed step status; absence alone never establishes a skip."""

    operation_id: str
    status: Literal["completed", "skipped", "unknown"]
    evidence_refs: list[str] = Field(min_length=1)


def assess_steps(required: list[str], observations: list[StepObservation], known: set[str]) -> dict[str, list[str]]:
    """Separate explicit skipped requirements from absent or inconclusive evidence."""
    ids = [item.operation_id for item in observations]
    if len(ids) != len(set(ids)) or len(required) != len(set(required)):
        raise ValueError("Step IDs must be unique")
    if not set(ids + required).issubset(known):
        raise ValueError("Step references unknown workflow operations")
    if any(not ref.strip() for item in observations for ref in item.evidence_refs):
        raise ValueError("Step evidence references cannot be blank")
    statuses = {item.operation_id: item.status for item in observations}
    return {"skipped_required": [step for step in required if statuses.get(step) == "skipped"],
            "unknown_required": [step for step in required if statuses.get(step) in (None, "unknown")],
            "completed_required": [step for step in required if statuses.get(step) == "completed"]}


def run_failures(root: Path, output: Path) -> dict[str, Any]:
    """Replay four fabricated CW-02 cases through actual step/resource checks.

    Uses the existing hypothetical CW-02 batch solely as an arithmetic reference.
    Every scenario remains illustrative; no sensor or physical run is claimed.
    """
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    data = AlternativeSet.model_validate_json((root / "examples/apparatus-alternatives/illustrative-input.json").read_text())
    process = next(item.option.process for item in data.options if item.id == "cw02")
    graph, _, sources = compile_coil(root)
    known = {node.id for node in graph.nodes}
    required = ["prep_verify_stock", "relative_rotation", "verify_and_release"]
    prediction = evaluate_process(process)
    cases: dict[str, Any] = {}
    for name in ("missed_preparation", "delayed_batch", "excess_rejects", "incomplete_observations"):
        actual = process.model_copy(deep=True)
        steps = [StepObservation(operation_id=step, status="completed",
                 evidence_refs=["Fabricated replay scenario: " + name]) for step in required]
        if name == "missed_preparation":
            steps[0].status = "skipped"
        elif name == "delayed_batch":
            actual.inputs["elapsed_s"] = EngineeringValue(value=9000, unit="s", basis="assumed", source="Fabricated delayed full batch, not a measured winding-stage duration")
        elif name == "excess_rejects":
            actual.inputs["accepted_count"] = EngineeringValue(value=50, unit="count", basis="assumed", source="Fabricated 50 accepted of 100 attempts")
            # Material disposition is not inferred from counts alone.
            for key in ("recoverable_scrap_g", "unrecovered_waste_g"):
                actual.inputs[key] = EngineeringValue(unit="g", basis="unknown")
        else:
            steps = steps[1:]
            for key in ("accepted_count", "labor_s", "electricity_wh"):
                actual.inputs[key] = EngineeringValue(unit=actual.inputs[key].unit, basis="unknown")
        evaluated = evaluate_process(actual)
        deviation = differences(prediction, evaluated, {key: DeviationTolerance(relative=0.1) for key in prediction.metrics if key in (
            "cost_usd_per_accepted", "labor_s_per_accepted", "electricity_wh_per_accepted", "stock_g_per_accepted",
            "unrecovered_waste_g_per_accepted", "accepted_outputs_per_hour")})
        cases[name] = {"evidence_kind": "illustrative", "step_observations": [step.model_dump() for step in steps],
                       "steps": assess_steps(required, steps, known), "process_input": actual.model_dump(),
                       "process_report": evaluated.model_dump(), "deviations": deviation.model_dump()}
    result = {"schema_version": 1, "evidence_kind": "illustrative", "physical_validation": False,
              "required_steps_basis": "Selected candidate requirements for this fabricated replay, not a verified source protocol",
              "source_workflow_hashes": sources, "reference_input": process.model_dump(),
              "reference_report": prediction.model_dump(), "cases": cases,
              "limitations": ["Full-batch delay does not locate a winding-stage cause.",
                              "Explicit skip is distinct from missing evidence.",
                              "Counts alone do not measure reject material mass or recovery.",
                              "No failed step automatically triggers physical corrective action."]}
    lines = ["# Offline failure replay", "", "**Fabricated scenarios; no physical observations or sensor detection claimed.**", "",
             "| Case | Explicit skipped required steps | Unknown required steps | Metric deviations outside 10% | Unknown metrics |",
             "| --- | --- | --- | --- | --- |"]
    for name, case in cases.items():
        metrics = case["deviations"]["metrics"]
        flagged = [key for key, value in metrics.items() if value["outside_tolerance"] is True]
        unknown = [key for key, value in metrics.items() if value["direction"] == "unknown"]
        lines.append("| " + name + " | " + " | ".join(
            ", ".join(values) or "none" for values in (case["steps"]["skipped_required"], case["steps"]["unknown_required"], flagged, unknown)) + " |")
    lines += ["", "A missing observation does not establish a skipped operation. A delay in batch elapsed time does not prove winding was the cause.", ""]
    output.mkdir(parents=True)
    write_json(output / "summary.json", result)
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return result
