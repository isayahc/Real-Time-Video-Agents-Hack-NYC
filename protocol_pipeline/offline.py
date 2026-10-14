"""Offline CW-02 protocol adapter with explicit candidate equipment and boundaries.

This loads existing planning documents; it does not extract a protocol from video
or infer measurements. Preparation ranges are displayed, never added to winding.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .design import ApparatusRequirements, write_json
from .evaluation import ProcessEvaluationInput, UNITS, evaluate_process
from .models import Capability, EngineeringInputs, EngineeringValue, Operation, StrictModel


class CoilStep(StrictModel):
    """An operation from the existing proposed machine protocol."""

    operation: str = Field(min_length=1)
    apparatus: str = Field(min_length=1)
    human_action: str = Field(min_length=1)
    expected: str = Field(min_length=1)


class CoilProtocol(StrictModel):
    """Existing fixed protocol, explicitly separate from video observations."""

    basis: str
    steps: list[CoilStep] = Field(min_length=1)
    equivalence_gate: str


class WorkflowNode(StrictModel):
    """One proposed operation with source reference and candidate equipment."""

    id: str
    phase: Literal["preparation", "forming", "finishing"]
    description: str
    frequency: str
    equipment: list[str] = Field(min_length=1)
    source_ref: str
    basis: Literal["proposed_machine_protocol", "workflow_hypothesis"]
    verification: str
    attended_range_s: tuple[float, float] | None = None

    @model_validator(mode="after")
    def valid_range(self) -> WorkflowNode:
        """Reject negative or inverted illustrative preparation ranges."""
        if self.attended_range_s is not None:
            low, high = self.attended_range_s
            if not 0 <= low <= high:
                raise ValueError("Preparation range must be nonnegative and ordered")
        return self


class WorkflowLink(StrictModel):
    """Proposed ordering or concurrent activity; not a measured execution trace."""

    source: str
    target: str
    relation: Literal["before", "during"]
    basis: Literal["proposed_requires_review"] = "proposed_requires_review"


class WorkflowGraph(StrictModel):
    """Proposed process graph requiring review before scheduling or execution."""

    nodes: list[WorkflowNode]
    links: list[WorkflowLink]
    limitations: list[str]

    @model_validator(mode="after")
    def references(self) -> WorkflowGraph:
        """Reject duplicate nodes, broken links and cycles in proposed ordering."""
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Workflow node IDs must be unique")
        adjacency: dict[str, list[str]] = {node: [] for node in ids}
        for link in self.links:
            if link.source not in adjacency or link.target not in adjacency or link.source == link.target:
                raise ValueError("Workflow link must reference distinct existing nodes")
            if link.relation == "before":
                adjacency[link.source].append(link.target)
        active: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            """Check the proposed ordering without treating concurrency as ordering."""
            if node in active:
                raise ValueError("Workflow ordering contains a cycle")
            if node in visited:
                return
            active.add(node)
            for following in adjacency[node]:
                visit(following)
            active.remove(node)
            visited.add(node)

        for node in ids:
            visit(node)
        return self


# Task-specific candidates, not automatically inferred or verified BOM items.
PREP_EQUIPMENT: dict[str, list[str]] = {
    "verify_stock": ["wire stock", "stock specification/label", "dimensional measuring tools"],
    "prepare_mandrel": ["mandrel/fixture", "inspection tools", "cleaning materials if required"],
    "prepare_containers": ["labels", "accepted-part tray", "scrap container"],
    "thread_and_tension": ["wire guide", "spool brake/dancer", "tension sensor"],
    "home_and_calibrate": ["axis controller", "home sensors", "inspection calibration reference"],
    "trial_coil": ["winding apparatus", "released-coil inspection tools"],
    "measure_cut": ["length measure", "manual wire cutter"],
    "prepare_ends": ["manual wire preparation tools if required"],
    "orient_secure": ["removable mandrel clamp"],
}
CORE_OPERATIONS = {"constrain", "establish_contact", "relative_rotation", "maintain_tension", "verify_and_release"}
FINISHING = {"rework", "label_store", "scrap_recover", "cleanup", "maintenance"}
LIMITATIONS = [
    "Fixed planning protocol; original video and annotation have not been ingested or reviewed.",
    "Equipment and graph links are proposed candidates, not a verified BOM or executable schedule.",
    "Preparation applicability and repetitions need review; trial coils may repeat forming/inspection.",
    "Threading, clamping, cutting and inspection may overlap existing allowances; ranges are not summed.",
    "Full-process measurements and released-coil acceptance criteria remain unresolved.",
]


def load_json(path: Path) -> dict[str, Any]:
    """Read a repository planning source without any remote access."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def compile_coil(root: Path) -> tuple[WorkflowGraph, ApparatusRequirements, dict[str, dict[str, str]]]:
    """Adapt the fixed CW-02 sources into candidate operations and equipment.

    Source references identify planning document fields rather than pretending to
    be observed action IDs. Unknown task variants fail instead of receiving an
    invented apparatus mapping.
    """
    protocol_path = "snapshots/v2/protocol.json"
    prep_path = "snapshots/v1/preprocessing-estimates.json"
    baseline_path = "benchmarks/coil-winding/baseline.json"
    protocol = CoilProtocol.model_validate(load_json(root / protocol_path))
    operations = [step.operation for step in protocol.steps]
    if len(operations) != len(set(operations)) or set(operations) != CORE_OPERATIONS:
        raise ValueError("CW-02 adapter requires the five unique supported coil operations")
    preparation = load_json(root / prep_path)
    baseline = load_json(root / baseline_path)
    nodes: list[WorkflowNode] = []
    for category, frequency, scale, unit in (("batch_steps", "per_batch", 60, "minutes"),
                                              ("per_attempt_steps", "per_attempt", 1, "seconds")):
        for index, step in enumerate(preparation[category]):
            if step["id"] not in PREP_EQUIPMENT:
                raise ValueError(f"Unmapped preparation operation: {step['id']}")
            nodes.append(WorkflowNode(
                id="prep_" + step["id"], phase="preparation", description=step["operation"],
                frequency=frequency, equipment=PREP_EQUIPMENT[step["id"]],
                source_ref=f"{prep_path}#/{category}/{index}", basis="workflow_hypothesis",
                verification=step["applicability"] + "; confirm task boundaries before adding time",
                attended_range_s=(scale * step[unit + "_low"], scale * step[unit + "_high"]),
            ))
    if {node.id for node in nodes} != {"prep_" + key for key in PREP_EQUIPMENT}:
        raise ValueError("Preparation must preserve all nine unique source candidates")
    for index, step in enumerate(protocol.steps):
        nodes.append(WorkflowNode(
            id=step.operation, phase="forming", description=step.human_action + ": " + step.expected,
            frequency="per_attempt", equipment=[step.apparatus],
            source_ref=f"{protocol_path}#/steps/{index}", basis="proposed_machine_protocol",
            verification=protocol.equivalence_gate,
        ))
    for index, step in enumerate(baseline["steps"]):
        if step["id"] in FINISHING:
            nodes.append(WorkflowNode(
                id=step["id"], phase="finishing", description=step["operation"],
                frequency=step["frequency"], equipment=[step["tools"]],
                source_ref=f"{baseline_path}#/steps/{index}", basis="workflow_hypothesis",
                verification=step["verification"] + "; candidate transfer from manual baseline requires review",
            ))
    links = [WorkflowLink(source=a, target=b, relation=relation) for a, b, relation in (
        ("prep_verify_stock", "constrain", "before"),
        ("prep_prepare_mandrel", "constrain", "before"),
        ("constrain", "establish_contact", "before"),
        ("establish_contact", "relative_rotation", "before"),
        ("maintain_tension", "relative_rotation", "during"),
        ("relative_rotation", "verify_and_release", "before"),
        ("verify_and_release", "label_store", "before"),
    )]
    if {node.id for node in nodes if node.phase == "finishing"} != FINISHING:
        raise ValueError("Baseline must preserve all five finishing/maintenance candidates")
    graph = WorkflowGraph(nodes=nodes, links=links, limitations=LIMITATIONS)
    requirements = ApparatusRequirements(
        protocol_operations=[Operation(
            id=node.id, intent=node.description, physical_operation=node.description,
            object_ids=["wire", "coil_station"], source_action_ids=[node.source_ref],
            preconditions=["Confirm applicability, equipment specifications and source protocol"],
            postconditions=[node.verification], constraints=["Candidate workflow; not physically verified"],
        ) for node in nodes],
        required_capabilities=[Capability(
            id="cap_" + node.id, name="Support " + node.id.replace("_", " "),
            operation_ids=[node.id], rationale="Candidate equipment: " + "; ".join(node.equipment),
        ) for node in nodes],
        unresolved_requirements=LIMITATIONS + [protocol.equivalence_gate],
        engineering_inputs=EngineeringInputs(),
        note="Fixed-protocol offline adapter. source_action_ids are planning-document references, not video actions. No model calls.",
    )
    sources = {path: {"sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
               for path in (protocol_path, prep_path, baseline_path, "examples/process-evaluation/coil-v2-partial.json")}
    return graph, requirements, sources


def coil_report(summary: dict[str, Any]) -> str:
    """Render candidate equipment, separated accounting and missing evidence."""
    graph = WorkflowGraph.model_validate(summary["workflow"])

    def cell(value: str) -> str:
        """Keep source text from changing the Markdown table structure."""
        return value.replace("|", "\\|").replace("\n", " ")

    lines = ["# CW-02 offline protocol-to-resource report", "",
             "**Planning sources only. No live inference, physical validation or demonstrated savings.**", "",
             "## Candidate workflow and apparatus", "",
             "Each operation maps to a candidate capability in `apparatus-requirements.json`.", "",
             "| Operation | Phase / repetition | Candidate equipment | Preparation attended range |",
             "| --- | --- | --- | --- |"]
    for node in graph.nodes:
        timing = (f"{node.attended_range_s[0]:g}–{node.attended_range_s[1]:g} s/event (unmeasured)"
                  if node.attended_range_s else "Unknown")
        lines.append(f"| {cell(node.id + ': ' + node.description)} | {node.phase} / {node.frequency} | {cell('; '.join(node.equipment))} | {timing} |")
    lines += ["", "Tension maintenance runs during winding in the proposed graph. Other ordering and candidate applicability require review; this graph is not a schedule.", "",
              "Preparation ranges are not added to winding touch-time estimates because overlapping work is unresolved.", "",
              "## Full-process resource evaluation", "",
              "Boundary: stock verification and station preparation through accepted-coil storage, scrap accounting and station reset, including allocated maintenance.", "",
              "Full-process values remain unknown. The winding-only inputs below do not populate this boundary.", "",
              "| Metric | Full process | Winding-only planning scenario |", "| --- | --- | --- |"]
    for key, metric in summary["full_process_evaluation"]["metrics"].items():
        partial = summary["winding_only_evaluation"]["metrics"][key]
        label = "Unknown" if partial["value"] is None else f"{partial['value']:.6g} {partial['unit']} (assumptions)"
        lines.append(f"| {key} | Unknown | {label} |")
    lines += ["", "Winding-only scenario assumes 100 attempts and 95 accepted outputs; acceptance is unverified. Cost, yield and throughput are conditional calculations, not measurements.", "",
              "## Missing measurements and review", ""]
    for item in summary["measurement_checklist"]:
        lines.append(f"- {item['field']} ({item['unit']}): {item['instruction']}")
    lines += ["", "## Limitations", ""] + ["- " + item for item in graph.limitations]
    lines += ["", "[Process graph](process-graph.json) · [Candidate requirements](apparatus-requirements.json) · [Full-process input template](full-process-input.json) · [Structured summary](summary.json)", ""]
    return "\n".join(lines)


def run_coil_offline(root: Path, output: Path) -> dict[str, Any]:
    """Execute fixed protocol → candidate requirements → local resource evaluation.

    Preserve winding-only assumptions in a separate report, emit a full-boundary
    measurement template and refuse to overwrite earlier evidence.
    """
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    graph, requirements, sources = compile_coil(root)
    full = ProcessEvaluationInput(
        configuration_id="CW-02-full-process-unmeasured",
        functional_unit="One accepted released coil; actual acceptance criteria unresolved",
        boundary="Stock verification and station preparation through accepted-coil storage, scrap accounting and station reset, including allocated maintenance",
        inputs={key: EngineeringValue(unit=unit, basis="unknown") for key, unit in UNITS.items()},
    )
    partial = ProcessEvaluationInput.model_validate(load_json(root / "examples/process-evaluation/coil-v2-partial.json"))
    focused = {
        "accepted_count": (["verify_and_release", "rework", "label_store"], "Count final accepted coils once after any rework and reinspection."),
        "attempted_count": (["relative_rotation", "rework"], "Count distinct production attempts; record setup/trial stock separately and do not count rework as a new attempt."),
        "elapsed_s": ([node.id for node in graph.nodes], "Measure batch wall-clock start/end including preparation, waiting and reset; do not sum concurrent task durations."),
        "labor_s": ([node.id for node in graph.nodes], "Measure attended intervals per operator; reconcile threading/clamping/touch-time overlaps and allocated maintenance."),
        "electricity_wh": ([node.id for node in graph.nodes], "Meter the full boundary including setup, idle and cleanup; retain any justified allocation."),
        "consumed_stock_g": (["prep_verify_stock", "prep_trial_coil", "prep_measure_cut", "relative_rotation", "rework"], "Weigh all consumed stock including setup/trial losses, retained leads and rejects."),
        "recoverable_scrap_g": (["verify_and_release", "rework", "scrap_recover"], "Weigh segregated recoverable scrap; avoid counting it as both recovered and unrecovered."),
        "unrecovered_waste_g": (["verify_and_release", "rework", "scrap_recover", "cleanup"], "Record final unrecovered material disposition across the full boundary."),
    }
    checklist = [{"field": key, "unit": unit,
                  "operation_ids": focused[key][0] if key in focused else [node.id for node in graph.nodes],
                  "instruction": focused[key][1] if key in focused else "Source the rate or explicit batch cost allocation; missing is unknown, and zero requires evidence."}
                 for key, unit in UNITS.items()]
    checklist.append({"field": "acceptance_verified", "unit": "boolean", "operation_ids": ["verify_and_release"],
                      "instruction": "Resolve released geometry/material tolerances and downstream function; record the acceptance method and evidence."})
    summary = {"schema_version": 1, "status": "planning_requires_measurements", "live_inference": False,
               "physical_validation": False, "sources": sources, "workflow": graph.model_dump(),
               "full_process_evaluation": evaluate_process(full).model_dump(),
               "winding_only_evaluation": evaluate_process(partial).model_dump(),
               "measurement_checklist": checklist}
    markdown = coil_report(summary)
    output.mkdir(parents=True)
    for name, data in (("process-graph.json", graph.model_dump()),
                       ("apparatus-requirements.json", requirements.model_dump()),
                       ("full-process-input.json", full.model_dump()),
                       ("summary.json", summary), ("measurement-checklist.json", checklist)):
        write_json(output / name, data)
    (output / "report.md").write_text(markdown, encoding="utf-8")
    (output / "report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>CW-02 offline report</title><style>body{max-width:1100px;margin:32px auto;padding:0 20px;'
        'font:16px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}</style>'
        '<body><pre>' + html.escape(markdown) + '</pre></body></html>', encoding="utf-8")
    return summary
