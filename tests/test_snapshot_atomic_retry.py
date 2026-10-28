# SPDX-License-Identifier: MPL-2.0
"""Transient checkpoint locks must not discard evidence or repeat paid work."""
from pathlib import Path
from unittest.mock import patch

import pytest

from protocol_pipeline.snapshots import atomic_json, file_index, read_json


def test_pending_checkpoint_is_not_indexed_as_artifact(tmp_path: Path) -> None:
    """Final replacement consumes snapshot.tmp; it cannot be a portable artifact."""
    (tmp_path / 'snapshot.tmp').write_text('{}')
    (tmp_path / 'snapshot.json').write_text('{}')
    (tmp_path / 'evidence.txt').write_text('retained')
    assert [row['path'] for row in file_index(tmp_path)] == ['evidence.txt']


def test_windows_lock_retries_replacement_only(tmp_path: Path) -> None:
    """A temporary Windows lock preserves the old checkpoint until replacement."""
    target = tmp_path / 'snapshot.json'
    atomic_json(target, {'status': 'old'})
    original = Path.replace
    calls = []

    def replace(source: Path, destination: Path) -> Path:
        """Simulate one sharing denial, then use the actual filesystem."""
        calls.append(source)
        if len(calls) == 1:
            assert read_json(target) == {'status': 'old'}
            error = PermissionError('locked')
            error.winerror = 5
            raise error
        return original(source, destination)

    with patch.object(Path, 'replace', replace), patch('protocol_pipeline.snapshots.time.sleep') as sleep:
        atomic_json(target, {'status': 'new'})
    assert len(calls) == 2
    sleep.assert_called_once_with(.05)
    assert read_json(target) == {'status': 'new'}


@pytest.mark.parametrize('winerror, attempts', [(5, 6), (32, 6), (33, 6), (None, 1)])
def test_persistent_or_unrelated_denial_retains_evidence(tmp_path: Path, winerror: int | None, attempts: int) -> None:
    """Bound retries and retain both previous and pending JSON on failure."""
    target = tmp_path / 'snapshot.json'
    atomic_json(target, {'status': 'old'})
    error = PermissionError('denied')
    if winerror is not None:
        error.winerror = winerror
    with patch.object(Path, 'replace', side_effect=error) as replace, patch('protocol_pipeline.snapshots.time.sleep'):
        with pytest.raises(PermissionError):
            atomic_json(target, {'status': 'new'})
    assert replace.call_count == attempts
    assert read_json(target) == {'status': 'old'}
    assert read_json(target.with_suffix('.tmp')) == {'status': 'new'}
