# SPDX-License-Identifier: MPL-2.0
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


def test_status_read_retries_transient_windows_access(monkeypatch: Any, tmp_path: Path) -> None:
    from unittest.mock import Mock
    from protocol_pipeline.web import read_json
    read = Mock(side_effect=[PermissionError('busy'), '{"stage":"completed"}'])
    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr('protocol_pipeline.web.time.sleep', lambda _: None)
    assert read_json(tmp_path / 'job.json') == {'stage': 'completed'}
    assert read.call_count == 2
    read.side_effect = PermissionError('persistent denial')
    read.reset_mock()
    with pytest.raises(PermissionError):
        read_json(tmp_path / 'job.json')
    assert read.call_count == 4


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


def test_account_catalog_is_cached_per_provider(client: TestClient, monkeypatch: Any) -> None:
    from types import SimpleNamespace
    calls = []

    def provider(name: str) -> Any:
        def available_models() -> list[str]:
            calls.append(name)
            return [f'{name}/model-a', f'{name}/model-b']
        return SimpleNamespace(client=SimpleNamespace(available_models=available_models))

    monkeypatch.setattr('protocol_pipeline.web.create_provider', provider)
    for name in ('nebius', 'gmi'):
        for _ in range(2):
            response = client.get(f'/api/models/{name}')
            assert response.status_code == 200
            assert response.json() == {'provider': name, 'models': [f'{name}/model-a', f'{name}/model-b']}
    assert calls == ['nebius', 'gmi']
    assert client.get('/api/models/unknown').status_code == 422


def test_gmi_analysis_uses_selected_provider(client: TestClient, video: bytes, monkeypatch: Any) -> None:
    calls = []
    replay = client.app.state.store.provider_factory()

    def provider(name: str) -> Any:
        calls.append(name)
        return replay

    monkeypatch.setattr('protocol_pipeline.web.create_provider', provider)
    response = client.post('/api/runs', params={**PARAMS, 'provider': 'gmi'}, headers=HEADERS, content=video)
    assert response.status_code == 202
    assert response.json()['provider'] == 'gmi'
    assert wait_job(client, response.json()['id'])['stage'] == 'completed'
    assert calls == ['gmi']


@pytest.mark.parametrize('repair', [True, False])
def test_observation_correction_retains_candidates(client: TestClient, video: bytes, repair: bool) -> None:
    from protocol_pipeline.models import ObservationGraph
    original = client.app.state.store.provider_factory
    calls = []

    class Provider:
        name = 'test-live'
        live = True

        def __init__(self) -> None:
            self.replay = original()
            self.graph = None

        def complete(self, model: str, contract: Any, instruction: str, content: Any) -> Any:
            if contract is ObservationGraph:
                calls.append(content)
                if self.graph is None:
                    self.graph, self.trace = self.replay.complete(model, contract, instruction, content)
                graph = self.graph.model_copy(deep=True)
                if len(calls) == 1 or not repair:
                    graph.actions[0].start_s = 0.5
                return graph, self.trace
            return self.replay.complete(model, contract, instruction, content)

    client.app.state.store.provider_factory = Provider
    run_id = start(client, video)
    job = wait_job(client, run_id)
    assert job['stage'] == ('completed' if repair else 'failed')
    assert len(calls) == 2
    assert 'frame_0000' in calls[1][-1]['text']
    assert any(event['stage'] == 'correcting_observations' for event in job['events'])
    output = client.app.state.store.path(run_id) / 'extracted'
    assert (output / 'observation-candidate-1.json').is_file()
    assert (output / 'observation-candidate-2.json').is_file()
    if not repair:
        assert not (output / 'observations.json').exists()


def test_import_snapshot_populates_existing_workbench(client: TestClient, video: bytes, tmp_path: Path) -> None:
    from protocol_pipeline.snapshots import E2EConfig, file_index
    run_id=start(client,video)
    assert wait_job(client,run_id)['stage']=='completed'
    root=tmp_path/'saved-snapshot'
    copied=root/'workbench'/run_id
    shutil.copytree(client.app.state.store.path(run_id),copied)
    document={'kind':'workbench-e2e','schema_version':1,'version':1,'status':'completed',
              'config':E2EConfig().model_dump(),'run_path':f'workbench/{run_id}',
              'source':{'path':f'workbench/{run_id}/source.mp4','sha256':hashlib.sha256(video).hexdigest()},
              'files':file_index(root)}
    (root/'snapshot.json').write_text(json.dumps(document))
    response=client.post('/api/snapshots/import',headers=HEADERS,json={'path':str(root)})
    assert response.status_code==200,response.text
    imported=response.json()['id']
    assert imported!=run_id
    assert client.get(f'/api/runs/{imported}').json()['stage']=='completed'
    result=client.get(f'/api/runs/{imported}/results')
    assert result.status_code==200
    original=client.get(f'/api/runs/{run_id}/results').json()['protocol']
    assert result.json()['protocol']['protocol_id']==original['protocol_id']
    assert result.json()['protocol']['operations'][0]['evidence'][0]['url'].startswith(f'/api/runs/{imported}/')
    assert client.get(f'/api/runs/{imported}/video').content==video
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as bundle:
        for path in root.rglob('*'):
            if path.is_file():bundle.write(path,path.relative_to(root).as_posix())
    uploaded=client.post('/api/snapshots/upload',headers={**HEADERS,'Content-Type':'application/zip'},content=archive.getvalue())
    assert uploaded.status_code==200,uploaded.text
    assert client.get(f"/api/runs/{uploaded.json()['id']}/results").status_code==200
    assert client.post('/api/snapshots/upload',headers=HEADERS,content=b'not a zip').status_code==422


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
    html = client.get('/video')
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


def test_step_five_generates_separately_and_persists_cost_edits(tmp_path: Path, video: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
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
        assert browser.get(f'/api/runs/{run_id}/scene').json()['stage'] == 'needs_design'
        assert browser.post(f'/api/runs/{run_id}/scene', headers=HEADERS, json={}).status_code == 409
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
        machine_calls = []
        def synthetic_machine(proposal_path, equipment_id, output, model, resume_from=None, authoring='forma',provider='nebius'):
            """Deterministic HTTP fixture; does not claim a live Forma call."""
            output.mkdir()
            machine_calls.append(equipment_id)
            report = {'equipment_id': equipment_id, 'core_version': 'fixture', 'cad_meshes': 1, 'components': 1,
                      'machine_specific_cad': {'parts':8,'description':'Explicit synthetic HTTP fixture',
                                               'representation':'opencad-python'},
                      'source_proposal_sha256': hashlib.sha256(proposal_path.read_bytes()).hexdigest(),
                      'deterministic_is_valid': False, 'physical_validation': False}
            (output / 'machine-report.json').write_text(json.dumps(report))
            (output / 'machine.forma.json').write_text(json.dumps({'project_ir': {'cad_model': {'meshes': [
                {'vertices': [0,0,0,100,0,0,0,100,0], 'faces': [0,1,2]}]}}}))
            (output / 'machine.py').write_text('# Synthetic source download fixture\n')
            (output / 'machine.step').write_text('Synthetic STEP download fixture')
            return report
        monkeypatch.setattr('protocol_pipeline.web.forma_runtime', lambda: {'available': True, 'message': 'Synthetic fixture'})
        monkeypatch.setattr('protocol_pipeline.web.generate_machine', synthetic_machine)
        def launch_fixture(store, run_id, keys, batch_id):
            store.slots.acquire()
            store.execute_machines(run_id, keys)
        monkeypatch.setattr('protocol_pipeline.web.JobStore.launch_machines', launch_fixture)
        machines_url = f'/api/runs/{run_id}/machines'
        assert browser.get(f'/api/runs/{run_id}/scene').json()['stage'] == 'needs_machines'
        assert browser.post(f'/api/runs/{run_id}/scene', headers=HEADERS, json={}).status_code == 409
        assert browser.post(machines_url, headers=HEADERS, json={'model': 'fixture'}).status_code == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            machines = browser.get(machines_url).json()
            if machines['stage'] == 'ready':
                break
            time.sleep(.02)
        assert machines['stage'] == 'ready', machines
        assert machine_calls == ['workcell']
        assert browser.post(machines_url, headers=HEADERS, json={'model': 'fixture'}).json()['stage'] == 'ready'
        assert machine_calls == ['workcell']
        assert browser.get(machines['machines'][0]['artifact_url']).status_code == 200
        row=machines['machines'][0]
        for name in ('machine.py', 'machine.step'):
            download = browser.get(f"{machines_url}/{row['key']}/artifacts/{name}")
            assert download.status_code == 200
            assert 'attachment' in download.headers['content-disposition']
        assert browser.get(f"{machines_url}/{row['key']}/artifacts/worker.log").status_code == 404
        assert browser.get(f"{machines_url}/{row['key']}/artifacts/machine.tree.json").status_code == 404
        assert row['preview']['ready'] is False
        assert browser.post(f"{machines_url}/{row['key']}/previews/{'0'*64}",headers=HEADERS,content=b'invalid').status_code==409
        gif=tmp_path/'preview-fixture.gif'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=320x320:rate=10','-t','2',str(gif)],check=True,capture_output=True,timeout=15)
        cached=browser.post(f"{machines_url}/{row['key']}/previews/{row['preview']['cache_key']}",headers={**HEADERS,'Content-Type':'image/gif'},content=gif.read_bytes())
        assert cached.status_code==200,cached.text
        assert cached.json()['ready'] is True
        image=browser.get(cached.json()['gif_url'])
        assert image.headers['content-type']=='image/gif'
        assert 'immutable' in image.headers['cache-control']
        assert browser.get(cached.json()['poster_url']).headers['content-type']=='image/png'
        def synthetic_scene(proposal_path, protocol_path, output, options, machine_assets):
            """HTTP lifecycle fixture; real native generation is tested separately."""
            output.mkdir()
            report = {'source_proposal_sha256': hashlib.sha256(proposal_path.read_bytes()).hexdigest(),
                      'machine_asset_sha256': {item['equipment_id']: hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() for item in machine_assets},
                      'engine': 'synthetic HTTP fixture, not the native engine', 'physical_validation': False}
            (output / 'scene-report.json').write_text(json.dumps(report))
            (output / 'scene.oi.json').write_text(json.dumps({'format': 'synthetic HTTP fixture'}))
            (output / 'preview.json').write_text(json.dumps({'samples': []}))
            return report

        monkeypatch.setattr('protocol_pipeline.web.openindustries_runtime', lambda: {'available': True, 'message': 'Synthetic fixture'})
        monkeypatch.setattr('protocol_pipeline.web.build_rehearsal', synthetic_scene)
        scene_url = f'/api/runs/{run_id}/scene'
        assert browser.post(scene_url, headers=HEADERS, json={}).status_code == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            scene = browser.get(scene_url).json()
            if scene['stage'] in ('completed', 'failed'):
                break
            time.sleep(.02)
        assert scene['stage'] == 'completed', scene
        assert browser.get(scene_url + '/artifacts/scene.oi.json').status_code == 200
        assert browser.get(scene_url + '/artifacts/secrets').status_code == 404
        assert browser.post(scene_url, headers=HEADERS, json={}).json()['attempt_id'] == scene['attempt_id']
        assert len(contracts) == 3  # scene creation does not repeat vision or design inference
        edits = browser.post(url + '/costs', headers=HEADERS, json={'values': {'equipment.workcell.unit_cost_usd': 4000}})
        assert edits.status_code == 200, edits.text
        assert edits.json()['equipment_total_usd'] == 4000
        assert browser.post(url + '/costs', headers=HEADERS, json={'values': {'utilization': 2}}).status_code == 422
        assert browser.get(url + '/export').status_code == 200
        assert (root / run_id / 'extracted/extracted-protocol.json').read_bytes() == original
    with TestClient(create_app(root, factory)) as browser:
        state = browser.get(url).json()
        assert state['stage'] == 'completed'
        assert state['economics']['equipment_total_usd'] == 4000
        assert browser.get(scene_url).json()['stage'] == 'completed'
        assert len(contracts) == 3
