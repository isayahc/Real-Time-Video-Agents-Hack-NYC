# SPDX-License-Identifier: MPL-2.0
"""Load a pinned SO-101 model and export a shared, evidence-labeled tool interface.

URDF loading/forward kinematics and geometry use yourdfpy/trimesh. This module
validates contracts and coordinate conversions; it does not drive hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal, Self

import numpy as np
import trimesh
from pydantic import Field, model_validator
from yourdfpy import URDF

from .seed_benchmark import Contract, Digest, Text, TrialManifest, validate_manifest

# OI importForm maps CAD (x,y,z) millimetres to (x,z,-y) metres.
OI_FROM_URDF = np.array([[1., 0., 0., 0.], [0., 0., 1., 0.],
                         [0., -1., 0., 0.], [0., 0., 0., 1.]])


def rigid_matrix(value: list[list[float]]) -> np.ndarray:
    """Require an SE(3) transform, with column vectors and no hidden scale/reflection."""
    matrix = np.asarray(value, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError("Transform must be a finite 4x4 matrix")
    if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-10, rtol=0):
        raise ValueError("Transform must have an affine last row")
    rotation = matrix[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-8, rtol=0) or not math.isclose(np.linalg.det(rotation), 1., abs_tol=1e-8):
        raise ValueError("Transform must be a right-handed rigid rotation")
    return matrix


class Frame(Contract):
    """T_parent_frame maps frame-local coordinates into the named parent in metres."""

    parent_link: Text
    matrix_m: list[list[float]]
    basis: Literal["upstream_model", "protocol_definition"]
    source: Text

    @model_validator(mode="after")
    def rigid(self) -> Self:
        """Reject malformed transforms before any CAD or scene export."""
        rigid_matrix(self.matrix_m)
        return self


class Specification(Contract):
    """Separate source-model quantities from measured, physically usable constraints."""

    value: float | None
    unit: Literal["kg", "m", "V", "A", "Pa"]
    basis: Literal["unknown", "upstream_model", "measured"]
    source: Text

    @model_validator(mode="after")
    def provenance(self) -> Self:
        """Unknown cannot carry a number; a model value is not a physical measurement."""
        if (self.value is None) != (self.basis == "unknown"):
            raise ValueError("Unknown specifications must remain null")
        if self.value is not None and self.value < 0:
            raise ValueError("Specification cannot be negative")
        return self


class JointDefinition(Contract):
    """Source URDF joint definition; dynamic limits are model values, not ratings."""

    type: Literal["fixed", "revolute"]
    parent: Text
    child: Text
    origin_m: list[list[float]]
    axis: list[float] = Field(min_length=3, max_length=3)
    lower_rad: float | None
    upper_rad: float | None
    effort_Nm_model_only: float | None
    velocity_rad_s_model_only: float | None

    @model_validator(mode="after")
    def joint_geometry(self) -> Self:
        """Require a rigid origin and complete, ordered limits for actuated joints."""
        rigid_matrix(self.origin_m)
        limits = (self.lower_rad, self.upper_rad, self.effort_Nm_model_only, self.velocity_rad_s_model_only)
        if self.type == "revolute":
            if any(value is None for value in limits) or self.lower_rad >= self.upper_rad:
                raise ValueError("Revolute joints require ordered limits")
            if not math.isclose(float(np.linalg.norm(self.axis)), 1., abs_tol=1e-8):
                raise ValueError("Revolute joint axis must be normalized")
            if self.effort_Nm_model_only <= 0 or self.velocity_rad_s_model_only <= 0:
                raise ValueError("Model effort and velocity must be positive")
        elif any(value is not None for value in limits):
            raise ValueError("Fixed joints cannot have actuated limits")
        return self


def joint_definition(joint: Any) -> JointDefinition:
    """Read an already parsed yourdfpy joint into the consumer-neutral contract."""
    return JointDefinition(type=joint.type, parent=joint.parent, child=joint.child,
        origin_m=joint.origin.tolist(), axis=joint.axis.tolist(),
        lower_rad=joint.limit.lower if joint.limit else None,
        upper_rad=joint.limit.upper if joint.limit else None,
        effort_Nm_model_only=joint.limit.effort if joint.limit else None,
        velocity_rad_s_model_only=joint.limit.velocity if joint.limit else None)


class RobotContract(Contract):
    """Single SI contract consumed by CAD and OI, with a virtual mounting interface."""

    schema_version: Literal[1]
    robot_id: Literal["so101-follower-new-calibration"]
    source_lock_sha256: Digest
    urdf_sha256: Digest
    length_unit: Literal["m"]
    angle_unit: Literal["rad"]
    mass_unit: Literal["kg"]
    handedness: Literal["right"]
    up_axis: Literal["Z"]
    root_link: Text
    joints: dict[Text, JointDefinition]
    reference_link_transforms_m: dict[Text, list[list[float]]]
    reference_pose_rad: dict[Text, float]
    reference_pose_basis: Text
    mount: Frame
    tcp: Frame
    mount_kind: Literal["virtual_frame_only"]
    mounting_hole_diameter: Specification
    mounting_hole_spacing: Specification
    maximum_payload: Specification
    maximum_tool_mass: Specification
    supply_voltage: Specification
    supply_current: Specification
    vacuum_pressure: Specification
    vacuum_flow_or_control_interface: Literal["not_provided_by_model"]
    gripper_command_mapping: Literal["uncalibrated_do_not_convert_lerobot_0_100_to_radians"]
    limitations: list[Text] = Field(min_length=1)

    @model_validator(mode="after")
    def specification_units(self) -> Self:
        """Reject swapping dimensions, payloads or utility units."""
        for name, unit in (("mounting_hole_diameter", "m"), ("mounting_hole_spacing", "m"),
                           ("maximum_payload", "kg"), ("maximum_tool_mass", "kg"),
                           ("supply_voltage", "V"), ("supply_current", "A"), ("vacuum_pressure", "Pa")):
            if getattr(self, name).unit != unit:
                raise ValueError(f"{name} must use {unit}")
        for matrix in self.reference_link_transforms_m.values():
            rigid_matrix(matrix)
        return self

    def require_physical_attachment(self) -> None:
        """Fail closed: this version defines a model frame, not a verified fastener interface."""
        raise ValueError("Physical attachment is unverified: virtual mount, unknown fasteners, payload and utilities")


def digest(path: Path) -> str:
    """Return the SHA-256 identity of exact file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(root: Path, relative: str) -> Path:
    """Resolve a source-lock path without allowing traversal, absolute paths or symlinks out."""
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes its source root")
    return path


def read_lock(path: Path) -> dict[str, Any]:
    """Validate the lock's fixed upstream, immutable revision and expected file inventory."""
    lock = json.loads(path.read_text())
    if lock.get("repository") != "https://github.com/TheRobotStudio/SO-ARM100":
        raise ValueError("Unexpected upstream repository")
    commit = lock.get("commit", "")
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Upstream revision must be a full commit SHA")
    if lock.get("schema_version") != 1 or lock.get("license") != "Apache-2.0":
        raise ValueError("Unsupported source lock")
    if lock.get("urdf") != "Simulation/SO101/so101_new_calib.urdf":
        raise ValueError("Expected follower new-calibration URDF")
    files = lock.get("files", {})
    if not {lock["urdf"], "LICENSE", "Simulation/SO101/README.md"}.issubset(files):
        raise ValueError("Source lock is missing model, license or documentation")
    for name, metadata in files.items():
        contained(path.parent, name)
        sha = metadata.get("sha256", "")
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("Invalid source digest")
        if type(metadata.get("bytes")) is not int or not 0 < metadata["bytes"] < 50_000_000:
            raise ValueError("Invalid source byte count")
    return lock


def fetch_sources(lock_path: Path, destination: Path) -> None:
    """Explicitly fetch immutable public files; verify bytes before writing each asset."""
    lock = read_lock(lock_path)
    for name, metadata in lock["files"].items():
        target = contained(destination, name)
        if target.exists():
            if digest(target) != metadata["sha256"] or target.stat().st_size != metadata["bytes"]:
                raise ValueError(f"Existing source differs: {name}")
            continue
        url = f"https://raw.githubusercontent.com/TheRobotStudio/SO-ARM100/{lock['commit']}/{name}"
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read(metadata["bytes"] + 1)
        if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
            raise ValueError(f"Downloaded source differs: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)


def verify_sources(lock_path: Path, source_root: Path) -> dict[str, Any]:
    """Verify every upstream byte and require a locked dependency for each URDF mesh."""
    lock = read_lock(lock_path)
    for name, metadata in lock["files"].items():
        file = contained(source_root, name)
        if file.stat().st_size != metadata["bytes"] or digest(file) != metadata["sha256"]:
            raise ValueError(f"Source hash/size mismatch: {name}")
    urdf = contained(source_root, lock["urdf"])
    for mesh in ET.parse(urdf).iter("mesh"):
        asset = contained(urdf.parent, mesh.attrib["filename"])
        if asset.relative_to(source_root.resolve()).as_posix() not in lock["files"]:
            raise ValueError("URDF mesh is not pinned in source lock")
    return lock


def set_pose(robot: URDF, pose: dict[str, float]) -> None:
    """Require exact actuated-joint coverage and enforce model limits in radians."""
    if set(pose) != set(robot.actuated_joint_names):
        raise ValueError("Pose must supply every actuated joint by its exact name")
    for name, value in pose.items():
        limit = robot.joint_map[name].limit
        if isinstance(value, bool) or not math.isfinite(value) or not limit.lower <= value <= limit.upper:
            raise ValueError(f"Joint {name} is outside model radian limits")
    robot.update_cfg(pose)


def load_robot(contract_path: Path, lock_path: Path, source_root: Path) -> tuple[RobotContract, URDF]:
    """Load the actual pinned meshes and check base, joints, reference pose and TCP."""
    contract = RobotContract.model_validate_json(contract_path.read_bytes())
    lock = verify_sources(lock_path, source_root)
    if contract.source_lock_sha256 != digest(lock_path):
        raise ValueError("Contract source lock hash mismatch")
    urdf = contained(source_root, lock["urdf"])
    if contract.urdf_sha256 != digest(urdf):
        raise ValueError("Contract URDF hash mismatch")
    robot = URDF.load(str(urdf), load_collision_meshes=True, build_collision_scene_graph=True)
    if not robot.validate() or robot.base_link != contract.root_link:
        raise ValueError("Invalid robot structure or root frame")
    actual_joints = {j.name: joint_definition(j) for j in robot.robot.joints}
    if contract.joints != actual_joints:
        raise ValueError("Contract joints/limits/transforms differ from pinned URDF")
    set_pose(robot, contract.reference_pose_rad)
    if set(contract.reference_link_transforms_m) != set(robot.link_map):
        raise ValueError("Reference pose must include every link transform")
    for name, expected in contract.reference_link_transforms_m.items():
        if not np.allclose(robot.get_transform(name), expected, atol=1e-10, rtol=0):
            raise ValueError(f"Reference transform mismatch: {name}")
    if not robot.scene.geometry or not np.isfinite(robot.scene.bounds).all():
        raise ValueError("Robot meshes did not load")
    for frame in (contract.mount, contract.tcp):
        if frame.parent_link not in robot.link_map:
            raise ValueError("Interface parent link does not exist")
    source_tcp = robot.get_transform("gripper_frame_link", contract.tcp.parent_link)
    if not np.allclose(source_tcp, contract.tcp.matrix_m, atol=1e-10, rtol=0):
        raise ValueError("TCP differs from pinned upstream gripper frame")
    if contract.mount != contract.tcp:
        raise ValueError("V1 virtual mount must coincide with the modeled TCP")
    return contract, robot


def align_attachment(base_from_mount: np.ndarray, attachment_from_mating: np.ndarray) -> np.ndarray:
    """Solve T_base_attachment so its local mating frame coincides with the robot mount."""
    rigid_matrix(base_from_mount.tolist())
    rigid_matrix(attachment_from_mating.tolist())
    return base_from_mount @ np.linalg.inv(attachment_from_mating)


def consumer_frames(base_from_frame: np.ndarray) -> dict[str, list[list[float]]]:
    """Expose the same frame in OpenCAD millimetres and OI metres/Y-up coordinates."""
    rigid_matrix(base_from_frame.tolist())
    cad = base_from_frame.copy()
    cad[:3, 3] *= 1000
    oi = OI_FROM_URDF @ base_from_frame @ np.linalg.inv(OI_FROM_URDF)
    return {"opencad_z_up_mm": cad.tolist(), "oi_y_up_m": oi.tolist()}


def build_bundle(contract_path: Path, lock_path: Path, source_root: Path, output: Path,
                 benchmark_path: Path | None = None) -> dict[str, Any]:
    """Execute model loading, attachment alignment and exact mesh/contract exports."""
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    contract, robot = load_robot(contract_path, lock_path, source_root)
    lock = read_lock(lock_path)
    base_from_mount = robot.get_transform(contract.mount.parent_link) @ np.array(contract.mount.matrix_m)
    # A deliberately nonidentity mating frame tests both rotation and translation.
    attachment_from_mating = trimesh.transformations.euler_matrix(0, 0, math.pi / 2)
    attachment_from_mating[:3, 3] = [0, 0, -.01]
    base_from_attachment = align_attachment(base_from_mount, attachment_from_mating)
    error = float(np.max(np.abs(base_from_attachment @ attachment_from_mating - base_from_mount)))
    scene = robot.scene.copy()
    marker = trimesh.creation.box(extents=[.004, .006, .020])
    marker.visual.face_colors = [240, 30, 160, 255]
    scene.add_geometry(marker, node_name="reference_attachment", geom_name="reference_attachment",
                       transform=base_from_attachment)
    meshes = []
    for node in sorted(scene.graph.nodes_geometry):
        transform, name = scene.graph[node]
        mesh = scene.geometry[name].copy()
        mesh.apply_transform(transform)
        meshes.append({"name": node, "vertices": (mesh.vertices * 1000).reshape(-1).tolist(),
                       "faces": mesh.faces.reshape(-1).tolist()})
    joints = {name: joint.model_dump() for name, joint in contract.joints.items()}
    transforms = {link: robot.get_transform(link).tolist() for link in robot.link_map}
    # Bounds are in gripper_link coordinates, derived from actual stock-body visuals.
    gripper_meshes = []
    for visual in robot.link_map["gripper_link"].visuals:
        mesh_path = contained((source_root / lock["urdf"]).parent, visual.geometry.mesh.filename)
        mesh = trimesh.load_mesh(mesh_path)
        if visual.geometry.mesh.scale is not None:
            mesh.apply_scale(visual.geometry.mesh.scale)
        mesh.apply_transform(visual.origin)
        gripper_meshes.append(mesh)
    gripper = trimesh.util.concatenate(gripper_meshes)
    report = {"schema_version": 1, "status": "model_loaded_and_attachment_aligned",
              "evidence_kind": "model_kinematics", "contract_sha256": digest(contract_path),
              "upstream_commit": lock["commit"], "source_lock_sha256": digest(lock_path),
              "libraries": {name: version(name) for name in ("yourdfpy", "trimesh", "numpy")},
              "reference_pose_rad": contract.reference_pose_rad, "joints": joints,
              "reference_link_transforms_m": transforms, "robot_bounds_m": robot.scene.bounds.tolist(),
              "stock_gripper_body_bounds_m": gripper.bounds.tolist(),
              "model_mass_kg": sum(link.inertial.mass for link in robot.robot.links if link.inertial),
              "mount_frames": consumer_frames(base_from_mount),
              "reference_attachment": {"purpose": "frame_alignment_marker_not_manufacturable_tool",
                  "extents_m": [.004, .006, .020], "basis": "protocol_definition",
                  "attachment_from_mating_m": attachment_from_mating.tolist(),
                  "base_from_attachment_m": base_from_attachment.tolist(), "alignment_max_abs_error": error},
              "visual_mesh_instances": len(robot.scene.graph.nodes_geometry),
              "collision_mesh_instances": len(robot.collision_scene.graph.nodes_geometry),
              "mesh_exports": len(meshes), "physical_attachment_validated": False,
              "payload_validated": False, "collision_free_verified": False,
              "task_simulation_executed": False, "provider_execution_verified": False,
              "limitations": contract.limitations}
    output.mkdir(parents=True)
    for name in lock["files"]:
        target = output / "upstream" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / name, target)
    shutil.copyfile(contract_path, output / "robot-contract.json")
    shutil.copyfile(lock_path, output / "source-lock.json")
    (output / "robot-with-reference.glb").write_bytes(scene.export(file_type="glb"))
    write_json(output / "robot.forma.json", {"format": "forma-project", "version": 1,
        "title": "SO-101 source model with reference attachment", "project_ir": {
            "hardware_ir_version": "0.2", "cad_model": {"meshes": meshes}},
        "robot_contract_sha256": digest(contract_path)})
    write_json(output / "model-report.json", report)
    if benchmark_path:
        validate_manifest(benchmark_path)
        manifest = TrialManifest.model_validate_json(benchmark_path.read_bytes())
        for role in type(manifest.components).model_fields:
            if role == "robot":
                continue
            identity = getattr(manifest.components, role)
            relative = "benchmark-inputs/" + identity.path
            target = contained(output, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(contained(benchmark_path.parent, identity.path), target)
            identity.path = relative
        manifest.components.robot = manifest.components.robot.model_copy(update={
            "id": contract.robot_id, "version": lock["commit"], "path": "robot-contract.json",
            "sha256": digest(contract_path), "availability": "materialized"})
        write_json(output / "benchmark-manifest.json", manifest.model_dump())
        write_json(output / "benchmark-validation.json", validate_manifest(output / "benchmark-manifest.json"))
    return report


def write_json(path: Path, value: Any) -> None:
    """Write reproducible UTF-8 JSON without permitting nonfinite numbers."""
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    """Fetch explicitly or build from an already cached, hash-verified upstream model."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--benchmark", type=Path)
    args = parser.parse_args()
    try:
        if args.fetch:
            fetch_sources(args.lock, args.source_root)
        if args.output:
            if not args.contract:
                parser.error("--output requires --contract")
            report = build_bundle(args.contract, args.lock, args.source_root, args.output, args.benchmark)
            print(json.dumps({"status": report["status"], "physical_attachment_validated": False}))
        elif not args.fetch:
            parser.error("Supply --fetch or --output")
    except (ValueError, OSError) as error:
        parser.exit(1, f"Robot contract validation failed: {error}\n")


if __name__ == "__main__":
    main()
