# SPDX-License-Identifier: MPL-2.0
"""Guard source geometry and clearance sequencing in authored presentation motion."""
from copy import deepcopy

import pytest

from scripts.animate_fastening_concept import compose


def fixture_scene() -> tuple[dict, dict]:
    """Supply minimal test geometry, never used as demo or provider evidence."""
    names = ('x_carriage', 'z_slide', 'spindle_housing', 'rotating_chuck', 'hex_bit')
    parts = [{'id': n, 'metadata': {'sourceId': n},
              'vertices': [-.083, .18, -.0025, -.078, .20, .0025]} for n in names]
    return ({'instances': [{'id': 'machine', 'assetId': 'generated'}],
             'bundledAssets': [{'id': 'generated', 'parts': parts}], 'assets': []},
            {'id': 'reference', 'name': 'test source', 'source': {}, 'dimensions': [1, 1, 1],
             'parts': [{'id': str(i), 'vertices': [i, i+1, i+2]} for i in range(13)]})


def test_original_workpiece_retained_and_traverse_only_while_raised() -> None:
    """Keep every reference vertex fixed while the raised driver moves between targets."""
    scene, asset = fixture_scene()
    before, source_before = deepcopy(scene), deepcopy(asset)
    result, _ = compose(scene, asset)
    assert scene == before and asset == source_before
    assert result['bundledAssets'][-1] == source_before
    assert all(t['instanceId'] == 'machine' for t in result['animation']['tracks'])
    for track in result['animation']['tracks']:
        assert track['id'] == track['instanceId']+':'+track['partId']
        for left, right in zip(track['keys'], track['keys'][1:]):
            if left['position'][0] != right['position'][0]:
                assert left['position'][1] == right['position'][1] == 0
            # Quaternion interpolation must not take a shortcut over whole turns.
            assert abs(right['rotation'][1]-left['rotation'][1]) < 180


def test_incompatible_bit_pose_rejected_before_snapshot_creation() -> None:
    """A changed generated tool cannot silently reuse this reviewed trajectory."""
    scene, asset = fixture_scene()
    scene['bundledAssets'][0]['parts'][-1]['vertices'][0] = .2
    with pytest.raises(ValueError, match='pose contract'):
        compose(scene, asset)
