# SPDX-License-Identifier: MPL-2.0
"""Coverage, provenance and non-double-counted labor at measurement intake."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from protocol_pipeline.alternatives import AlternativeSet
from protocol_pipeline.pipeline import sha256
from protocol_pipeline.workflow_measurements import WorkflowBatch, compare_batch, reconcile_batch

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def collection(tmp_path: Path) -> tuple[dict, dict, Path, AlternativeSet]:
    """Synthetic timing spans, not measurements of an actual coil workflow."""
    baseline = {'baseline_id': 'synthetic', 'steps': [
        {'id': 'setup', 'frequency': 'per_batch'}, {'id': 'wind', 'frequency': 'per_attempt'},
        {'id': 'inspect', 'frequency': 'per_accepted'}, {'id': 'rework', 'frequency': 'per_rework'}]}
    path = tmp_path/'baseline.json';path.write_text(json.dumps(baseline))
    alternatives = AlternativeSet.model_validate_json((ROOT/'examples/apparatus-alternatives/evidence-input.json').read_text())
    process = alternatives.options[0].option.process.model_dump()
    process['inputs'].pop('labor_s')
    for key, value in [('elapsed_s', 30), ('accepted_count', 2), ('attempted_count', 2)]:
        process['inputs'][key].update(value=value, basis='assumed', source='Synthetic fixture')

    def occurrence(start: float, end: float, operator: str) -> dict:
        """Create overlapping synthetic operator intervals for union accounting."""
        return {'start_s': start, 'end_s': end, 'evidence_refs': ['synthetic'],
                'attendance': [{'operator_id': operator, 'start_s': start, 'end_s': end,
                                'basis': 'assumed', 'source': 'Synthetic fixture'}]}

    batch = {'baseline_id': 'synthetic', 'baseline_sha256': sha256(path), 'evidence_kind': 'illustrative',
             'conditions': 'Synthetic overlap scenario', 'evidence_refs': ['synthetic'], 'process': process,
             'attendance_complete': True, 'attendance_source': 'Synthetic complete coverage', 'steps': [
                 {'step_id': 'setup', 'status': 'observed', 'rationale': 'synthetic', 'evidence_refs': ['synthetic'],
                  'occurrences': [occurrence(0, 10, 'a')]},
                 {'step_id': 'wind', 'status': 'observed', 'rationale': 'synthetic', 'evidence_refs': ['synthetic'],
                  'occurrences': [occurrence(5, 15, 'a'), occurrence(15, 25, 'a')]},
                 {'step_id': 'inspect', 'status': 'observed', 'rationale': 'synthetic', 'evidence_refs': ['synthetic'],
                  'occurrences': [occurrence(10, 15, 'b'), occurrence(25, 30, 'a')]},
                 {'step_id': 'rework', 'status': 'not_applicable', 'rationale': 'No rework in synthetic batch',
                  'evidence_refs': ['synthetic']} ]}
    return batch, baseline, path, alternatives


def test_union_labor_keeps_batch_elapsed_independent(collection: tuple) -> None:
    """One operator's overlap counts once; another operator adds labor, not elapsed."""
    raw, baseline, path, alternatives = collection
    original = deepcopy(raw)
    audit = reconcile_batch(WorkflowBatch.model_validate(raw), baseline, path)
    assert audit['status'] == 'coverage_reconciled'
    metrics = audit['evaluation']['metrics']
    assert metrics['labor_s_per_accepted']['value'] == 17.5  # 30 s operator a + 5 s operator b
    assert metrics['accepted_outputs_per_hour']['value'] == 240  # 2 / 30 s, not summed spans
    assert raw == original
    before = alternatives.model_dump()
    comparison = compare_batch(alternatives, 'manual', audit)
    assert comparison['overall_recommendation'] == 'undetermined'
    assert alternatives.model_dump() == before
    assert comparison['physical_validation'] is False


@pytest.mark.parametrize('problem', ['missing_step', 'missing_attempt', 'missing_acceptance', 'attendance_unconfirmed', 'unknown_count'])
def test_incomplete_coverage_cannot_become_partial_zero_labor(collection: tuple, problem: str) -> None:
    """Keep total labor unknown until full workflow/frequency coverage is reconciled."""
    raw, baseline, path, _ = collection
    if problem == 'missing_step':
        raw['steps'][3].update(status='unobserved', evidence_refs=[])
    elif problem == 'missing_attempt':
        raw['steps'][1]['occurrences'].pop()
    elif problem == 'missing_acceptance':
        raw['steps'][2]['occurrences'].pop()
    elif problem == 'attendance_unconfirmed':
        raw['attendance_complete'] = False
    else:
        raw['process']['inputs']['attempted_count'].update(value=None, basis='unknown', source=None)
    audit = reconcile_batch(WorkflowBatch.model_validate(raw), baseline, path)
    assert audit['blockers']
    assert audit['evaluation']['metrics']['labor_s_per_accepted']['value'] is None
    assert audit['process']['attendance'] is None


def test_wrong_baseline_boundary_and_timeline_fail(collection: tuple) -> None:
    """Do not attach a different source, partial boundary or out-of-batch event."""
    raw, baseline, path, alternatives = collection
    batch = WorkflowBatch.model_validate(raw)
    path.write_text(path.read_text()+' ')
    with pytest.raises(ValueError, match='hash mismatch'):
        reconcile_batch(batch, baseline, path)
    raw['baseline_sha256'] = sha256(path)
    raw['process']['boundary'] = 'winding only'
    audit = reconcile_batch(WorkflowBatch.model_validate(raw), baseline, path)
    with pytest.raises(ValueError, match='boundary'):
        compare_batch(alternatives, 'manual', audit)
    raw['steps'][0]['occurrences'][0]['end_s'] = 31
    with pytest.raises(ValueError, match='elapsed boundary'):
        reconcile_batch(WorkflowBatch.model_validate(raw), baseline, path)


def test_evidence_and_exclusive_labor_contract(collection: tuple) -> None:
    """Reject invented physical measurements and duplicate aggregate attendance."""
    raw, _, _, _ = collection
    for mutation in [
        lambda value: value.update(evidence_kind='physical'),
        lambda value: value['process'].update(acceptance_verified=True, acceptance_source='synthetic'),
        lambda value: value['steps'][3].update(evidence_refs=[]),
        lambda value: value['process']['inputs'].update(labor_s={'value': 35, 'unit': 'operator-s', 'basis': 'assumed', 'source': 'synthetic'}),
        lambda value: value['steps'].append(deepcopy(value['steps'][0])),
    ]:
        changed = deepcopy(raw);mutation(changed)
        with pytest.raises(ValueError):
            WorkflowBatch.model_validate(changed)


def test_physical_intake_does_not_fill_missing_economics(collection: tuple) -> None:
    """Even sourced attendance cannot manufacture capital, rates, yield equivalence."""
    raw, baseline, path, alternatives = collection
    raw['evidence_kind'] = 'physical'
    for item in raw['process']['inputs'].values():
        if item['value'] is not None:item['basis'] = 'measured'
    for step in raw['steps']:
        for occurrence in step.get('occurrences', []):
            for item in occurrence['attendance']:item['basis'] = 'measured'
    audit = reconcile_batch(WorkflowBatch.model_validate(raw), baseline, path)
    comparison = compare_batch(alternatives, 'manual', audit)
    for pair in comparison['scenarios']['current-evidence']['comparisons']:
        assert pair['result']['decision'] == 'undetermined'
    assert audit['evaluation']['metrics']['cost_usd_per_accepted']['value'] is None


def test_template_cli_offline_preserves_original_and_unknowns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create/re-audit real collection templates without network access or overwrites."""
    import socket
    import sys
    from scripts.evaluate_workflow_batch import main

    def no_network(*args: object, **kwargs: object) -> None:
        """Reject any accidental connection during a measurement-only operation."""
        raise AssertionError('Network prohibited')

    monkeypatch.setattr(socket.socket, 'connect', no_network)
    monkeypatch.setattr(socket, 'create_connection', no_network)
    output = tmp_path/'template'
    argv = ['evaluate_workflow_batch.py', '--baseline', str(ROOT/'benchmarks/coil-winding/baseline.json'),
            '--alternatives', str(ROOT/'examples/apparatus-alternatives/illustrative-input.json'),
            '--option', 'manual', '--output', str(output), '--template']
    monkeypatch.setattr(sys, 'argv', argv)
    main()
    original = (output/'batch.json').read_bytes()
    batch = WorkflowBatch.model_validate_json(original)
    assert len(batch.steps) == 15
    assert all(step.status == 'unobserved' for step in batch.steps)
    assert all(item.value is None for item in batch.process.inputs.values())
    with pytest.raises(FileExistsError):main()
    assert (output/'batch.json').read_bytes() == original
    comparison = json.loads((output/'updated-alternatives.json').read_text())
    assert comparison['equivalence_verified'] is False
    argv[argv.index(str(output))] = str(tmp_path/'audit')
    argv[-1:] = ['--input', str(output/'batch.json')]
    main()
    assert json.loads((tmp_path/'audit/coverage.json').read_text())['status'] == 'needs_measurements'
