"""Exercise upload → real decoding → replay extraction → compiler → HTTP results."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from protocol_pipeline.extraction import ReplayProvider
from protocol_pipeline.web import create_app

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {'X-Workbench-Request': '1'}
PARAMS = {'filename': 'fixture.mp4', 'model': 'fixture-compiler', 'vision_model': 'fixture-vision', 'frame_count': 2}


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is required for frontend tests')
def test_frontend_model_workflow() -> None:
    """Run the shipped JavaScript through preset, override and persistence flows."""
    subprocess.run(['node', '--test', str(ROOT / 'tests/test_web_frontend.cjs')],
                   check=True, capture_output=True, text=True, timeout=30)


@pytest.fixture(scope='module')
def video(tmp_path_factory: Any) -> bytes:
    """Generate a real two-second video; its semantics are explicitly synthetic."""
    path = tmp_path_factory.mktemp('media') / 'fixture.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=5',
                    '-t', '2', '-pix_fmt', 'yuv420p', str(path)], check=True, capture_output=True)
    return path.read_bytes()


def replay_file(path: Path) -> Path:
    """Prepare grounded synthetic responses for both video extraction stages."""
    spec = json.loads((ROOT / 'examples/extraction/recorded-response.json').read_text())['responses'][0]['response']
    op = spec['operations'][3]
    op.update(object_ids=['tube'], source_refs=['action:transfer'])
    spec['operations'] = [op]
    spec['links'] = []
    cap = spec['capabilities'][3]
    cap['operation_ids'] = [op['id']]
    spec['capabilities'] = [cap]
    criterion = spec['acceptance_criteria'][1]
    criterion.update(operation_ids=[op['id']], source_refs=['hypothesis:requires inspection'])
    spec['acceptance_criteria'] = [criterion]
    evidence = {'evidence_frame_ids': ['frame_0000', 'frame_0001'], 'confidence': .5, 'interpretation': 'Synthetic test'}
    graph = {'objects': [{**evidence, 'id': 'tube', 'description': 'synthetic tube'}],
             'actions': [{**evidence, 'id': 'transfer', 'action': 'transfer', 'object_ids': ['tube'], 'start_s': 0, 'end_s': 1.8}],
             'state_changes': [], 'limitations': ['Synthetic replay, not live model interpretation']}
    path.write_text(json.dumps({'responses': [{'contract': 'ObservationGraph', 'response': graph},
                                             {'contract': 'ProtocolSpecification', 'response': spec}]}))
    return path


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Serve the real application with only inference replaced by labeled replay."""
    replay = replay_file(tmp_path / 'replay.json')
    with TestClient(create_app(tmp_path / 'runs', lambda: ReplayProvider(replay))) as browser:
        yield browser


def wait_job(client: TestClient, run_id: str) -> dict[str, Any]:
    """Wait for a bounded worker completion, failing if execution stalls."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = client.get(f'/api/runs/{run_id}').json()
        if job['stage'] in ('completed', 'failed'):
            return job
        time.sleep(.03)
    pytest.fail('Worker did not finish')


def start(client: TestClient, content: bytes) -> str:
    """Upload a video using the same raw request contract as the browser."""
    response = client.post('/api/runs', params=PARAMS, headers=HEADERS, content=content)
    assert response.status_code == 202, response.text
    return response.json()['id']


def test_complete_flow_evidence_ranges_and_export(client: TestClient, video: bytes) -> None:
    """Compile a replayed video, seek media, resolve frames and verify ZIP hashes."""
    run_id = start(client, video)
    job = wait_job(client, run_id)
    assert job['stage'] == 'completed', job
    assert job['live_inference'] is False
    assert len(job['sampled_frames']) == 2
    assert [frame['timestamp_s'] for frame in job['sampled_frames']] == [0, 1.8]
    assert client.get(job['sampled_frames'][0]['url']).headers['content-type'] == 'image/jpeg'
    assert [event['stage'] for event in job['events']] == ['queued', 'ingesting_frames', 'extracting_observations', 'extracting_protocol', 'compiling', 'completed']
    response = client.get(f'/api/runs/{run_id}/results')
    assert response.status_code == 200
    result = response.json()
    assert result['summary']['physical_validation'] is False
    assert result['accounting']['metrics']['cost_usd_per_accepted']['value'] is None
    assert result['accounting']['metrics']['cost_usd_per_accepted']['missing_inputs']
    evidence = result['protocol']['operations'][0]['evidence']
    assert [item['timestamp_s'] for item in evidence] == [0, 1.8]
    assert client.get(evidence[0]['url']).headers['content-type'] == 'image/jpeg'
    media = client.get(f'/api/runs/{run_id}/video', headers={'Range': 'bytes=10-29'})
    assert media.status_code == 206
    assert media.content == video[10:30]
    assert client.get(f'/api/runs/{run_id}/artifacts/compiled/report.md').status_code == 200
    bundle = client.get(f'/api/runs/{run_id}/bundle')
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        checksums = json.loads(archive.read('checksums.json'))
        assert archive.read('source.mp4') == video
        for name, digest in checksums.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    assert client.get('/api/runs').json()[0]['id'] == run_id


def test_failed_video_is_not_success(client: TestClient) -> None:
    """Decode failure retains the run and never exposes completed results."""
    run_id = start(client, b'not a video')
    job = wait_job(client, run_id)
    assert job['stage'] == 'failed'
    assert 'ingesting_frames' in job['error']
    assert client.get(f'/api/runs/{run_id}/results').status_code == 409
    assert client.get(f'/api/runs/{run_id}/bundle').status_code == 409


def test_upload_guards_and_local_origin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject cross-site writes, malformed inputs and oversized streaming bodies."""
    assert client.post('/api/runs', params=PARAMS, content=b'x').status_code == 403
    assert client.post('/api/runs', params=PARAMS, headers={**HEADERS, 'Origin': 'https://other.example'}, content=b'x').status_code == 403
    assert client.post('/api/runs', params=PARAMS, headers=HEADERS, content=b'').status_code == 422
    assert client.post('/api/runs', params={**PARAMS, 'filename': 'x.html'}, headers=HEADERS, content=b'x').status_code == 422
    monkeypatch.setattr('protocol_pipeline.web.MAX_UPLOAD', 2)
    assert client.post('/api/runs', params=PARAMS, headers=HEADERS, content=b'123').status_code == 413
    assert client.get('/api/runs').json() == []
    assert client.get('/', headers={'Host': 'evil.example'}).status_code == 400


def test_missing_credentials_fail_before_creating_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Preflight unavailable credentials without a paid call or replay fallback."""
    monkeypatch.delenv('NEBIUS_API_KEY', raising=False)
    monkeypatch.delenv('NEBIUS_TOKEN_FACTORY_KEY', raising=False)
    monkeypatch.setattr('protocol_pipeline.web.load_environment', lambda: None)
    with TestClient(create_app(tmp_path)) as client:
        assert client.post('/api/runs', params=PARAMS, headers=HEADERS, content=b'x').status_code == 503
        assert client.get('/api/runs').json() == []


def test_restart_recovers_completed_and_interrupts_unfinished(tmp_path: Path, video: bytes) -> None:
    """Reopen finished jobs after restart without rerunning inference."""
    replay = replay_file(tmp_path / 'replay.json')
    root = tmp_path / 'runs'
    with TestClient(create_app(root, lambda: ReplayProvider(replay))) as client:
        run_id = start(client, video)
        assert wait_job(client, run_id)['stage'] == 'completed'
    pending_id = 'a' * 32
    pending = root / pending_id
    pending.mkdir()
    (pending / 'job.json').write_text(json.dumps({'id': pending_id, 'stage': 'queued', 'events': [], 'created_at': time.time()}))
    with TestClient(create_app(root, lambda: ReplayProvider(replay))) as client:
        assert client.get(f'/api/runs/{run_id}/results').status_code == 200
        assert client.get(f'/api/runs/{pending_id}').json()['stage'] == 'failed'
        assert len(client.get('/api/runs').json()) == 2


def test_artifact_confinement_and_static_app(client: TestClient, video: bytes) -> None:
    """Never serve unlisted files; ship video, results and external-script UI."""
    run_id = start(client, video)
    wait_job(client, run_id)
    assert client.get(f'/api/runs/{run_id}/artifacts/unknown.txt').status_code == 404
    assert client.get('/api/runs/not-a-run/video').status_code == 404
    assert client.get('/assets/web.py').status_code == 404
    html = client.get('/')
    assert '<video' in html.text and 'id="result-content"' in html.text
    assert "frame-ancestors 'none'" in html.headers['content-security-policy']
    assert client.get('/assets/app.js').status_code == 200



@pytest.mark.parametrize('configured,expected', [
    (None, 'MiniMaxAI/MiniMax-M3'),
    ('   ', 'MiniMaxAI/MiniMax-M3'),
    (' custom/vision ', 'custom/vision'),
])
def test_vision_config_defaults(client: TestClient, monkeypatch: pytest.MonkeyPatch,
                               configured: str | None, expected: str) -> None:
    """Resolve absent/blank settings and preserve explicit server overrides."""
    monkeypatch.delenv('NEBIUS_VISION_MODEL', raising=False)
    if configured is not None:
        monkeypatch.setenv('NEBIUS_VISION_MODEL', configured)
    config = client.get('/api/config').json()
    assert config['provider'] == 'nebius'
    assert config['vision_model'] == expected


@pytest.mark.parametrize('override', [None, 'another/vision-model'])
def test_selected_model_reaches_nebius_and_rejection_is_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, video: bytes, override: str | None,
) -> None:
    """Capture actual provider JSON and safely expose an unavailable-model response."""
    from urllib.error import HTTPError
    from urllib.request import Request

    captured: list[dict[str, Any]] = []

    def reject(request: Request, **kwargs: Any) -> Any:
        """Record the outbound request and simulate a private error response."""
        captured.append(json.loads(request.data))
        raise HTTPError(request.full_url, 404, 'private provider detail', {}, None)

    monkeypatch.setenv('NEBIUS_API_KEY', 'test-secret-never-display')
    monkeypatch.delenv('NEBIUS_VISION_MODEL', raising=False)
    monkeypatch.setattr('protocol_pipeline.pipeline.urlopen', reject)
    with TestClient(create_app(tmp_path / 'runs')) as browser:
        config = browser.get('/api/config').json()
        chosen = override or config['vision_model']
        response = browser.post('/api/runs', params={**PARAMS, 'vision_model': chosen},
                                headers=HEADERS, content=video)
        assert response.status_code == 202
        job = wait_job(browser, response.json()['id'])
        assert captured[0]['model'] == chosen
        assert job['vision_model'] == chosen
        assert job['stage'] == 'failed'
        assert 'Vision model request was rejected by Nebius (HTTP 404)' in job['error']
        assert 'start a new run' in job['error']
        assert 'private provider detail' not in json.dumps(job)
        assert 'test-secret-never-display' not in json.dumps(job)


def test_queue_progress_timeout_and_logs(tmp_path: Path, video: bytes, caplog: pytest.LogCaptureFixture) -> None:
    """Expose queued/active timings, timeout diagnostics and a backend traceback."""
    import logging
    import threading

    entered, release = threading.Event(), threading.Event()

    class WaitingProvider:
        name = 'test-timeout'
        live = False

        def complete(self, *args: Any, **kwargs: Any) -> Any:
            entered.set()
            assert release.wait(10)
            raise TimeoutError('simulated provider timeout')

    caplog.set_level(logging.INFO, logger='protocol_pipeline.web')
    with TestClient(create_app(tmp_path / 'runs', WaitingProvider)) as browser:
        first = start(browser, video)
        try:
            assert entered.wait(10)
            active = browser.get(f'/api/runs/{first}').json()
            assert active['stage'] == 'extracting_observations'
            assert active['stage_elapsed_s'] >= 0
            assert 'fixture-vision' in active['progress_message']
            assert len(active['sampled_frames']) == 2
            assert browser.get(active['sampled_frames'][0]['url']).status_code == 200
            second = start(browser, video)
            queued = browser.get(f'/api/runs/{second}').json()
            assert queued['stage'] == 'queued'
            assert queued['queue_position'] == 1
            assert 'one at a time' in queued['progress_message']
        finally:
            release.set()
        for run_id in (first, second):
            failed = wait_job(browser, run_id)
            assert failed['error_type'] == 'TimeoutError'
            assert failed['failed_stage'] == 'extracting_observations'
            assert 'Timed out' in failed['error']
            assert failed['progress_message'] == failed['error']
            assert 'test-secret-never-display' not in json.dumps(failed)
    assert f'run={first} stage=extracting_observations' in caplog.text
    assert 'previous_duration_s=' in caplog.text
    assert 'error_type=TimeoutError' in caplog.text
    assert 'Traceback (most recent call last)' in caplog.text
    assert 'simulated provider timeout' in caplog.text


def test_validation_failure_exposes_fields_and_traceback(tmp_path: Path, video: bytes,
                                                       caplog: pytest.LogCaptureFixture) -> None:
    """Retain the actual schema failure instead of generic credential/model advice."""
    from protocol_pipeline.models import ObservationGraph

    class InvalidProvider:
        name = 'invalid-response'
        live = False

        def complete(self, *args: Any, **kwargs: Any) -> Any:
            return ObservationGraph.model_validate({'actions': [{}]})

    with TestClient(create_app(tmp_path / 'runs', InvalidProvider)) as browser:
        job = wait_job(browser, start(browser, video))
        assert job['error_type'] == 'ValidationError'
        assert 'actions.0.id' in job['error']
        assert 'Field required' in job['error']
        assert 'Check video decoding' not in job['error']
    assert 'Traceback (most recent call last)' in caplog.text
    assert 'actions.0.id' in caplog.text


def test_reload_launcher_preserves_run_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reload uses an importable factory and keeps custom run storage across child restarts."""
    from protocol_pipeline.web import main
    import os

    called = {}
    monkeypatch.setattr('sys.argv', ['web', '--reload', '--port', '8123', '--runs', str(tmp_path)])
    monkeypatch.setenv('WORKBENCH_RUNS', '')
    monkeypatch.setattr('uvicorn.run', lambda app, **kwargs: called.update(app=app, **kwargs))
    main()
    assert called['app'] == 'protocol_pipeline.web:create_app'
    assert called['factory'] is True
    assert called['reload'] is True
    assert called['port'] == 8123
    assert os.environ['WORKBENCH_RUNS'] == str(tmp_path.resolve())


def test_step_five_generates_separately_and_persists_cost_edits(tmp_path: Path, video: bytes) -> None:
    """One design call, no new vision request, immutable extraction and reopenable assumptions."""
    from protocol_pipeline.autonomy import AutonomyProposal
    from protocol_pipeline.compiler import ProtocolSpecification
    from test_autonomy import proposal_fixture

    replay = replay_file(tmp_path / 'replay.json')
    source_spec = ProtocolSpecification.model_validate(json.loads(replay.read_text())['responses'][1]['response'])
    contracts = []

    class DesignReplay(ReplayProvider):
        def complete(self, model, contract, instruction, content):
            contracts.append(contract.__name__)
            if contract is AutonomyProposal:
                return contract.model_validate(proposal_fixture(source_spec)), {'requested_model': model, 'provenance': 'synthetic design fixture'}
            return super().complete(model, contract, instruction, content)

    root = tmp_path / 'runs'
    factory = lambda: DesignReplay(replay)
    with TestClient(create_app(root, factory)) as browser:
        run_id = start(browser, video)
        assert wait_job(browser, run_id)['stage'] == 'completed'
        original = (root / run_id / 'extracted/extracted-protocol.json').read_bytes()
        url = f'/api/runs/{run_id}/autonomy'
        assert browser.get(url).json()['stage'] == 'not_started'
        assert browser.post(url, headers=HEADERS, params={'model': 'design-fixture'}).status_code == 202
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = browser.get(url).json()
            if state['stage'] in ('completed', 'failed'):
                break
            time.sleep(.02)
        assert state['stage'] == 'completed', state
        assert state['design']['pricing_basis'] == 'model_planning_estimates_not_supplier_quotes'
        assert contracts == ['ObservationGraph', 'ProtocolSpecification', 'AutonomyProposal']
        assert browser.post(url, headers=HEADERS, params={'model': 'design-fixture'}).json()['stage'] == 'completed'
        assert len(contracts) == 3
        edits = browser.post(url + '/costs', headers=HEADERS, json={'values': {'equipment.robot.unit_cost_usd': 2000}})
        assert edits.status_code == 200, edits.text
        assert edits.json()['equipment_total_usd'] == 4000
        assert browser.post(url + '/costs', headers=HEADERS, json={'values': {'utilization': 2}}).status_code == 422
        assert browser.get(url + '/export').status_code == 200
        assert (root / run_id / 'extracted/extracted-protocol.json').read_bytes() == original
    with TestClient(create_app(root, factory)) as browser:
        state = browser.get(url).json()
        assert state['stage'] == 'completed'
        assert state['economics']['equipment_total_usd'] == 4000
        assert len(contracts) == 3
