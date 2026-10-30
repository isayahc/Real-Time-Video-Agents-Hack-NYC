# SPDX-License-Identifier: MPL-2.0
"""Check operator decisions, evidence boundaries and the durable HTTP journey offline."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from protocol_pipeline import process_workspace as workspace
from protocol_pipeline.snapshots import atomic_json
from protocol_pipeline.web import create_app

HEADERS = {'X-Workbench-Request': '1'}


def measured_review() -> workspace.Review:
    """Create synthetic sourced inputs to test decisions, never physical evidence."""
    review, _ = workspace.example()
    review.steps_reviewed = True
    for name in ('baseline', 'candidate'):
        option = getattr(review, name)
        for q in option.values.values():
            if q.value is not None:
                q.kind, q.source = 'measured', 'Synthetic unit-test fixture; not real measurement'
        option.values['first_pass_count'] = workspace.Quantity(value=90, unit='count', kind='measured', source='Synthetic first-pass log')
    for gate in review.gates:
        gate.baseline = workspace.GateState(status='passed', source='Synthetic test assessment')
        gate.candidate = workspace.GateState(status='passed', source='Synthetic test assessment')
    return review


def test_metrics_keep_rework_unknowns_and_evidence_distinct() -> None:
    """Do not substitute acceptance for first-pass yield or elapsed time for labor."""
    review, _ = workspace.example()
    result = workspace.compare(review, True)
    metrics = result['metrics']['baseline']['metrics']
    assert metrics['accepted_outputs_per_hour']['value'] == pytest.approx(34.2)
    assert metrics['labor_s_per_accepted']['value'] == pytest.approx(9000 / 95)
    assert metrics['first_pass_yield']['value'] is None
    assert result['decision'] == 'insufficient_evidence'
    review.baseline.values['first_pass_count'] = workspace.Quantity(value=90, unit='count', kind='simulated', source='Synthetic simulation log')
    review.baseline.values['facility_cost'] = workspace.Quantity(unit='USD/batch')
    metrics = workspace.compare(review, True)['metrics']['baseline']['metrics']
    assert metrics['first_pass_yield']['value'] == .9
    assert metrics['first_pass_yield']['evidence'] == 'estimated + simulated'
    assert metrics['cost_usd_per_accepted']['value'] is None
    review.baseline.values['accepted_count'].value = 0
    review.baseline.values['first_pass_count'].value = 0
    result = workspace.compare(review, True)
    assert result['metrics']['baseline']['metrics']['labor_s_per_accepted']['value'] is None
    assert result['decision'] == 'insufficient_evidence'


def test_acceptance_and_mock_gates_override_better_arithmetic() -> None:
    """A faster candidate cannot bypass constraints or an illustrative evidence label."""
    review = measured_review()
    assert workspace.compare(review, False)['decision'] == 'supported_change'
    assert workspace.compare(review, True)['decision'] == 'insufficient_evidence'
    review.gates[1].candidate = workspace.GateState(status='failed', source='Synthetic unguarded pinch point')
    assert workspace.compare(review, False)['decision'] == 'retain_current_process'
    review.gates[1].candidate = workspace.GateState()
    assert workspace.compare(review, False)['decision'] == 'insufficient_evidence'
    review.gates[1].candidate = workspace.GateState(status='passed', source='Synthetic gate')
    review.candidate.values['labor_s'].value = 20000
    assert workspace.compare(review, False)['decision'] == 'insufficient_evidence'


def test_validation_rejects_unsourced_values_and_invalid_counts() -> None:
    """Require evidence, integer counts and first-pass <= eventual acceptance."""
    with pytest.raises(ValueError, match='source'):
        workspace.Quantity(value=0, unit='s', kind='estimated')
    with pytest.raises(ValueError, match='Unknown'):
        workspace.Quantity(value=0, unit='s')
    review, _ = workspace.example()
    payload = review.model_dump()
    payload['baseline']['values']['first_pass_count'] = {'value': 99, 'unit': 'count', 'kind': 'estimated', 'source': 'test'}
    with pytest.raises(ValueError, match='cannot exceed'):
        workspace.Review.model_validate(payload)


def test_full_http_journey_reopen_export_and_revision_conflict(tmp_path: Path) -> None:
    """Save corrected steps, compare, reopen after restart and verify portable hashes."""
    with TestClient(create_app(tmp_path)) as client:
        assert 'Is this task worth automating?' in client.get('/').text
        assert 'Make the next process change' in client.get('/process-review').text
        assert 'id="result-content"' in client.get('/video').text
        assert client.post('/api/processes').status_code == 403
        record = client.post('/api/processes', headers=HEADERS).json()
        url = f"/api/processes/{record['id']}"
        initial = deepcopy(record)
        record['data']['steps'][0] = 'Check wire stock and record its lot before setup'
        record['data']['steps_reviewed'] = True
        record = client.post(url + '/save', json={'revision': record['revision'], 'data': record['data']}, headers=HEADERS).json()
        assert record['revision'] == 2
        assert client.post(url + '/save', json={'revision': 1, 'data': initial['data']}, headers=HEADERS).status_code == 409
        record = client.post(url + f"/compare?revision={record['revision']}", headers=HEADERS).json()
        assert record['status'] == 'completed'
        assert record['result']['decision'] == 'insufficient_evidence'
        assert client.get('/api/runs').json() == []
        response = client.get(url + '/export')
        assert response.status_code == 200
        with ZipFile(io.BytesIO(response.content)) as z:
            manifest = json.loads(z.read('snapshot.json'))
            assert manifest['kind'] == 'process-comparison'
            for item in manifest['files']:
                assert hashlib.sha256(z.read(item['path'])).hexdigest() == item['sha256']
            assert 'MOCK' in z.read('decision.md').decode()
            assert 'baseline' in z.read('decision.md').decode()
            assert json.loads(z.read('review.json'))['sources']
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(url).json() == record
        assert len(client.get('/api/processes').json()) == 1
        assert len(list((tmp_path / 'processes' / record['id']).glob('v*/review.json'))) == 3
        saved = tmp_path / 'processes' / record['id'] / 'v000003/decision.md'
        saved.write_text('tampered')
        assert client.get(url + '/export').status_code == 409


def test_import_boundary_changes_and_failed_source(tmp_path: Path) -> None:
    """A new source/boundary cannot inherit old numerical claims or gate approvals."""
    with TestClient(create_app(tmp_path)) as client:
        record = client.post('/api/processes', headers=HEADERS).json()
        url = f"/api/processes/{record['id']}"
        record['data']['boundary'] = 'Changed batch boundary'
        record = client.post(url + '/save', json={'revision': record['revision'], 'data': record['data']}, headers=HEADERS).json()
        assert all(q['value'] is None for q in record['data']['baseline']['values'].values())
        source_id = 'a' * 32
        atomic_json(tmp_path / source_id / 'job.json', {'id': source_id, 'stage': 'failed', 'created_at': 1, 'events': [], 'error': 'Extraction failed'})
        response = client.post(url + '/import', json={'revision': record['revision'], 'run_id': source_id}, headers=HEADERS)
        assert response.status_code == 409 and 'Extraction failed' in response.text
        assert client.get(url).json() == record
        atomic_json(tmp_path / source_id / 'job.json', {'id': source_id, 'stage': 'completed', 'created_at': 1, 'events': []})
        atomic_json(tmp_path / source_id / 'extracted/extracted-protocol.json', {
            'title': 'Saved coil protocol', 'functional_unit': 'One accepted coil', 'boundary': 'Full coil batch',
            'operations': [{'physical_operation': 'Inspect the released coil'}]})
        record = client.post(url + '/import', json={'revision': record['revision'], 'run_id': source_id}, headers=HEADERS).json()
        assert record['data']['steps'] == ['Inspect the released coil']
        assert record['data']['functional_unit'] == 'One accepted coil'
        assert record['linked_run'] == source_id
        assert record['sources'][f'extraction/{source_id}']['sha256']
        record = client.post(url + '/import', json={'revision': record['revision'], 'text': 'Prepare stock\nWind coil\nInspect and record rejects'}, headers=HEADERS).json()
        assert len(record['data']['steps']) == 3
        assert 'linked_run' not in record
        assert record['result'] is None and not record['data']['steps_reviewed']


def test_failed_comparison_is_saved_exportable_and_retryable(tmp_path: Path, monkeypatch: Any) -> None:
    """Persist a real evaluator failure rather than showing stale successful results."""
    original = workspace.compare

    def fail(*args: Any) -> dict[str, Any]:
        """Simulate a deterministic evaluator rejecting unsupported input."""
        raise ValueError('Unsupported comparison fixture')

    with TestClient(create_app(tmp_path)) as client:
        record = client.post('/api/processes', headers=HEADERS).json()
        url = f"/api/processes/{record['id']}"
        monkeypatch.setattr(workspace, 'compare', fail)
        failed = client.post(url + f"/compare?revision={record['revision']}", headers=HEADERS).json()
        assert failed['status'] == 'failed' and failed['result'] is None
        assert 'Unsupported comparison fixture' in failed['error']
        assert client.get(url).json() == failed
        assert client.get(url + '/export').status_code == 200
        monkeypatch.setattr(workspace, 'compare', original)
        retry = client.post(url + f"/compare?revision={failed['revision']}", headers=HEADERS).json()
        assert retry['status'] == 'completed' and retry['error'] is None
