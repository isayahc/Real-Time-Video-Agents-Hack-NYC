# SPDX-License-Identifier: MPL-2.0
"""Keep targeted inspection inside the existing sample and preserve time boundaries."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.inspect_ha4m_joining import inspect, select_frames
from scripts.sample_ha4m import RECORDINGS


def test_samples_include_last_in_action_and_separate_context() -> None:
    """A half-open interval's end is context, never an in-action frame."""
    selected = select_frames(1221, 1474, 2427)
    assert len(selected) == 11
    assert selected[0] == 1220
    assert selected[1] == 1221
    assert selected[-2:] == [1473, 1474]
    assert len([i for i in selected if 1221 <= i < 1474]) == 9
    assert selected == sorted(set(selected))


def test_short_and_endpoint_intervals_never_leave_recording() -> None:
    """Deduplicate short intervals and omit nonexistent boundary context."""
    assert select_frames(0, 1, 1) == [0]
    assert select_frames(0, 2, 3) == [0, 1, 2]
    assert select_frames(8, 10, 10) == [7, 8, 9]


@pytest.mark.parametrize('interval', [(-1, 2, 3), (1, 1, 3), (2, 1, 3), (0, 4, 3)])
def test_invalid_intervals_fail(interval: tuple[int, int, int]) -> None:
    """Reject out-of-range or reversed evidence requests."""
    with pytest.raises(ValueError):
        select_frames(*interval)


def test_changed_annotation_cannot_trigger_download(tmp_path: Path) -> None:
    """Validate the source contract before fetching any new pictures."""
    source = tmp_path / 'source'
    folder = source / RECORDINGS[0]
    folder.mkdir(parents=True)
    (folder / 'Labels.txt').write_text('0 9 0')
    (folder / 'rgb-listing.xml').write_text('<invalid/>')
    (source / 'manifest.json').write_text(json.dumps({'recordings': [
        {'recording_id': recording, 'labels_sha256': '0' * 64, 'rgb_listing_sha256': '0' * 64}
        for recording in RECORDINGS]}))
    with patch('scripts.inspect_ha4m_joining.fetch') as fetch:
        with pytest.raises(ValueError, match='checksum'):
            inspect(source, tmp_path / 'output')
        fetch.assert_not_called()
    assert not (tmp_path / 'output').exists()
