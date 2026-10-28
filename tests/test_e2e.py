"""Append-only snapshots, provider routing and opt-in real native E2E coverage."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Iterator
from zipfile import ZipFile

import pytest

from protocol_pipeline import e2e
from protocol_pipeline.snapshots import (E2EConfig, allocate_snapshot, atomic_json, copy_source,
                                        latest_snapshot, read_json, verify_snapshot)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def stub_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace computation for storage/error tests, explicitly not quality evidence."""
    @contextmanager
    def capture() -> Iterator[Any]:
        """Avoid native runtime requirements for snapshot persistence checks."""
        yield lambda *args: None

    monkeypatch.setattr(e2e, 'native_capture', capture)
    monkeypatch.setattr(e2e, 'preflight', lambda *args: {'status': 'test_fixture'})
    for method in ('extract', 'design', 'cad', 'scene', 'review', 'lab'):
        monkeypatch.setattr(e2e.PipelineRun, method, lambda *args: None)


def test_versions_are_atomic_under_concurrency(tmp_path: Path) -> None:
    """Concurrent invocations must reserve different versions without overwrites."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        versions = list(pool.map(lambda _: allocate_snapshot(tmp_path), range(16)))
    assert sorted(int(path.name[1:]) for path in versions) == list(range(1, 17))


def test_source_provenance_mismatch_stops_before_inference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never attach another recording's provenance to a fresh live run."""
    video = tmp_path / 'source.mp4'
    video.write_bytes(b'input fixture')
    provenance = tmp_path / 'provenance.json'
    atomic_json(provenance, {'video_sha256': 'wrong'})
    def unexpected(*args: Any) -> None:
        """Fail if provider preparation is reached after invalid provenance."""
        pytest.fail('Preflight must not run')
    monkeypatch.setattr(e2e, 'preflight', unexpected)
    with pytest.raises(ValueError, match='provenance video checksum'):
        e2e.run_e2e(tmp_path / 'versions', video=video, source_provenance=provenance)


def test_video_export_failure_is_not_completed_snapshot(tmp_path: Path, stub_pipeline: None,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicitly requested comparison video must succeed before completion."""
    video = tmp_path / 'source.mp4'
    video.write_bytes(b'input fixture')
    def fail(self: e2e.PipelineRun) -> None:
        """Represent an encoder failure without calling native tools."""
        raise RuntimeError('encoding failed')
    monkeypatch.setattr(e2e.PipelineRun, 'machine_video', fail)
    with pytest.raises(RuntimeError, match='encoding failed'):
        e2e.run_e2e(tmp_path / 'versions', video=video, overrides={'machine_video': True})
    document = verify_snapshot(latest_snapshot(tmp_path / 'versions'))
    assert document['status'] == 'failed'
    assert document['stages']['machine_video']['status'] == 'failed'
    assert 'lab' not in document['stages']


def test_latest_roundtrip_relocation_and_config_inheritance(tmp_path: Path, stub_pipeline: None) -> None:
    """Move an entire snapshot, then append using only serialized input/settings."""
    video = tmp_path / 'source.mp4'
    video.write_bytes(b'Explicit non-video storage fixture')
    first = e2e.run_e2e(tmp_path / 'versions', video=video, overrides={'frame_count': 4, 'visual_passes': 2})
    original = (first / 'snapshot.json').read_bytes()
    moved = tmp_path / 'moved'
    shutil.move(first, moved)
    video.unlink()
    second = e2e.run_e2e(tmp_path / 'versions', snapshot=moved)
    document = verify_snapshot(second / 'snapshot.json')
    assert document['config']['vision_model'] == 'nvidia/Nemotron-3.5-Super-VL'
    assert document['config']['text_model'] == 'openai/gpt-6-astra'
    assert document['config']['frame_count'] == 4
    assert document['config']['visual_passes'] == 2
    assert (moved / 'snapshot.json').read_bytes() == original
    third = e2e.run_e2e(tmp_path / 'versions', overrides={'frame_count': 6})
    assert third != second
    assert read_json(third / 'snapshot.json')['parent']['version'] == document['version']
    assert latest_snapshot(tmp_path / 'versions') == third / 'snapshot.json'
    assert all(not Path(item['path']).is_absolute() for item in document['files'])
    assert set(document['stages']) == {'preflight', 'extraction', 'proposal', 'cad', 'scene', 'visual_review', 'lab'}


def test_failed_run_is_retained_and_next_run_appends(tmp_path: Path, stub_pipeline: None,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """Never report success or overwrite evidence when a downstream stage fails."""
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'Storage fixture')

    def fail(self: e2e.PipelineRun) -> None:
        """Leave partial evidence as a real failed CAD worker would."""
        atomic_json(self.run / 'failure.json', {'status': 'fixture_failure'})
        raise RuntimeError('native CAD rejected fixture')

    monkeypatch.setattr(e2e.PipelineRun, 'cad', fail)
    with pytest.raises(RuntimeError, match='CAD rejected'):
        e2e.run_e2e(tmp_path / 'versions', video=video)
    first = latest_snapshot(tmp_path / 'versions')
    document = verify_snapshot(first)
    assert document['status'] == 'failed'
    assert document['stages']['cad']['status'] == 'failed'
    assert 'lab' not in document['stages']
    original = first.read_bytes()
    monkeypatch.setattr(e2e.PipelineRun, 'cad', lambda self: None)
    second = e2e.run_e2e(tmp_path / 'versions')
    assert second.name == 'v000002'
    assert first.read_bytes() == original


@pytest.mark.parametrize('mutation', ['content', 'traversal', 'symlink', 'schema'])
def test_snapshot_tampering_rejected_before_new_run(tmp_path: Path, stub_pipeline: None, mutation: str) -> None:
    """Validate bytes and relative paths before creating a version or calling models."""
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'Input fixture')
    output = e2e.run_e2e(tmp_path / 'versions', video=video)
    manifest = output / 'snapshot.json'
    document = read_json(manifest)
    source = output / document['source']['path']
    if mutation == 'content':
        source.write_bytes(b'changed')
    elif mutation == 'traversal':
        document['files'][0]['path'] = '../video.mp4'
    elif mutation == 'symlink':
        source.unlink()
        try:
            source.symlink_to(video)
        except OSError as error:
            if getattr(error, 'winerror', None) == 1314:
                pytest.skip('Windows session lacks symlink creation privilege (WinError 1314)')
            raise
    else:
        document['schema_version'] = 99
    atomic_json(manifest, document)
    with pytest.raises(ValueError):
        e2e.run_e2e(tmp_path / 'versions')
    assert not (tmp_path / 'versions/v000002').exists()


def test_legacy_zip_import_copies_only_video_and_verifies_hash(tmp_path: Path) -> None:
    """Existing PR #50 snapshots are usable without restoring executable source."""
    source = ROOT / 'snapshots/workbench-20261022-184138Z-a90ec05/snapshot.zip'
    result = copy_source(source, tmp_path / 'input')
    assert (tmp_path / result['path']).stat().st_size > 1000
    assert list((tmp_path / 'input').iterdir()) == [tmp_path / result['path']]
    malicious = tmp_path / 'ambiguous.zip'
    with ZipFile(malicious, 'w') as archive:
        for run in ('a' * 32, 'b' * 32):
            archive.writestr(f'runs/workbench/{run}/source.mp4', b'fixture')
        archive.writestr('../../escape.py', b'never execute')
    with pytest.raises(ValueError, match='exactly one'):
        copy_source(malicious, tmp_path / 'bad')
    assert not (tmp_path.parent / 'escape.py').exists()


def test_preflight_never_substitutes_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Account catalog mismatches fail before OpenCode or inference calls."""
    class Provider:
        """Catalog-only fixture with no inference capability."""
        name = 'nebius'

        def __init__(self) -> None:
            self.client = self

        def available_models(self) -> list[str]:
            """Return a different model, which must not be used as a fallback."""
            return ['unrequested-model']

    monkeypatch.setattr(e2e, 'NebiusProvider', Provider)
    monkeypatch.setattr(e2e, 'GMIProvider', Provider)
    monkeypatch.setattr(e2e.shutil, 'which', lambda name: name)
    monkeypatch.setattr(e2e, 'forma_runtime', lambda: {'available': True})
    with pytest.raises(ValueError, match='no fallback'):
        e2e.preflight(E2EConfig())


@pytest.mark.skipif(os.getenv('WORKBENCH_NATIVE_E2E_TESTS') != '1', reason='Opt-in native CAD, OI and Chromium integration')
def test_native_pipeline_from_video_to_lab_and_matched_visual_review(tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """Use deterministic inference with real FFmpeg, OCCT, Forma, OI and WebGL renders."""
    from protocol_pipeline.autonomy import AutonomyProposal
    from protocol_pipeline.compiler import ProtocolSpecification
    from protocol_pipeline.models import ObservationGraph
    from protocol_pipeline.opencad_program import CadProgram
    from protocol_pipeline.opencode_machine_worker import execute
    from protocol_pipeline.visual_review import VisualCritique
    from test_autonomy import proposal_fixture
    from test_opencad_program import program_data

    video = tmp_path / 'fixture.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=5',
                    '-t', '2', '-pix_fmt', 'yuv420p', str(video)], check=True, capture_output=True)
    spec = read_json(ROOT / 'examples/extraction/recorded-response.json')['responses'][0]['response']
    for operation in spec['operations']:
        operation.update(source_refs=['action:transfer'], object_ids=['tube'])
    for criterion in spec['acceptance_criteria']:
        criterion['source_refs'] = ['hypothesis:synthetic acceptance check']
    calls = []

    class Provider:
        """Only inference is synthetic; all downstream services execute normally."""
        live = False

        def __init__(self, name: str) -> None:
            self.name = name

        def complete(self, model: str, contract: Any, instruction: str, content: list[dict]) -> tuple[Any, dict]:
            """Check exact provider/model routing and return typed fixture responses."""
            calls.append((self.name, model, contract.__name__))
            if contract is ObservationGraph:
                assert self.name == 'nebius' and model == E2EConfig().vision_model
                frames = read_json(next(tmp_path.rglob('ingested/manifest.json')))['frames']
                evidence = {'evidence_frame_ids': [row['id'] for row in frames], 'confidence': .5,
                            'interpretation': 'Deterministic fixture; not inference'}
                raw = {'objects': [{**evidence, 'id': 'tube', 'description': 'Fixture tube'}],
                       'actions': [{**evidence, 'id': 'transfer', 'action': 'transfer', 'object_ids': ['tube'],
                                    'start_s': 0, 'end_s': frames[-1]['timestamp_s']}],
                       'state_changes': [], 'limitations': ['Synthetic test']}
            elif contract is ProtocolSpecification:
                assert self.name == 'gmi' and model == E2EConfig().text_model
                raw = spec
            else:
                assert contract is AutonomyProposal and self.name == 'gmi' and model == E2EConfig().text_model
                raw = proposal_fixture(ProtocolSpecification.model_validate(spec))
            return contract.model_validate(raw), {'provider': self.name, 'requested_model': model, 'provenance': 'synthetic fixture'}

    class Author:
        """Supply feature-based Python to the real native CAD authoring/validation loop."""
        session_id = 'synthetic-e2e'
        provider = 'fixture'

        def complete(self, contract: Any, *args: Any) -> tuple[CadProgram, dict]:
            """Return the committed plate and hollow loft fixture."""
            return contract.model_validate(program_data()), {'provenance': 'synthetic fixture'}

    def generate(proposal: Path, equipment_id: str, output: Path, model: str, **kwargs: Any) -> dict:
        """Replace the outer worker process so deterministic author injection stays local."""
        assert model == E2EConfig().text_model and kwargs['provider'] == 'gmi' and kwargs['authoring'] == 'opencode'
        equipment = next(row for row in read_json(proposal)['proposal']['equipment'] if row['id'] == equipment_id)
        output.mkdir(parents=True)
        execute(output, {'model': model, 'provider': 'gmi', 'equipment': equipment, 'operations': [],
                         'source_proposal_sha256': e2e.sha256(proposal)})
        return read_json(output / 'machine-report.json')

    def review(path: Path, phase: str, options: Any, context: dict, *args: Any) -> VisualCritique:
        """Request a real layout correction and approve only its matched after capture."""
        assert options.vision_model == E2EConfig().vision_model
        assert options.cad_provider == 'gmi' and options.cad_model == E2EConfig().text_model
        assert (path / phase / 'render-isometric.png').stat().st_size > 1000
        result = VisualCritique.model_validate({
            'status': 'needs_improvement' if phase == 'before' else 'acceptable',
            'score': 30 if phase == 'before' else 80, 'summary': 'Synthetic visual critique',
            'issues': [{'id': 'layout-1', 'kind': 'layout', 'severity': 'medium', 'equipment_ids': ['robot'],
                        'description': 'Synthetic spacing issue', 'evidence_view_ids': ['render-top'],
                        'correction': 'Move fixture'}] if phase == 'before' else [],
            'layout_changes': [{'instance_id': context['instances'][0]['instance_id'],
                                'position_m': [1, 0, 0], 'rationale': 'Synthetic spacing correction'}] if phase == 'before' else [],
            'cad_changes': [], 'resolved_issue_ids': ['layout-1'] if phase == 'after' else [],
            'limitations': ['Deterministic response, not live quality evidence'],
        })
        atomic_json(path / f'{phase}-critique.json', result.model_dump(mode='json'))
        return result

    monkeypatch.setattr(e2e, 'preflight', lambda *args: {'status': 'fixture_inference; real native dependencies'})
    monkeypatch.setattr(e2e, 'GMIProvider', lambda: Provider('gmi'))
    monkeypatch.setattr('protocol_pipeline.web.create_provider', Provider)
    monkeypatch.setattr('protocol_pipeline.web.generate_machine', generate)
    monkeypatch.setattr('protocol_pipeline.opencode_machine.OpenCodeMachineSession', lambda *args, **kwargs: Author())
    monkeypatch.setattr('protocol_pipeline.visual_review.review_images', review)
    output = e2e.run_e2e(tmp_path / 'versions', video=video, overrides={'frame_count': 2})
    document = verify_snapshot(output / 'snapshot.json')
    assert document['status'] == 'completed'
    assert [row[0] for row in calls] == ['nebius', 'gmi', 'gmi']
    run = output / document['run_path']
    summary = read_json(run / 'visual-reviews/summary.json')
    assert summary['passes'][0]['outcome'] == 'applied'
    review_root = run / 'visual-reviews' / summary['passes'][0]['id']
    before, after = [read_json(review_root / phase / 'captures.json') for phase in ('before', 'after')]
    assert before['frames'] == after['frames']
    assert before['sha256'] != after['sha256']
    assert list(run.glob('machines/*/*/machine.step'))
    assert list(run.glob('lab/*/renders/render-top.png'))
    assert all(row['status'] == 'completed' for row in document['stages'].values())
