# SPDX-License-Identifier: MPL-2.0
"""Compile explicitly supplied protocol plans into apparatus and resource contracts.

No task-specific lookup, video inference, scheduling, or measurement imputation
occurs here. Inputs can describe any process using the same versioned schema.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .design import ApparatusRequirements, write_json
from .evaluation import ProcessEvaluationInput, evaluate_process
from .models import Capability, EngineeringInputs, EngineeringValue, Operation, StrictModel


class PlannedOperation(StrictModel):
    """A sourced process operation with explicit repetition and evidence limits."""

    id: str = Field(min_length=1)
    phase: Literal["preparation", "processing", "finishing"]
    intent: str = Field(min_length=1)
    physical_operation: str = Field(min_length=1)
    object_ids: list[str] = Field(min_length=1)
    frequency: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    basis: Literal["planning", "workflow_hypothesis", "reviewed_source", "model_inference"]
    preconditions: list[str]
    postconditions: list[str]
    constraints: list[str]
    attended_range_s: tuple[float, float] | None = None

    @model_validator(mode="after")
    def provenance_and_range(self) -> PlannedOperation:
        """Reject blank provenance and invalid unmeasured time ranges."""
        if any(not item.strip() for item in self.source_refs + self.object_ids):
            raise ValueError("Operation references cannot be blank")
        if self.attended_range_s is not None and not 0 <= self.attended_range_s[0] <= self.attended_range_s[1]:
            raise ValueError("Attended range must be ordered and nonnegative")
        return self


class PlannedLink(StrictModel):
    """A proposed precedence or concurrent activity relationship."""

    source: str
    target: str
    relation: Literal["before", "during"]
    basis: Literal["planning", "reviewed_source", "model_inference"] = "planning"


class PlannedCapability(StrictModel):
    """A required capability mapped to operations and candidate equipment."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    operation_ids: list[str] = Field(min_length=1)
    candidate_equipment: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class AcceptanceCriterion(StrictModel):
    """An expected result requiring a defined test and evidence before acceptance."""

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    operation_ids: list[str] = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    verification_needed: str = Field(min_length=1)


class ProtocolSpecification(StrictModel):
    """Reusable protocol input with shared boundary and separate resource values."""

    schema_version: Literal[1] = 1
    protocol_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    functional_unit: str = Field(min_length=1)
    boundary: str = Field(min_length=1)
    operations: list[PlannedOperation] = Field(min_length=1)
    links: list[PlannedLink] = Field(default_factory=list)
    capabilities: list[PlannedCapability] = Field(min_length=1)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    resource_inputs: dict[str, EngineeringValue] = Field(default_factory=dict)
    engineering_inputs: EngineeringInputs = Field(default_factory=EngineeringInputs)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def integrity(self) -> ProtocolSpecification:
        """Validate references, full capability coverage and acyclic precedence."""
        ids = [operation.id for operation in self.operations]
        for values in (ids, [cap.id for cap in self.capabilities], [item.id for item in self.acceptance_criteria]):
            if len(values) != len(set(values)):
                raise ValueError("Operation, capability and criterion IDs must be unique")
        known = set(ids)
        covered: set[str] = set()
        for capability in self.capabilities:
            if not set(capability.operation_ids).issubset(known):
                raise ValueError("Capability references an unknown operation")
            covered.update(capability.operation_ids)
        if covered != known:
            raise ValueError("Every operation requires a capability mapping")
        for criterion in self.acceptance_criteria:
            if not set(criterion.operation_ids).issubset(known) or any(not ref.strip() for ref in criterion.source_refs):
                raise ValueError("Acceptance criterion requires valid operations and nonblank source references")
        adjacency: dict[str, list[str]] = {key: [] for key in ids}
        for link in self.links:
            if link.source not in known or link.target not in known or link.source == link.target:
                raise ValueError("Links require distinct existing operation IDs")
            if link.relation == "before":
                adjacency[link.source].append(link.target)
        active: set[str] = set()
        visited: set[str] = set()

        def visit(key: str) -> None:
            """Check precedence without turning a concurrent constraint into order."""
            if key in active:
                raise ValueError("Protocol precedence contains a cycle")
            if key in visited:
                return
            active.add(key)
            for successor in adjacency[key]:
                visit(successor)
            active.remove(key)
            visited.add(key)

        for key in ids:
            visit(key)
        # Validate resource units/ranges with the existing accounting contract.
        ProcessEvaluationInput(configuration_id=self.protocol_id, functional_unit=self.functional_unit,
                               boundary=self.boundary, inputs=self.resource_inputs)
        return self


def compile_specification(spec: ProtocolSpecification) -> tuple[ApparatusRequirements, ProcessEvaluationInput]:
    """Translate one validated protocol without any task-name branches or lookups."""
    spec = ProtocolSpecification.model_validate(spec.model_dump())
    requirements = ApparatusRequirements(
        protocol_operations=[Operation(id=op.id, intent=op.intent, physical_operation=op.physical_operation,
            object_ids=op.object_ids, source_action_ids=op.source_refs, preconditions=op.preconditions,
            postconditions=op.postconditions, constraints=op.constraints) for op in spec.operations],
        required_capabilities=[Capability(id=cap.id, name=cap.name, operation_ids=cap.operation_ids,
            rationale=cap.rationale + "; candidate equipment: " + "; ".join(cap.candidate_equipment)) for cap in spec.capabilities],
        unresolved_requirements=spec.limitations + [item.description + ": " + item.verification_needed for item in spec.acceptance_criteria],
        engineering_inputs=spec.engineering_inputs,
        note="Compiled from explicitly supplied protocol data. Source references may be planning documents; this does not establish video observations, verified acceptance or physical execution.",
    )
    process = ProcessEvaluationInput(configuration_id=spec.protocol_id, functional_unit=spec.functional_unit,
                                     boundary=spec.boundary, inputs=spec.resource_inputs, acceptance_verified=False)
    return requirements, process


def compile_protocol_file(input_path: Path, output: Path) -> dict[str, Any]:
    """Write graph, design handoff, accounting template/report and review checklist."""
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    raw = input_path.read_bytes()
    spec = ProtocolSpecification.model_validate_json(raw)
    requirements, process = compile_specification(spec)
    evaluated = evaluate_process(process)
    summary = {"schema_version": 1, "protocol_id": spec.protocol_id, "title": spec.title,
               "status": "candidate_plan_requires_review", "input_sha256": hashlib.sha256(raw).hexdigest(),
               "live_inference": False, "physical_validation": False,
               "accounting": evaluated.model_dump(), "acceptance_criteria": [item.model_dump() for item in spec.acceptance_criteria],
               "limitations": spec.limitations}
    graph = {"schema_version": 1, "protocol_id": spec.protocol_id,
             "operations": [op.model_dump() for op in spec.operations], "links": [link.model_dump() for link in spec.links]}
    lines = ["# " + spec.title, "", "**Explicitly supplied plan; acceptance and physical performance remain unverified.**", "",
             "Functional unit: " + spec.functional_unit, "", "Boundary: " + spec.boundary, "",
             "| Operation | Phase / frequency | Candidate equipment |", "| --- | --- | --- |"]

    def cell(text: str) -> str:
        """Keep source content from breaking report table structure."""
        return text.replace("|", "\\|").replace("\n", " ")

    for operation in spec.operations:
        equipment = sorted({item for cap in spec.capabilities if operation.id in cap.operation_ids for item in cap.candidate_equipment})
        lines.append(f"| {cell(operation.id + ': ' + operation.intent)} | {operation.phase} / {cell(operation.frequency)} | {cell('; '.join(equipment))} |")
    lines += ["", "## Resource results", "", "| Metric | Value | Basis |", "| --- | --- | --- |"]
    for key, metric in evaluated.metrics.items():
        value = metric.status if metric.value is None else f"{metric.value:g} {metric.unit}"
        lines.append(f"| {key} | {value} | {metric.basis} |")
    lines += ["", "## Acceptance checks", ""] + ["- " + criterion.description + ": " + criterion.verification_needed for criterion in spec.acceptance_criteria]
    lines += ["", "## Missing resource inputs", ""] + ["- " + key for key in sorted({key for metric in evaluated.metrics.values() for key in metric.missing_inputs})]
    lines += ["", "## Limitations", ""] + ["- " + limitation for limitation in spec.limitations]
    lines += ["", "No durations, resource quantities or acceptance outcomes are inferred from operation names or equipment. Preparation ranges are not summed; concurrency and task overlap require review.", ""]
    output.mkdir(parents=True)
    for name, payload in (("process-graph.json", graph), ("apparatus-requirements.json", requirements.model_dump()),
                          ("process-input.json", process.model_dump()), ("summary.json", summary)):
        write_json(output / name, payload)
    (output / "protocol-input.json").write_bytes(raw)
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary
