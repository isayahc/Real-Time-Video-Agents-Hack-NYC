# SPDX-License-Identifier: MPL-2.0
"""Verify pinned robot loading, frame alignment, units and explicit unknown constraints."""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("yourdfpy", reason="Install .[robot] for robot contract tests")
import numpy as np
import trimesh
from pydantic import ValidationError
from yourdfpy import URDF

from protocol_pipeline.robot_contract import (
    OI_FROM_URDF, RobotContract, align_attachment, build_bundle, consumer_frames,
    digest, fetch_sources, load_robot, read_lock, rigid_matrix, set_pose, verify_sources,
)
from protocol_pipeline.seed_benchmark import TrialManifest, validate_manifest

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "examples/so101-robot"
LOCK = CASE / "source-lock.json"
CONTRACT = CASE / "robot-contract.json"


@pytest.fixture(scope="module")
def source_root() -> Path:
    """Use an explicitly prepared upstream cache; CI sets this and cannot silently skip."""
    configured = os.getenv("SO101_SOURCE_ROOT")
    if not configured:
        pytest.skip("Set SO101_SOURCE_ROOT to the pinned cache for real model checks")
    root = Path(configured)
    verify_sources(LOCK, root)
    return root


@pytest.fixture(scope="module")
def loaded(source_root: Path) -> tuple[RobotContract, URDF]:
    """Load the real model once, with hash checks and no network access."""
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Unexpected network")):
        return load_robot(CONTRACT, LOCK, source_root)


def data() -> dict[str, Any]:
    """Load a fresh contract for negative tests."""
    return json.loads(CONTRACT.read_text())


def test_committed_evidence_matches_contract() -> None:
    """Keep checked-in executed reports bound to the actual committed inputs."""
    model = json.loads((CASE / "executed-model-report.json").read_text())
    oi = json.loads((CASE / "executed-oi-report.json").read_text())
    contract = RobotContract.model_validate_json(CONTRACT.read_bytes())
    assert model["contract_sha256"] == oi["robot_contract_sha256"] == digest(CONTRACT)
    assert model["source_lock_sha256"] == digest(LOCK)
    assert model["joints"] == {name: joint.model_dump() for name, joint in contract.joints.items()}
    assert model["reference_link_transforms_m"] == contract.reference_link_transforms_m
    assert model["reference_attachment"]["alignment_max_abs_error"] < 1e-12
    assert oi["maximum_world_vertex_error_m"] < 1e-9
    assert oi["mesh_instances"] == model["mesh_exports"] == 18
    assert not model["physical_attachment_validated"]
    assert not oi["task_simulation_executed"]


def test_pinned_model_names_limits_and_reference_transforms(loaded: tuple[RobotContract, URDF]) -> None:
    """Require actual visual/collision geometry and the source's full kinematic chain."""
    contract, robot = loaded
    set_pose(robot, contract.reference_pose_rad)
    assert set(robot.actuated_joint_names) == {
        "shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"}
    assert len(robot.scene.graph.nodes_geometry) == 17
    # yourdfpy combines each link's collision meshes into one geometry.
    assert len(robot.collision_scene.graph.nodes_geometry) == 7
    assert sum(len(link.collisions) for link in robot.robot.links) == 17
    assert contract.joints["gripper"].lower_rad == -0.174533
    assert contract.joints["gripper"].upper_rad == 1.74533
    assert contract.joints["wrist_roll"].lower_rad == -2.74385
    assert np.allclose(robot.get_transform("gripper_frame_link")[:3, 3],
                       [.39136147022015805, -.00000921206311460634, .22646971024033286], atol=1e-10)
    assert np.allclose(robot.scene.bounds,
                       [[-.030982855742037654, -.05546242713325176, -.0024002597322628503],
                        [.3986340402882503, .05546259874596096, .2656957244868987]], atol=1e-8)


@pytest.mark.parametrize("fraction", [0., .23, .8, 1.])
def test_joint_chain_and_attachment_under_moving_poses(loaded: tuple[RobotContract, URDF], fraction: float) -> None:
    """Cross-check library FK against the exported joint chain at limits and interior poses."""
    contract, robot = loaded
    pose = {name: joint.upper_rad if fraction == 1. else joint.lower_rad + fraction * (joint.upper_rad - joint.lower_rad)
            for name, joint in contract.joints.items() if joint.type == "revolute"}
    set_pose(robot, pose)
    transforms = {contract.root_link: np.eye(4)}
    pending = dict(contract.joints)
    while pending:
        progressed = False
        for name, joint in list(pending.items()):
            if joint.parent not in transforms:
                continue
            rotation = trimesh.transformations.rotation_matrix(pose[name], joint.axis) if joint.type == "revolute" else np.eye(4)
            transforms[joint.child] = transforms[joint.parent] @ np.array(joint.origin_m) @ rotation
            assert np.allclose(transforms[joint.child], robot.get_transform(joint.child), atol=1e-10, rtol=0)
            del pending[name]
            progressed = True
        assert progressed, "Invalid exported joint tree"
    mount = robot.get_transform(contract.mount.parent_link) @ np.array(contract.mount.matrix_m)
    mating = trimesh.transformations.euler_matrix(.2, -.3, .4)
    mating[:3, 3] = [.01, -.02, .03]
    attachment = align_attachment(mount, mating)
    assert np.allclose(attachment @ mating, mount, atol=1e-12, rtol=0)
    assert not np.allclose(attachment, mount)


@pytest.mark.parametrize("mutation", ["missing", "extra", "degrees", "normalized_gripper", "nan", "boolean"])
def test_invalid_joint_commands_rejected(loaded: tuple[RobotContract, URDF], mutation: str) -> None:
    """Do not silently interpret degrees or normalized hardware commands as radians."""
    contract, robot = loaded
    pose = dict(contract.reference_pose_rad)
    if mutation == "missing":
        del pose["gripper"]
    elif mutation == "extra":
        pose["wrong_name"] = 0.
    else:
        pose["gripper"] = {"degrees": 90., "normalized_gripper": 100., "nan": float("nan"), "boolean": True}[mutation]
    with pytest.raises(ValueError):
        set_pose(robot, pose)


@pytest.mark.parametrize("mutation", ["scale", "reflection", "nan", "bottom_row", "shape"])
def test_invalid_transform_rejected(mutation: str) -> None:
    """Reject unit scaling and reflections masquerading as frame transforms."""
    matrix = np.eye(4)
    if mutation == "scale":
        matrix[0, 0] = 1000
    elif mutation == "reflection":
        matrix[0, 0] = -1
    elif mutation == "nan":
        matrix[0, 3] = float("nan")
    elif mutation == "bottom_row":
        matrix[3, 0] = 1
    else:
        matrix = np.eye(3)
    with pytest.raises(ValueError):
        rigid_matrix(matrix.tolist())


def test_consumer_transforms_preserve_points_and_orientation() -> None:
    """Verify mm conversion and both sides of the OI basis change using asymmetric input."""
    transform = trimesh.transformations.euler_matrix(.3, -.4, .6)
    transform[:3, 3] = [.12, -.21, .37]
    frames = consumer_frames(transform)
    cad = np.array(frames["opencad_z_up_mm"])
    oi = np.array(frames["oi_y_up_m"])
    point = np.array([.003, -.004, .007, 1.])
    point_mm = point.copy(); point_mm[:3] *= 1000
    expected_mm = transform @ point; expected_mm[:3] *= 1000
    assert np.allclose(cad @ point_mm, expected_mm)
    assert np.allclose(oi @ OI_FROM_URDF @ point, OI_FROM_URDF @ transform @ point)


@pytest.mark.parametrize("mutation", ["unknown_number", "missing_known_value", "wrong_units", "nonfinite", "extra"])
def test_unknown_constraints_are_not_numeric_defaults(mutation: str) -> None:
    """Unmeasured physical data cannot quietly acquire a fabricated constraint."""
    value = data()
    if mutation == "unknown_number":
        value["maximum_payload"]["value"] = .5
    elif mutation == "missing_known_value":
        value["maximum_payload"]["basis"] = "measured"
    elif mutation == "wrong_units":
        value["maximum_payload"]["unit"] = "m"
    elif mutation == "nonfinite":
        value["reference_pose_rad"]["gripper"] = float("inf")
    else:
        value["physical_attachment_validated"] = True
    with pytest.raises(ValidationError):
        RobotContract.model_validate(value)


def test_virtual_mount_never_certifies_physical_attachment() -> None:
    """Even supplied numerical payloads do not turn a virtual frame into a verified mount."""
    value = data()
    value["maximum_payload"].update(value=.5, basis="measured", source="test-only supplied measurement")
    contract = RobotContract.model_validate(value)
    with pytest.raises(ValueError, match="virtual mount"):
        contract.require_physical_attachment()
    assert contract.maximum_tool_mass.value is None
    assert contract.vacuum_flow_or_control_interface == "not_provided_by_model"


@pytest.mark.parametrize("mutation", ["joint_limit", "joint_name", "reference_frame", "tcp", "source_hash"])
def test_model_contract_drift_rejected(source_root: Path, tmp_path: Path, mutation: str) -> None:
    """Compare the contract to actual source geometry rather than trusting a JSON claim."""
    value = data()
    if mutation == "joint_limit":
        value["joints"]["gripper"]["upper_rad"] = 2.
    elif mutation == "joint_name":
        value["joints"]["renamed"] = value["joints"].pop("gripper")
    elif mutation == "reference_frame":
        value["reference_link_transforms_m"]["wrist_link"][0][3] += .001
    elif mutation == "tcp":
        value["tcp"]["matrix_m"][0][3] += .001
        value["mount"] = copy.deepcopy(value["tcp"])
    else:
        value["source_lock_sha256"] = "0" * 64
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="mismatch|differ"):
        load_robot(path, LOCK, source_root)


def test_missing_and_modified_mesh_rejected(source_root: Path, tmp_path: Path) -> None:
    """Hash verification fails before a loader can silently omit a missing mesh."""
    lock = read_lock(LOCK)
    for name in lock["files"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / name, target)
    mesh = next(tmp_path / name for name in lock["files"] if name.endswith('.stl'))
    mesh.write_bytes(mesh.read_bytes() + b" ")
    with pytest.raises(ValueError, match="mismatch"):
        verify_sources(LOCK, tmp_path)
    mesh.unlink()
    with pytest.raises(FileNotFoundError):
        verify_sources(LOCK, tmp_path)


@pytest.mark.parametrize("change", ["branch", "traversal", "untrusted_repository"])
def test_source_lock_rejects_mutable_or_escaping_inputs(tmp_path: Path, change: str) -> None:
    """Source downloads remain pinned to the declared public model repository."""
    lock = json.loads(LOCK.read_text())
    if change == "branch":
        lock["commit"] = "main"
    elif change == "traversal":
        lock["files"]["../outside"] = next(iter(lock["files"].values()))
    else:
        lock["repository"] = "https://example.org/private"
    path = tmp_path / "source-lock.json"
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError):
        read_lock(path)


def test_fetch_verifies_downloads_and_refuses_overwrite(tmp_path: Path, source_root: Path) -> None:
    """Exercise the fetch path with real pinned bytes and a corrupted response."""
    lock = read_lock(LOCK)
    with patch('urllib.request.urlopen', side_effect=lambda url, timeout: io.BytesIO(
            (source_root / url.split(lock['commit'] + '/', 1)[1]).read_bytes())):
        fetch_sources(LOCK, tmp_path / "downloaded")
    verify_sources(LOCK, tmp_path / "downloaded")
    with patch('urllib.request.urlopen', side_effect=AssertionError("Cache must avoid network")):
        fetch_sources(LOCK, tmp_path / "downloaded")
    (tmp_path / "downloaded/LICENSE").write_text("changed")
    with pytest.raises(ValueError, match="Existing source differs"):
        fetch_sources(LOCK, tmp_path / "downloaded")
    with patch('urllib.request.urlopen', return_value=io.BytesIO(b"corrupt")):
        with pytest.raises(ValueError, match="Downloaded source differs"):
            fetch_sources(LOCK, tmp_path / "bad")
    assert not (tmp_path / "bad/LICENSE").exists()


def test_complete_bundle_and_benchmark_binding(source_root: Path, tmp_path: Path) -> None:
    """Execute the offline export, reopen geometry, verify inputs and keep execution blocked."""
    output = tmp_path / "bundle"
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Unexpected network")):
        report = build_bundle(CONTRACT, LOCK, source_root, output, ROOT / "examples/so101-benchmark/manifest.json")
    assert report["status"] == "model_loaded_and_attachment_aligned"
    assert report["reference_attachment"]["alignment_max_abs_error"] < 1e-12
    assert report["mesh_exports"] == 18
    assert not report["physical_attachment_validated"]
    assert not report["task_simulation_executed"]
    verify_sources(output / "source-lock.json", output / "upstream")
    loaded_glb = trimesh.load_scene(output / "robot-with-reference.glb")
    assert len(loaded_glb.graph.nodes_geometry) == 18
    manifest = TrialManifest.model_validate_json((output / "benchmark-manifest.json").read_bytes())
    assert manifest.components.robot.availability == "materialized"
    assert manifest.evidence_kind == "assumption"
    assert manifest.benchmark.physical.geometry.seed_diameter_mm.value is None
    assert manifest.components.calibration.availability == "definition_only"
    assert validate_manifest(output / "benchmark-manifest.json")["execution_blockers"]
    exported = json.loads((output / "robot.forma.json").read_text())
    assert exported["robot_contract_sha256"] == digest(CONTRACT)
    meshes = exported["project_ir"]["cad_model"]["meshes"]
    points = np.concatenate([np.array(m["vertices"]).reshape(-1, 3) for m in meshes]) / 1000
    assert np.allclose(points.min(axis=0), loaded_glb.bounds[0], atol=1e-7)
    assert np.allclose(points.max(axis=0), loaded_glb.bounds[1], atol=1e-7)
    with pytest.raises(FileExistsError):
        build_bundle(CONTRACT, LOCK, source_root, output)


def test_cli_reports_failure_for_bad_source(tmp_path: Path) -> None:
    """The documented entrypoint fails clearly instead of producing an empty robot."""
    command = [sys.executable, '-m', 'protocol_pipeline.robot_contract', '--lock', str(LOCK),
               '--contract', str(CONTRACT), '--source-root', str(tmp_path / 'absent'),
               '--output', str(tmp_path / 'output')]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'Robot contract validation failed' in result.stderr
    assert not (tmp_path / 'output').exists()
