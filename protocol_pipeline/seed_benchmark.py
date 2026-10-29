# SPDX-License-Identifier: MPL-2.0
"""Validate reproducible SO-101 trial inputs without claiming trial execution."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from .models import StrictModel

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Index = Annotated[int, Field(strict=True, ge=0)]
EvidenceKind = Literal["assumption", "simulation", "physical"]
FailureKind = Literal[
    "pickup_miss", "multiple_seeds", "dropped_seed", "wrong_cell",
    "outside_tolerance", "damaged_seed", "collision", "timeout",
    "reset_failed", "invalid_observation", "execution_error",
]
FAILURES = list(FailureKind.__args__)


class Contract(StrictModel):
    """Reject coercions and unknown fields in experimental inputs."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Quantity(Contract):
    """Nonnegative quantity with explicit provenance; unknown is never zero."""

    value: float | None
    unit: Literal["mm", "s", "count"]
    basis: Literal["assumption", "measurement", "definition", "unknown"]
    source: Text

    @model_validator(mode="after")
    def provenance(self) -> Self:
        """Keep missing measurements null and counts integral."""
        if (self.value is None) != (self.basis == "unknown"):
            raise ValueError("Only unknown quantities have null values")
        if self.value is not None:
            if self.value < 0 or (self.unit == "count" and not self.value.is_integer()):
                raise ValueError("Quantities must be nonnegative; counts must be integral")
        return self


class Identity(Contract):
    """Versioned artifact identity, including honest definition-only placeholders."""

    id: Text
    version: Text
    path: Text
    sha256: Digest
    availability: Literal["definition_only", "materialized"]


class Components(Contract):
    """Inputs held constant except tooling in a tooling-only comparison."""

    robot: Identity
    tool: Identity
    policy: Identity
    evaluator: Identity
    environment: Identity
    calibration: Identity
    cameras: Identity


class Geometry(Contract):
    """Rectangular tray grid in millimetres, indexed from zero at cell (0, 0)."""

    rows: Quantity
    columns: Quantity
    pitch_x_mm: Quantity
    pitch_y_mm: Quantity
    cell_opening_mm: Quantity
    cell_depth_mm: Quantity
    seed_diameter_mm: Quantity
    frame: Literal["tray_cell_0_0_center_z_rim_x_columns_y_rows_z_up"]

    @model_validator(mode="after")
    def dimensions(self) -> Self:
        """Reject invalid units, dimensions and overlapping circular openings."""
        for name in type(self).model_fields:
            if name == "frame":
                continue
            quantity = getattr(self, name)
            unit = "count" if name in ("rows", "columns") else "mm"
            if quantity.unit != unit or (quantity.value is not None and quantity.value <= 0):
                raise ValueError(f"{name} requires positive {unit}")
        if self.rows.value is None or self.columns.value is None:
            raise ValueError("Tray row and column counts must be declared")
        opening = self.cell_opening_mm.value
        for pitch in (self.pitch_x_mm.value, self.pitch_y_mm.value):
            if opening is not None and pitch is not None and opening > pitch:
                raise ValueError("Cell opening cannot exceed grid pitch")
        return self


class Acceptance(Contract):
    """An evidence-specific acceptance rule; physical tolerances may be unknown."""

    evidence_kind: Literal["simulation", "physical"]
    geometry: Geometry
    seeds_per_cell: Quantity
    radial_tolerance_mm: Quantity
    settling_time_s: Quantity
    timeout_s: Quantity
    damage_rule: Literal["no_damage_flag", "no_visible_crack_or_crush_pre_post"]
    observation: Literal["simulator_state", "calibrated_pre_post_images"]
    placement_rule: Literal["whole_seed_inside_target_cell_below_rim_after_settle"]
    damage_limitations: Text

    @model_validator(mode="after")
    def acceptance_units_and_domain(self) -> Self:
        """Enforce seed count, plausible tolerances and separate observation domains."""
        for name, unit in (("seeds_per_cell", "count"), ("radial_tolerance_mm", "mm"),
                           ("settling_time_s", "s"), ("timeout_s", "s")):
            q = getattr(self, name)
            if q.unit != unit:
                raise ValueError(f"{name} must use {unit}")
        if self.seeds_per_cell.value != 1:
            raise ValueError("This benchmark requires exactly one seed per target cell")
        for q in (self.settling_time_s, self.timeout_s):
            if q.value is not None and q.value <= 0:
                raise ValueError("Timing limits must be positive")
        if self.timeout_s.value is not None and self.settling_time_s.value is not None:
            if self.timeout_s.value <= self.settling_time_s.value:
                raise ValueError("Timeout must exceed settling time")
        expected = (("no_damage_flag", "simulator_state") if self.evidence_kind == "simulation"
                    else ("no_visible_crack_or_crush_pre_post", "calibrated_pre_post_images"))
        if (self.damage_rule, self.observation) != expected:
            raise ValueError("Acceptance observation/damage rule belongs to another evidence kind")
        diameter = self.geometry.seed_diameter_mm.value
        opening = self.geometry.cell_opening_mm.value
        tolerance = self.radial_tolerance_mm.value
        if None not in (diameter, opening, tolerance):
            if 2 * tolerance + diameter > opening:
                raise ValueError("Radial tolerance must keep the entire seed inside the opening")
        return self


class Boundaries(Contract):
    """One attempted placement per timed cycle, followed by separately timed reset."""

    cycle_start: Literal["ready_before_pickup"]
    cycle_end: Literal["acceptance_decided_and_robot_home_or_failure_stop"]
    reset_start: Literal["cycle_end"]
    reset_end: Literal["initial_conditions_verified"]
    reset_in_cycle: Literal[False]
    retry_policy: Literal["no_retry_within_attempt"]
    reset_failure_policy: Literal["retain_failure_and_abort_remaining_trials"]


class InitialConditions(Contract):
    """Versioned procedures supplement the hashed environment and calibration."""

    seed_presentation: Text
    tray_preparation: Text
    robot_start: Text
    reset_procedure: Text
    verification: Text
    randomization: Text


class Benchmark(Contract):
    """Frozen task and separate simulation/physical acceptance definitions."""

    id: Text
    version: Text
    seed_type: Text
    seed_lot: Text
    simulation: Acceptance
    physical: Acceptance
    boundaries: Boundaries
    initial_conditions: InitialConditions
    failure_categories: list[FailureKind]
    numerical_protocol_source: Text
    limitations: list[Text] = Field(min_length=1)

    @model_validator(mode="after")
    def domains(self) -> Self:
        """Require both evidence domains and the complete failure vocabulary."""
        if self.simulation.evidence_kind != "simulation" or self.physical.evidence_kind != "physical":
            raise ValueError("Simulation and physical acceptance must remain separate")
        if sorted(self.failure_categories) != sorted(FAILURES):
            raise ValueError("Failure categories must contain each required category exactly once")
        for key in ("rows", "columns"):
            if getattr(self.simulation.geometry, key).value != getattr(self.physical.geometry, key).value:
                raise ValueError("Simulation and physical tray topology must match")
        return self


class Target(Contract):
    """Zero-based target cell in the declared row/column frame."""

    row: Index
    column: Index


class TrialManifest(Contract):
    """Inputs for matched repeated trials, never a report of executed outcomes."""

    schema_version: Literal[1]
    experiment_id: Text
    evidence_kind: EvidenceKind
    benchmark: Benchmark
    components: Components
    boundaries: Boundaries
    trial_seeds: list[Index] = Field(min_length=1)
    targets: list[Target] = Field(min_length=1)
    execution_requested: bool

    @model_validator(mode="after")
    def coherence(self) -> Self:
        """Reject incomparable boundaries, duplicated trials and invalid target cells."""
        if self.boundaries != self.benchmark.boundaries:
            raise ValueError("Trial and benchmark boundaries must match")
        if len(set(self.trial_seeds)) != len(self.trial_seeds):
            raise ValueError("Trial seeds must be unique")
        cells = [(cell.row, cell.column) for cell in self.targets]
        if len(set(cells)) != len(cells):
            raise ValueError("Target cells must be unique")
        geometry = self.benchmark.simulation.geometry
        if any(row >= geometry.rows.value or col >= geometry.columns.value for row, col in cells):
            raise ValueError("Target cell is outside tray geometry")
        if self.execution_requested and self.execution_blockers():
            raise ValueError("Execution blocked: " + "; ".join(self.execution_blockers()))
        return self

    def execution_blockers(self) -> list[str]:
        """List missing inputs without silently upgrading a valid plan to an experiment."""
        blockers = []
        if self.evidence_kind == "assumption":
            blockers.append("assumption manifests cannot execute trials")
        for name in Components.model_fields:
            if getattr(self.components, name).availability == "definition_only":
                blockers.append(f"{name} is definition_only")
        if self.evidence_kind in ("simulation", "physical"):
            acceptance = getattr(self.benchmark, self.evidence_kind)
            quantities = {name: getattr(acceptance, name) for name in
                          ("seeds_per_cell", "radial_tolerance_mm", "settling_time_s", "timeout_s")}
            quantities.update({name: getattr(acceptance.geometry, name) for name in
                               Geometry.model_fields if name != "frame"})
            for name, q in quantities.items():
                if q.basis == "unknown" or (self.evidence_kind == "physical" and q.basis == "assumption"):
                    blockers.append(f"{self.evidence_kind}.{name} is {q.basis}")
            if self.evidence_kind == "physical" and self.benchmark.seed_lot == "unknown":
                blockers.append("physical seed lot is unknown")
        return blockers


def comparison_key(manifest: TrialManifest) -> str:
    """Hash all controlled inputs; only experiment ID and tool identity may change."""
    payload = TrialManifest.model_validate(manifest.model_dump()).model_dump()
    del payload["experiment_id"]
    del payload["components"]["tool"]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def require_matched_trials(baseline: TrialManifest, candidate: TrialManifest) -> None:
    """Reject changes to task, seeds, policy, evidence domain or timing boundaries."""
    if comparison_key(baseline) != comparison_key(candidate):
        raise ValueError("Incompatible tooling comparison: controlled trial inputs differ")


def validate_manifest(path: Path) -> dict[str, Any]:
    """Validate a manifest and verify every referenced artifact's exact local bytes."""
    raw = path.read_bytes()
    manifest = TrialManifest.model_validate_json(raw)
    root = path.resolve().parent
    verified: dict[str, str] = {}
    for role in Components.model_fields:
        identity = getattr(manifest.components, role)
        artifact = (root / identity.path).resolve()
        if not artifact.is_relative_to(root):
            raise ValueError(f"{role} artifact must remain inside manifest directory")
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual != identity.sha256:
            raise ValueError(f"{role} artifact hash mismatch")
        verified[role] = actual
    return {"schema_version": 1, "status": "contract_valid", "experiment_id": manifest.experiment_id,
            "manifest_sha256": hashlib.sha256(raw).hexdigest(), "comparison_key": comparison_key(manifest),
            "evidence_kind": manifest.evidence_kind, "artifacts_verified": verified,
            "execution_blockers": manifest.execution_blockers(), "trial_execution_performed": False,
            "provider_execution_verified": False, "physical_performance_established": False}


def main() -> None:
    """Validate local inputs and optionally preserve a machine-readable check report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = validate_manifest(args.manifest)
        rendered = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as stream:
                stream.write(rendered)
        print(rendered, end="")
    except (ValueError, OSError) as error:
        parser.exit(1, f"Seed benchmark validation failed: {error}\n")


if __name__ == "__main__":
    main()
