# SPDX-License-Identifier: MPL-2.0
"""Reconcile full-workflow batch coverage before reusing the existing evaluators."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .alternatives import AlternativeSet, evaluate_alternatives
from .evaluation import AttendanceInterval, ProcessEvaluationInput, evaluate_process
from .iteration import OutcomeRequest
from .models import StrictModel
from .pipeline import sha256


class StepOccurrence(StrictModel):
    """One sourced operation interval; attendance may overlap other operations."""

    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    evidence_refs: list[str] = Field(min_length=1)
    attendance: list[AttendanceInterval]

    @model_validator(mode='after')
    def valid_interval(self) -> StepOccurrence:
        """Keep attended intervals within the observed operation interval."""
        if self.end_s < self.start_s:
            raise ValueError('Operation ends before it starts')
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError('Occurrence evidence references cannot be blank')
        if any(item.start_s < self.start_s or item.end_s > self.end_s for item in self.attendance):
            raise ValueError('Attendance lies outside its operation interval')
        return self


class StepCoverage(StrictModel):
    """Explicitly distinguish observed, not-applicable and unobserved workflow steps."""

    step_id: str = Field(min_length=1)
    status: Literal['observed', 'not_applicable', 'unobserved']
    rationale: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    occurrences: list[StepOccurrence] = Field(default_factory=list)

    @model_validator(mode='after')
    def evidenced_status(self) -> StepCoverage:
        """A zero-event disposition needs evidence rather than a silent zero."""
        if self.status != 'unobserved' and not self.evidence_refs:
            raise ValueError('Observed/not-applicable coverage requires evidence')
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError('Coverage evidence references cannot be blank')
        if self.status != 'observed' and self.occurrences:
            raise ValueError('Only observed coverage may contain occurrences')
        return self


class WorkflowBatch(StrictModel):
    """A collection record, not an automatic assertion of full-process evidence."""

    schema_version: Literal[1] = 1
    baseline_id: str
    baseline_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    evidence_kind: Literal['physical', 'simulation', 'illustrative']
    conditions: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    process: ProcessEvaluationInput
    steps: list[StepCoverage] = Field(min_length=1)
    attendance_complete: bool = False
    attendance_source: str | None = None

    @model_validator(mode='after')
    def exclusive_attendance(self) -> WorkflowBatch:
        """Require event-based labor and an explicit complete-coverage attestation."""
        if 'labor_s' in self.process.inputs or self.process.attendance is not None:
            raise ValueError('Workflow intake derives labor from occurrences; remove aggregate labor/attendance')
        if len({step.step_id for step in self.steps}) != len(self.steps):
            raise ValueError('Workflow step IDs must be unique')
        if self.attendance_complete and not (self.attendance_source or '').strip():
            raise ValueError('Complete attendance requires a source covering all operators and the full batch')
        if self.evidence_kind == 'illustrative' and self.process.acceptance_verified:
            raise ValueError('Illustrative batches cannot verify physical output acceptance')
        OutcomeRequest(process=self.process, evidence_kind=self.evidence_kind,
                       conditions=self.conditions, evidence_refs=self.evidence_refs)
        if self.evidence_kind != 'illustrative' and any(
            event.basis != 'measured' for step in self.steps
            for occurrence in step.occurrences for event in occurrence.attendance
        ):
            raise ValueError('Physical/simulation attendance must be measured, not assumed')
        return self


def reconcile_batch(batch: WorkflowBatch, baseline: dict, baseline_path: Path) -> dict:
    """Audit coverage/frequency and calculate labor only after complete reconciliation.

    Elapsed batch time is supplied independently, never summed from concurrent
    steps. Evidence references are user assertions, not independently verified here.
    """
    batch = WorkflowBatch.model_validate(batch.model_dump())
    if baseline != json.loads(baseline_path.read_text(encoding='utf-8')):
        raise ValueError('Baseline content does not match the hashed source file')
    if batch.baseline_id != baseline['baseline_id'] or batch.baseline_sha256 != sha256(baseline_path):
        raise ValueError('Batch baseline identity/hash mismatch')
    expected = {step['id']: step for step in baseline['steps']}
    if {step.step_id for step in batch.steps} != set(expected):
        raise ValueError('Coverage must include every baseline step exactly once, with no unknown IDs')
    blockers = []
    elapsed = batch.process.inputs.get('elapsed_s')
    if elapsed is None or elapsed.value is None:
        blockers.append('Batch elapsed time is unknown; full interval coverage cannot be checked')
    attendance = []
    for step in batch.steps:
        if step.status == 'unobserved':
            blockers.append(f'{step.step_id}: applicability/occurrences remain unobserved')
        if step.status != 'observed':
            continue
        frequency = expected[step.step_id]['frequency']
        if frequency not in {'per_batch', 'per_attempt', 'per_accepted', 'per_rework', 'per_maintenance_event'}:
            blockers.append(f'{step.step_id}: unsupported frequency {frequency}; reconcile manually')
        count_key = {'per_attempt': 'attempted_count', 'per_accepted': 'accepted_count'}.get(frequency)
        required = 1 if frequency == 'per_batch' else None
        if count_key:
            quantity = batch.process.inputs.get(count_key)
            required = quantity.value if quantity else None
            if required is None:
                blockers.append(f'{step.step_id}: {count_key} needed to reconcile occurrences')
        if required is not None and len(step.occurrences) != required:
            blockers.append(f'{step.step_id}: expected {required:g} occurrences, got {len(step.occurrences)}')
        for occurrence in step.occurrences:
            if elapsed and elapsed.value is not None and occurrence.end_s > elapsed.value:
                raise ValueError(f'{step.step_id}: operation exceeds batch elapsed boundary')
            attendance.extend(occurrence.attendance)
    if not batch.attendance_complete:
        blockers.append('Complete operator attendance has not been confirmed')
    payload = batch.process.model_dump()
    if not blockers:
        payload.update(attendance=[event.model_dump() for event in attendance],
                       attendance_source=batch.attendance_source)
    process = ProcessEvaluationInput.model_validate(payload)
    report = evaluate_process(process)
    return {'schema_version': 1, 'status': 'coverage_reconciled' if not blockers else 'needs_measurements',
            'evidence_kind': batch.evidence_kind, 'blockers': blockers,
            'input_snapshot': batch.model_dump(), 'process': process.model_dump(),
            'evaluation': report.model_dump(), 'physical_validation': False,
            'limitations': ['Coverage reconciliation is not independent verification of supplied evidence.',
                            'Unknown applicability does not mean not applicable or zero labor.',
                            'Labor unions overlapping intervals per operator; elapsed time is independently supplied.',
                            'Setup/trial/rework/maintenance labor must appear once; do not add old planning allowances.',
                            'Simulation and illustrative data do not demonstrate physical performance.']}


def compare_batch(data: AlternativeSet, option_id: str, audit: dict) -> dict:
    """Apply one reconciled batch to a detached alternative set with unchanged gates."""
    payload = data.model_dump()
    matches = [option for option in payload['options'] if option['id'] == option_id]
    if len(matches) != 1:
        raise ValueError('Unknown alternative ID')
    original, updated = matches[0]['option']['process'], audit['process']
    for key in ('configuration_id', 'functional_unit', 'boundary'):
        if original[key] != updated[key]:
            raise ValueError(f'Measurement {key} must match the selected alternative')
    matches[0]['option']['process'] = updated
    # Nonphysical inputs must not inherit historical physical equivalence claims.
    if audit['evidence_kind'] != 'physical' or audit['blockers']:
        payload.update(equivalence_verified=False, equivalence_source=None)
        for option in payload['options']:
            option['option']['process'].update(acceptance_verified=False, acceptance_source=None)
    return evaluate_alternatives(AlternativeSet.model_validate(payload))
