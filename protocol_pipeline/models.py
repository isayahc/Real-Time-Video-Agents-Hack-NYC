"""Typed contracts separating annotations, video inference and engineering inputs."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Reject unknown fields and nonfinite numbers at every contract boundary."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AnnotatedObject(StrictModel):
    """A source object position on the reference frame, not a tracked trajectory."""

    id: int
    description: str = Field(min_length=1)
    position: tuple[float, float]

    @model_validator(mode="after")
    def normalized_position(self) -> AnnotatedObject:
        """Require both image coordinates to lie in the normalized range."""
        if not all(0 <= v <= 1 for v in self.position):
            raise ValueError("Object position must be normalized to [0, 1].")
        return self


class Annotation(StrictModel):
    """Normalize supported CREOLab fields while retaining raw bytes separately."""

    video_id: str = Field(min_length=1)
    objects: list[AnnotatedObject]
    caption: str
    reference_procedure: str | list[str] | None = None
    ground_truth_text: str


class Frame(StrictModel):
    """A decoded source frame with actual presentation timestamp and file hash."""

    id: str
    path: str
    timestamp_s: float = Field(ge=0)
    source_pts_s: float
    source_frame_index: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class EvidenceClaim(StrictModel):
    """A model interpretation linked to actual sampled video frames."""

    evidence_frame_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    interpretation: str = Field(min_length=1)


class VisualObject(EvidenceClaim):
    """An inferred object identity; this is not a YOLO track or annotation ID."""

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)


class Action(EvidenceClaim):
    """An inferred temporal action with grounded object references."""

    id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    object_ids: list[str] = Field(min_length=1)
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)

    @model_validator(mode="after")
    def ordered_interval(self) -> Action:
        """Reject reversed temporal intervals."""
        if self.end_s < self.start_s:
            raise ValueError("Action ends before it starts.")
        return self


class StateChange(EvidenceClaim):
    """An inferred before/after change, separate from physical measurements."""

    id: str = Field(min_length=1)
    object_id: str
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)
    action_ids: list[str] = Field(min_length=1)


class ObservationGraph(StrictModel):
    """Video-derived inference only; ground truth is stored outside this graph."""

    objects: list[VisualObject]
    actions: list[Action]
    state_changes: list[StateChange]
    limitations: list[str]


class Operation(StrictModel):
    """An embodiment-independent operation derived from visual action evidence."""

    id: str
    intent: str = Field(min_length=1)
    physical_operation: str = Field(min_length=1)
    object_ids: list[str] = Field(min_length=1)
    source_action_ids: list[str] = Field(min_length=1)
    preconditions: list[str]
    postconditions: list[str]
    constraints: list[str]


class Capability(StrictModel):
    """An apparatus requirement mapped to source operations."""

    id: str
    name: str = Field(min_length=1)
    operation_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class PreparationCandidate(StrictModel):
    """A hypothesized prerequisite outside the observed clip, not a new fact."""

    id: str
    description: str = Field(min_length=1)
    frequency: Literal["per_batch", "per_unit", "initial_deployment", "unknown"]
    reason: str = Field(min_length=1)
    verification_needed: str = Field(min_length=1)


class ProtocolPlan(StrictModel):
    """Derived protocol/capabilities plus separately labeled preparation hypotheses."""

    operations: list[Operation]
    required_capabilities: list[Capability]
    preprocessing_candidates: list[PreparationCandidate]
    unresolved_requirements: list[str]
    limitations: list[str]


class EngineeringValue(StrictModel):
    """An explicitly supplied measurement, specification or planning assumption."""

    value: float | None = None
    unit: str = Field(min_length=1)
    basis: Literal["unknown", "measured", "supplier_specification", "assumed"]
    source: str | None = None

    @model_validator(mode="after")
    def evidence_required(self) -> EngineeringValue:
        """Never turn an unknown into zero or accept an unsourced numerical claim."""
        if self.basis == "unknown" and self.value is not None:
            raise ValueError("Unknown engineering values must remain null.")
        if self.basis != "unknown" and (self.value is None or not self.source):
            raise ValueError("Known/assumed values require a number and a source description.")
        return self


class EngineeringInputs(StrictModel):
    """Supplementary inputs kept separate from original annotations and inference."""

    parameters: dict[str, EngineeringValue] = Field(default_factory=dict)
    costs: dict[str, EngineeringValue] = Field(default_factory=dict)
    labor: dict[str, EngineeringValue] = Field(default_factory=dict)
    power: dict[str, EngineeringValue] = Field(default_factory=dict)
    byproducts: dict[str, EngineeringValue] = Field(default_factory=dict)
