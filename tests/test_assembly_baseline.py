# SPDX-License-Identifier: MPL-2.0
"""Protect annotation timing and quality boundaries against misleading summaries."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest

from protocol_pipeline.assembly_baseline import summarize_recording, summarize_sample
from scripts.evaluate_ha4m import evaluate
from scripts.sample_ha4m import RECORDINGS, digest


def fixture() -> tuple[str, list[dict]]:
    """Return an artificial repeated-action sequence with duplicated sensor time."""
    return '0 0 0\n1 2 0\n2 2 0\n3 2 1\n4 0 0\n', [
        {'frame_id': i, 'timestamp_us': t}
        for i, t in enumerate([0, 0, 33333, 66666, 100000])]


def test_intervals_preserve_repetitions_background_and_terminal_uncertainty() -> None:
    """Count every frame once, split repetitions, and do not fabricate end time."""
    labels, frames = fixture()
    result = summarize_recording(labels, frames)
    assert sum(row['frame_count'] for row in result['segments']) == 5
    assert [(s['action_id'], s['repetition']) for s in result['segments']] == [(0, 0), (2, 0), (2, 1), (0, 0)]
    assert result['nominal_recording_s'] == 5 / 30
    assert result['device_first_to_last_s'] == 0.1
    assert result['duplicate_timestamp_intervals'] == 1
    assert result['segments'][-1]['device_duration_s'] is None
    assert result['accepted_count'] is None
    assert result['labor_s'] is None
    assert result['missing_action_repetitions']


@pytest.mark.parametrize('labels', ['0 13 0', '0 1 1', '0 11 2', '1 0 0', '0 0', '0 0 0\n0 0 0'])
def test_bad_annotation_contract_fails(labels: str) -> None:
    """Invalid IDs, repetition counts and duplicated/missing frame IDs fail closed."""
    with pytest.raises(ValueError):
        summarize_recording(labels, [{'frame_id': 0, 'timestamp_us': 0}])


def test_alignment_and_time_regression_fail() -> None:
    """Do not turn an incompatible video index into a timing claim."""
    labels, frames = fixture()
    for altered in (frames[:-1], [dict(row, frame_id=row['frame_id'] + 1) for row in frames],
                    [dict(row, timestamp_us=100000 - row['timestamp_us']) for row in frames]):
        with pytest.raises(ValueError):
            summarize_recording(labels, altered)


def test_aggregate_retains_background_and_unknown_acceptance() -> None:
    """Include background in time shares and refuse duplicated recording samples."""
    labels, frames = fixture()
    rows = [dict(summarize_recording(labels, frames), recording_id=str(i)) for i in range(10)]
    original = deepcopy(rows)
    result = summarize_sample(rows)
    assert rows == original
    assert sum(action['share_of_recorded_frames'] for action in result['actions_by_total_time']) == pytest.approx(1)
    assert result['actions_by_total_time'][0]['action_id'] == 2
    assert result['accepted_count'] is None
    assert result['physical_improvement_verified'] is False
    rows[-1]['recording_id'] = '0'
    with pytest.raises(ValueError, match='distinct'):
        summarize_sample(rows)


def test_offline_audit_rebuilds_sources_and_keeps_resource_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Recompute from raw files, reject changed bytes, and never infer accepted yield."""
    def reject_network(*args: object, **kwargs: object) -> None:
        """Fail accidental network access during local evidence analysis."""
        raise AssertionError('Offline audit attempted network access')

    monkeypatch.setattr(socket, 'create_connection', reject_network)
    labels, frames = fixture()
    manifest = {'recordings': []}
    source = tmp_path / 'source'
    for recording in RECORDINGS:
        folder = source / recording
        folder.mkdir(parents=True)
        listing = '<d:multistatus xmlns:d="DAV:">' + ''.join(
            f'<d:response><d:href>/FrameID{f["frame_id"]}_DeviceTimeStamp{f["timestamp_us"]}us.png</d:href></d:response>'
            for f in frames) + '</d:multistatus>'
        (folder / 'Labels.txt').write_bytes(labels.encode())
        (folder / 'rgb-listing.xml').write_bytes(listing.encode())
        manifest['recordings'].append({'recording_id': recording, 'labels_sha256': digest(labels.encode()),
            'rgb_listing_sha256': digest(listing.encode()), 'summary': {'accepted_count': 999}})
    (source / 'manifest.json').write_text(json.dumps(manifest))
    output = tmp_path / 'audit'
    result = evaluate(source, output)
    assert result['accepted_count'] is None
    reports = json.loads((output / 'resource-evaluations.json').read_text())
    assert len(reports) == 10
    for report in reports:
        assert report['acceptance_verified'] is False
        assert report['metrics']['cost_usd_per_accepted']['value'] is None
        assert report['metrics']['labor_s_per_accepted']['value'] is None
    with pytest.raises(FileExistsError):
        evaluate(source, output)
    (source / RECORDINGS[0] / 'Labels.txt').write_text('0 0 0')
    with pytest.raises(ValueError, match='checksum'):
        evaluate(source, tmp_path / 'bad')
