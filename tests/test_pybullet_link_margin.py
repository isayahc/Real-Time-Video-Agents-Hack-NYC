"""Opt-in contact regression for the explicitly patched PyBullet runtime."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv('SO101_MARGIN_RUNTIME_TESTS') != '1',
    reason='Opt-in patched PyBullet margin regression; stock 3.2.7 is expected to fail',
)


@pytest.fixture
def margin_world(tmp_path: Path) -> Iterator[tuple]:
    """Create a mesh child link and nearby sphere without SO-101 source assets."""
    p = pytest.importorskip('pybullet')
    trimesh = pytest.importorskip('trimesh')
    from pybullet_utils.bullet_client import BulletClient

    client = BulletClient(connection_mode=p.DIRECT)
    trimesh.creation.box(extents=[.01, .01, .01]).export(tmp_path / 'cube.stl')
    (tmp_path / 'probe.urdf').write_text('''<robot name="margin-probe">
<link name="base"><inertial><mass value="1"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial>
<collision><geometry><box size="0.01 0.01 0.01"/></geometry></collision></link>
<link name="jaw"><inertial><mass value="0.1"/><inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/></inertial>
<collision><geometry><mesh filename="cube.stl"/></geometry></collision></link>
<joint name="joint" type="fixed"><parent link="base"/><child link="jaw"/><origin xyz="0 0 0.05"/></joint>
</robot>''')
    robot = client.loadURDF(str(tmp_path / 'probe.urdf'), useFixedBase=True)
    sphere = client.createCollisionShape(p.GEOM_SPHERE, radius=.0015)
    obstacle = client.createMultiBody(0, sphere, basePosition=[.0067, 0, .05])
    try:
        yield client, robot, obstacle
    finally:
        client.disconnect()


def test_margin_targets_child_without_changing_base(margin_world: tuple) -> None:
    """A child request must not silently alter the base's margin or friction."""
    p, robot, _ = margin_world
    base_before = p.getDynamicsInfo(robot, -1)
    p.changeDynamics(robot, 0, collisionMargin=.00001, lateralFriction=.73)
    base_after = p.getDynamicsInfo(robot, -1)
    assert base_after[11] == base_before[11]
    assert base_after[1] == base_before[1]
    assert p.getDynamicsInfo(robot, 0)[11] == pytest.approx(.00001)
    assert p.getDynamicsInfo(robot, 0)[1] == pytest.approx(.73)


def test_margin_changes_child_mesh_contact_distance(margin_world: tuple) -> None:
    """Test the child hull's collision response, not just the outer margin getter."""
    p, robot, obstacle = margin_world
    before = min(c[8] for c in p.getClosestPoints(robot, obstacle, .01, linkIndexA=0))
    p.changeDynamics(robot, 0, collisionMargin=.00001)
    after = min(c[8] for c in p.getClosestPoints(robot, obstacle, .01, linkIndexA=0))
    assert before < 0 < after
    assert after - before == pytest.approx(.00099, abs=1e-7)
