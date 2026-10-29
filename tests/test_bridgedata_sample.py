# SPDX-License-Identifier: MPL-2.0
"""Ensure small-sample ingestion cannot silently turn into a bulk download."""
from io import BytesIO

import pytest

from scripts.sample_bridgedata import select_trajectories


def test_selection_stops_after_ten_rows() -> None:
    """Leave all remaining index rows unread and retain annotation separation."""
    rows = [f'raw/test/traj{i}/images0/im_0.jpg,raw/test/traj{i}/images0/im_9.jpg,label\n'.encode()
            for i in range(20)]
    stream = BytesIO(b''.join(rows))
    selected = select_trajectories(stream, 10)
    assert len(selected) == 10
    assert selected[0]['evaluation_only_annotations'] == ['label']
    assert stream.read() == b''.join(rows[10:])


@pytest.mark.parametrize('count', [0, 1, 21, 60096])
def test_count_cannot_exceed_authorized_selection(count: int) -> None:
    """Reject unsupported counts before reading any data."""
    with pytest.raises(ValueError, match='10 or 20'):
        select_trajectories(BytesIO(), count)


@pytest.mark.parametrize('first,last', [
    ('raw/../escape/im_0.jpg', 'raw/../escape/im_2.jpg'),
    ('raw/test/im_0.jpg', 'raw/test/im_99999.jpg'),
    ('raw/test/im_0.jpg', 'raw/other/im_2.jpg'),
])
def test_invalid_or_oversized_trajectory_rejected(first: str, last: str) -> None:
    """Reject traversal, excessive frames and mismatched trajectory boundaries."""
    with pytest.raises(ValueError):
        select_trajectories(BytesIO(f'{first},{last}\n'.encode()), 10)
