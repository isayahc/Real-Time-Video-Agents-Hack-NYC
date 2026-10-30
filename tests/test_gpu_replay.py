"""Exercise static export integrity and reject unsupported execution claims."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from protocol_pipeline.gpu_replay import GPUReplay, export_replay
from protocol_pipeline.pipeline import sha256


def test_blocked_export_is_static_and_allowlisted(tmp_path: Path) -> None:
    """The genuine blocked receipt cannot turn into a completed inference demo."""
    output = tmp_path / 'site'
    run = export_replay(Path('examples/gpu-replay/blocked.json'), output)
    page = (output / 'index.html').read_text(encoding='utf-8')
    assert run.status == 'blocked'
    assert 'no GR00T or SONIC execution' in page
    assert '<video' not in page and '<script' not in page
    assert {p.name for p in output.iterdir()} == {'index.html', 'run.json', 'checksums.json', 'vercel.json'}
    entries = json.loads((output / 'checksums.json').read_text())
    assert 'vercel.json' not in {entry['path'] for entry in entries}
    for entry in entries:
        assert sha256(output / entry['path']) == entry['sha256']
    with pytest.raises(FileExistsError):
        export_replay(Path('examples/gpu-replay/blocked.json'), output)


@pytest.fixture
def synthetic_run(tmp_path: Path) -> Path:
    """Create explicitly synthetic linked artifacts, never live inference evidence."""
    document = json.loads(Path('examples/gpu-replay/blocked.json').read_text())
    document.update(status='completed', evidence='synthetic_test', simulator='test simulator',
                    task='<script>alert(1)</script>', outcome='unknown')
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    entries = []
    for name, role in [('observation.json', 'observations'), ('actions.json', 'actions'),
                       ('trace.json', 'controller_trace'), ('frame.png', 'frame')]:
        path = artifacts / name
        if role == 'frame':
            from PIL import Image
            Image.new('RGB', (32, 32), '#20352e').save(path)
        else:
            path.write_text('{"synthetic_test": true}', encoding='utf-8')
        entries.append(dict(path='artifacts/' + name, role=role, sha256=sha256(path),
                            bytes=path.stat().st_size, caption='Synthetic fixture'))
    document['artifacts'] = entries
    document['gr00t'] = dict(status='completed', model_id='synthetic-gr00t', revision='test-only',
                             inputs=['artifacts/observation.json'], outputs=['artifacts/actions.json'])
    document['sonic'] = dict(status='completed', model_id='synthetic-sonic', revision='test-only',
                             inputs=['artifacts/actions.json'],
                             outputs=['artifacts/trace.json', 'artifacts/frame.png'])
    manifest = tmp_path / 'run.json'
    manifest.write_text(json.dumps(document), encoding='utf-8')
    (tmp_path / '.env').write_text('PRIVATE=do-not-copy', encoding='utf-8')
    return manifest


def test_linked_fixture_retains_label_and_escapes_text(synthetic_run: Path, tmp_path: Path) -> None:
    """Passing file checks cannot promote a fixture or inject executable HTML."""
    output = tmp_path / 'site'
    export_replay(synthetic_run, output)
    page = (output / 'index.html').read_text(encoding='utf-8')
    assert 'Synthetic test fixture' in page
    assert '<script>alert' not in page and '&lt;script&gt;' in page
    assert not (output / '.env').exists()
    assert (output / 'artifacts/frame.png').exists()


def test_tampering_rejected_before_output(synthetic_run: Path, tmp_path: Path) -> None:
    """Changed action bytes must not get packaged as the recorded model output."""
    (tmp_path / 'artifacts/actions.json').write_text('changed')
    with pytest.raises(ValueError, match='checksum mismatch'):
        export_replay(synthetic_run, tmp_path / 'site')
    assert not (tmp_path / 'site').exists()


@pytest.mark.parametrize('mutation', ['no_actions_consumed', 'no_trace', 'no_identity', 'no_media',
                                     'no_observations', 'traversal', 'duplicate', 'missing_reference'])
def test_false_completed_receipt_rejected(synthetic_run: Path, mutation: str) -> None:
    """Completion requires a linked observation/action/controller/media chain."""
    doc = json.loads(synthetic_run.read_text())
    if mutation == 'no_actions_consumed':
        doc['sonic']['inputs'] = ['artifacts/observation.json']
    elif mutation == 'no_trace':
        doc['sonic']['outputs'] = ['artifacts/frame.png']
    elif mutation == 'no_identity':
        doc['gr00t']['revision'] = None
    elif mutation == 'no_media':
        doc['sonic']['outputs'] = ['artifacts/trace.json']
    elif mutation == 'no_observations':
        doc['gr00t']['inputs'] = ['artifacts/actions.json']
    elif mutation == 'traversal':
        doc['artifacts'][0]['path'] = 'artifacts/../../private.json'
    elif mutation == 'duplicate':
        doc['artifacts'].append(doc['artifacts'][0])
    else:
        doc['sonic']['inputs'] = ['artifacts/missing.json']
    with pytest.raises(ValueError):
        GPUReplay.model_validate(doc)


def test_no_execution_cannot_claim_success() -> None:
    """A blocked preflight must never be rendered as successful robot behavior."""
    doc = json.loads(Path('examples/gpu-replay/blocked.json').read_text())
    doc['outcome'] = 'success'
    with pytest.raises(ValueError, match='cannot contain results'):
        GPUReplay.model_validate(doc)


def test_cli_supports_windows_console_encoding(tmp_path: Path) -> None:
    """A successful export must also exit successfully on a CP1252 console."""
    result = subprocess.run(
        [sys.executable, '-m', 'protocol_pipeline.gpu_replay', '--manifest',
         'examples/gpu-replay/blocked.json', '--output', str(tmp_path / 'site')],
        env={**os.environ, 'PYTHONIOENCODING': 'cp1252'}, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr.decode('cp1252')
    assert b'blocked (no_execution)' in result.stdout
