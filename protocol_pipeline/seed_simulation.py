# SPDX-License-Identifier: MPL-2.0
"""Execute SO-101 seed attempts in PyBullet; export observations for native OI replay.

Only setup/reset uses state setters. During trials, joint motors and Bullet's
contact solver move bodies: no seed attachment, teleportation or scripted success.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import time
from typing import Any, Literal
import zipfile

import numpy as np
from pydantic import Field, model_validator
import trimesh

from .robot_contract import (
    RobotContract, contained, digest, load_robot, read_lock, rigid_matrix, write_json,
)
from .seed_benchmark import Contract, TrialManifest, validate_manifest

OI_COMMIT = "9b34ec217563e2a6788d5e60d9cc74c0bcd21330"


class SimulationConfig(Contract):
    """Explicit simulation assumptions; none are measured hardware specifications."""

    schema_version: Literal[1] = 1
    timestep_s: float = Field(gt=0, le=1 / 240)
    solver_iterations: int = Field(strict=True, ge=50, le=1000)
    seed_mass_kg: float = Field(gt=0, le=0.001)
    friction: float = Field(ge=0, le=2)
    motor_force_Nm: float = Field(gt=0, le=10)
    motor_velocity_rad_s: float = Field(gt=0, le=2)
    joint_gain: float = Field(gt=0, le=1)
    fixture_xyz_m: list[float] = Field(min_length=3, max_length=3)
    world_from_tray: list[list[float]]
    gripper_open_rad: float
    gripper_closed_rad: float
    approach_height_m: float = Field(gt=0, le=0.1)
    lift_height_m: float = Field(gt=0.01, le=0.1)
    phase_seconds: float = Field(ge=0.5, le=4)
    video_fps: int = Field(strict=True, ge=5, le=30)
    notes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_frames(self) -> SimulationConfig:
        """Require rigid calibration, upright tray, and integral camera sampling."""
        matrix = rigid_matrix(self.world_from_tray)
        if not np.allclose(matrix[:3, 2], [0, 0, 1], atol=1e-10):
            raise ValueError("V1 tray must be horizontal with Z up")
        interval = 1 / (self.timestep_s * self.video_fps)
        if abs(interval - round(interval)) > 1e-8:
            raise ValueError("Video interval must be an integer number of physics steps")
        return self


def pose_matrix(xyz: list[float] | tuple[float, ...], xyzw: list[float] | tuple[float, ...]) -> np.ndarray:
    """Convert Bullet's XYZW quaternion and metre translation to a rigid matrix."""
    x, y, z, w = xyzw
    matrix = trimesh.transformations.quaternion_matrix([w, x, y, z])
    matrix[:3, 3] = xyz
    return matrix


def tray_geometry(manifest: TrialManifest) -> trimesh.Trimesh:
    """Build 72 open cylindrical cups from the benchmark's circular cell geometry.

    Cups are an explicit simulation approximation of a tray, with 1 mm walls and
    floors. The inner radius is enlarged to circumscribe the declared opening;
    the evaluator still uses the exact circular target. No outer tray fit claim.
    """
    g = manifest.benchmark.simulation.geometry
    parts = []
    segments = 32
    inside = g.cell_opening_mm.value / 2000 / math.cos(math.pi / segments)
    depth = g.cell_depth_mm.value / 1000
    for row in range(int(g.rows.value)):
        for col in range(int(g.columns.value)):
            centre = [col * g.pitch_x_mm.value / 1000, row * g.pitch_y_mm.value / 1000, -depth / 2]
            wall = trimesh.creation.annulus(r_min=inside, r_max=inside + .001, height=depth, sections=segments)
            wall.apply_translation(centre)
            floor = trimesh.creation.cylinder(radius=inside + .001, height=.001, sections=segments)
            floor.apply_translation([centre[0], centre[1], -depth - .0005])
            parts.extend([wall, floor])
    return trimesh.util.concatenate(parts)


def assess_placement(manifest: TrialManifest, world_from_tray: np.ndarray,
                     observations: list[dict[str, Any]], target: tuple[int, int],
                     picked_up: bool, collision: bool, timeout: bool) -> dict[str, Any]:
    """Evaluate observed state over the full settling window; never infer seed damage.

    A rigid-body solver has no seed-damage observation. Even a geometric placement
    cannot pass full benchmark acceptance until a damage model is supplied.
    """
    a = manifest.benchmark.simulation
    g = a.geometry
    if not observations:
        raise ValueError("Evaluator requires executed observations")
    radius = g.seed_diameter_mm.value / 2000
    row, col = target
    centre = np.array([col * g.pitch_x_mm.value / 1000, row * g.pitch_y_mm.value / 1000])
    end = observations[-1]["time_s"]
    window = [s for s in observations if s["time_s"] >= end - a.settling_time_s.value - 1e-9]
    covered = end - window[0]["time_s"] >= a.settling_time_s.value - 1e-8
    inverse = np.linalg.inv(world_from_tray)
    local = [inverse @ np.r_[s["seed_xyz_m"], 1] for s in window]
    radial = [float(np.linalg.norm(p[:2] - centre)) for p in local]
    inside = all(d + radius <= g.cell_opening_mm.value / 2000
                 and p[2] + radius <= 0 and p[2] - radius >= -g.cell_depth_mm.value / 1000 - 1e-4
                 for d, p in zip(radial, local))
    settled = all(np.linalg.norm(s["seed_velocity_m_s"]) <= .002 for s in window)
    within = all(d <= a.radial_tolerance_mm.value / 1000 for d in radial)
    geometric = bool(covered and inside and settled and within)
    failure = ("timeout" if timeout else "collision" if collision else "pickup_miss" if not picked_up
               else "invalid_observation" if geometric else "outside_tolerance" if inside else "wrong_cell")
    return {"accepted": False, "failure": failure, "geometric_placement_pass": geometric,
            "picked_up": picked_up, "collision": collision, "timeout": timeout,
            "seed_count": 1, "settling_window_covered": covered, "settled": bool(settled),
            "whole_seed_in_target": bool(inside), "within_radial_tolerance": bool(within),
            "final_seed_in_tray_m": local[-1][:3].tolist(), "final_radial_error_m": radial[-1],
            "damage": "unknown", "damage_observable": False,
            "acceptance_limit": "Rigid-body simulation has no seed-damage model; cannot establish full acceptance"}


def extract_fixture(archive: Path, destination: Path) -> dict[str, Any]:
    """Verify the authored CAD bundle and extract only its checked fixture STL."""
    with zipfile.ZipFile(archive) as z:
        bundle = json.loads(z.read("bundle.json"))
        for name, record in bundle["files"].items():
            content = z.read(name)
            if len(content) != record["bytes"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
                raise ValueError(f"Fixture archive hash mismatch: {name}")
        (destination / "fixture.stl").write_bytes(z.read("machine.stl"))
        return {"bundle_sha256": hashlib.sha256(z.read("bundle.json")).hexdigest(),
                "seed_centre_mm": json.loads(z.read("interfaces.json"))["fixture_from_seed_center"]["opencad_z_up_mm"][2][3],
                "spec": json.loads(z.read("spec.json"))}


class SeedWorld:
    """One isolated Bullet client with deterministic setup, motor control and observations."""

    def __init__(self, contract: RobotContract, source_root: Path, lock_path: Path,
                 manifest: TrialManifest, config: SimulationConfig, assets: Path,
                 fixture: dict[str, Any]) -> None:
        """Load the original URDF and create a single dynamic seed plus static tooling."""
        import pybullet as p
        from pybullet_utils.bullet_client import BulletClient

        self.p = BulletClient(connection_mode=p.DIRECT)
        try:
            self._initialize(contract, source_root, lock_path, manifest, config, assets, fixture)
        except Exception:
            self.close()
            raise

    def _initialize(self, contract: RobotContract, source_root: Path, lock_path: Path,
                    manifest: TrialManifest, config: SimulationConfig, assets: Path,
                    fixture: dict[str, Any]) -> None:
        """Build and verify the world, with cleanup guaranteed by the constructor."""
        p = self.p
        self.contract, self.manifest, self.config = contract, manifest, config
        self.step_index = 0
        self.observations: list[dict[str, Any]] = []
        self.frames: list[dict[str, Any]] = []
        self.collision_seen = False
        self.p.setPhysicsEngineParameter(fixedTimeStep=config.timestep_s,
                                        numSolverIterations=config.solver_iterations,
                                        deterministicOverlappingPairs=1, enableFileCaching=0)
        self.p.setGravity(0, 0, -9.81)
        self.robot = self.p.loadURDF(str(contained(source_root, read_lock(lock_path)["urdf"])),
                                   useFixedBase=True, flags=p.URDF_USE_INERTIA_FROM_FILE | p.URDF_USE_SELF_COLLISION |
                                   p.URDF_USE_SELF_COLLISION_EXCLUDE_PARENT)
        self.links = {"base_link": -1}
        self.joints = {}
        for index in range(self.p.getNumJoints(self.robot)):
            info = self.p.getJointInfo(self.robot, index)
            self.links[info[12].decode()] = index
            if info[2] != p.JOINT_FIXED:
                self.joints[info[1].decode()] = index
        if set(self.joints) != set(contract.reference_pose_rad):
            raise ValueError("Bullet joint mapping differs from robot contract")
        for name, index in self.joints.items():
            definition = contract.joints[name]
            info = self.p.getJointInfo(self.robot, index)
            if not np.allclose(info[8:10], [definition.lower_rad, definition.upper_rad], atol=1e-8):
                raise ValueError("Bullet joint limits differ from pinned robot")
            self.p.resetJointState(self.robot, index, contract.reference_pose_rad[name])
        # URDF origins are link frames, whereas Bullet base poses use inertial frames.
        self.reference_frame_max_error = 0.
        for name, expected in contract.reference_link_transforms_m.items():
            self.reference_frame_max_error = max(self.reference_frame_max_error, float(np.max(np.abs(self.link_pose(name) - expected))))
            # Bullet reports link quaternions at float32 precision.
            if not np.allclose(self.link_pose(name), expected, atol=1e-6, rtol=0):
                raise ValueError(f"Bullet/URDF frame mismatch: {name}: {np.max(np.abs(self.link_pose(name) - expected))}")
        self.environment: dict[str, int] = {}
        for name, mesh_file, xyz, quat, colour in [
            ("tray", "tray.obj", [0, 0, 0], None, [.2, .55, .3, 1]),
            ("fixture", "fixture.obj", config.fixture_xyz_m, [0, 0, 0, 1], [.2, .5, .9, 1]),
            ("support", "support.obj", [0, 0, 0], [0, 0, 0, 1], [.45, .45, .5, 1]),
            ("table", "table.obj", [0, 0, 0], [0, 0, 0, 1], [.65, .61, .52, 1]),
        ]:
            if name == "tray":
                transform = np.asarray(config.world_from_tray)
                xyz = transform[:3, 3].tolist()
                w, x, y, z = trimesh.transformations.quaternion_from_matrix(transform)
                quat = [x, y, z, w]
            collision = self.p.createCollisionShape(p.GEOM_MESH, fileName=str(assets / mesh_file),
                                                   flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
            visual = self.p.createVisualShape(p.GEOM_MESH, fileName=str(assets / mesh_file), rgbaColor=colour)
            body = self.p.createMultiBody(0, collision, visual, xyz, quat)
            self.p.changeDynamics(body, -1, lateralFriction=config.friction, restitution=0, collisionMargin=.00001)
            self.environment[name] = body
        self.seed_initial = np.array(config.fixture_xyz_m) + [0, 0, fixture["seed_centre_mm"] / 1000]
        radius = manifest.benchmark.simulation.geometry.seed_diameter_mm.value / 2000
        collision = self.p.createCollisionShape(p.GEOM_SPHERE, radius=radius)
        visual = self.p.createVisualShape(p.GEOM_SPHERE, radius=radius, rgbaColor=[.9, .15, .05, 1])
        self.seed = self.p.createMultiBody(config.seed_mass_kg, collision, visual, self.seed_initial.tolist())
        self.p.changeDynamics(self.seed, -1, lateralFriction=config.friction, restitution=0,
                              collisionMargin=.00001, ccdSweptSphereRadius=radius / 2,
                              contactProcessingThreshold=0)
        for link in self.links.values():
            self.p.changeDynamics(self.robot, link, lateralFriction=config.friction, restitution=0)
        self.command = dict(contract.reference_pose_rad)
        self.command["gripper"] = config.gripper_open_rad
        for name, angle in self.command.items():
            self.p.resetJointState(self.robot, self.joints[name], angle)
        self.drive(self.command)
        # Settle gravity/contact before cycle start. Reset verification checks the
        # resulting state, never resets the seed again to conceal an unstable seat.
        for _ in range(round(.5 / config.timestep_s)):
            self.p.stepSimulation()
        if np.linalg.norm(np.array(self.p.getBasePositionAndOrientation(self.seed)[0]) - self.seed_initial) > .001:
            raise ValueError("reset_failed: seed did not settle in its presentation seat")
        self.initial_observation = self.observe("ready", record=False)
        home_error = max(abs(self.initial_observation["joint_position_rad"][n] - a) for n, a in self.command.items())
        if home_error > .001 or self.initial_observation["seed_robot_contact_links"] or self.collision_seen:
            raise ValueError("reset_failed: home pose, empty gripper or collision check failed")
        view = self.p.computeViewMatrixFromYawPitchRoll(self.initial_observation["seed_xyz_m"], .085, 30, -30, 0, 2)
        projection = self.p.computeProjectionMatrixFOV(50, 320 / 360, .001, 3)
        segmentation = np.asarray(self.p.getCameraImage(320, 360, view, projection,
                                  renderer=self.p.ER_TINY_RENDERER)[4])
        visible_pixels = int(np.count_nonzero(segmentation == self.seed))
        if visible_pixels == 0:
            raise ValueError("reset_failed: seed not visible in the close-up camera")
        self.reset_report = {"seed_visible_pixels": visible_pixels, "home_max_error_rad": home_error, "seed_position_error_m": float(np.linalg.norm(
            np.array(self.initial_observation["seed_xyz_m"]) - self.seed_initial)),
            "seed_count": 1, "tray_empty": True, "gripper_empty": True, "method": "fresh isolated world"}

    def close(self) -> None:
        """Release this client's physics world without touching other simulations."""
        self.p.disconnect()

    def link_pose(self, name: str) -> np.ndarray:
        """Read a source-link frame, correcting Bullet's base inertial offset."""
        if self.links[name] == -1:
            base = self.p.getBasePositionAndOrientation(self.robot)
            inertia = self.p.getDynamicsInfo(self.robot, -1)
            return pose_matrix(*base) @ np.linalg.inv(pose_matrix(inertia[3], inertia[4]))
        state = self.p.getLinkState(self.robot, self.links[name], computeForwardKinematics=True)
        return pose_matrix(state[4], state[5])

    def drive(self, command: dict[str, float]) -> None:
        """Apply bounded radian position setpoints through physical joint motors."""
        if set(command) != set(self.joints):
            raise ValueError("Action must provide every actuated joint")
        for name, angle in command.items():
            joint = self.contract.joints[name]
            if not math.isfinite(angle) or not joint.lower_rad <= angle <= joint.upper_rad:
                raise ValueError(f"Invalid joint action: {name}")
        for name, angle in command.items():
            self.p.setJointMotorControl2(self.robot, self.joints[name], self.p.POSITION_CONTROL,
                                        targetPosition=angle, force=self.config.motor_force_Nm,
                                        maxVelocity=self.config.motor_velocity_rad_s,
                                        positionGain=self.config.joint_gain, velocityGain=1)
        self.command = dict(command)

    def observe(self, phase: str, *, record: bool = True) -> dict[str, Any]:
        """Read executed positions, velocities, normal forces and unintended contacts."""
        xyz, quaternion = self.p.getBasePositionAndOrientation(self.seed)
        velocity, angular = self.p.getBaseVelocity(self.seed)
        contacts = self.p.getContactPoints(bodyA=self.seed)
        robot_contacts = [c for c in contacts if c[2] == self.robot]
        touched = sorted({c[4] for c in robot_contacts if c[9] > 0})
        unwanted = []
        for body_name, body in self.environment.items():
            for c in self.p.getContactPoints(bodyA=self.robot, bodyB=body):
                if c[3] != -1 and c[8] < -.0001 and c[9] > .001:
                    unwanted.append([body_name, int(c[3]), float(c[8]), float(c[9])])
        for c in self.p.getContactPoints(bodyA=self.robot, bodyB=self.robot):
            if c[8] < -.0001 and c[9] > .001:
                unwanted.append(["self", int(c[3]), float(c[8]), float(c[9])])
        self.collision_seen |= bool(unwanted)
        observation = {"time_s": self.step_index * self.config.timestep_s, "phase": phase,
                       "joint_position_rad": {n: self.p.getJointState(self.robot, j)[0] for n, j in self.joints.items()},
                       "joint_target_rad": dict(self.command), "seed_xyz_m": list(xyz),
                       "seed_xyzw": list(quaternion), "seed_velocity_m_s": list(velocity),
                       "seed_angular_velocity_rad_s": list(angular),
                       "tcp_xyz_m": self.link_pose("gripper_frame_link")[:3, 3].tolist(),
                       "seed_robot_contact_links": touched,
                       "seed_normal_force_N": sum(c[9] for c in contacts), "unwanted_contacts": unwanted}
        if record:
            self.observations.append(observation)
        return observation

    def frame(self, observation: dict[str, Any]) -> dict[str, Any]:
        """Export observed link/seed poses in SI/Z-up for the OI frame adapter."""
        poses = {name: self.link_pose(name).tolist() for name in self.links if name != "gripper_frame_link"}
        poses["seed"] = pose_matrix(observation["seed_xyz_m"], observation["seed_xyzw"]).tolist()
        return {"time_s": observation["time_s"], "phase": observation["phase"], "poses": poses}

    def render(self, phase: str) -> np.ndarray:
        """Render current Bullet state: whole station and a close-up of the tiny seed."""
        from PIL import Image, ImageDraw

        images = []
        seed = self.p.getBasePositionAndOrientation(self.seed)[0]
        for width, target, distance, yaw, pitch in [
            (480, [.17, 0, .05], .8, 45, -40), (320, seed, .085, 30, -30)]:
            view = self.p.computeViewMatrixFromYawPitchRoll(target, distance, yaw, pitch, 0, 2)
            projection = self.p.computeProjectionMatrixFOV(50, width / 360, .001, 3)
            rgba = np.asarray(self.p.getCameraImage(width, 360, view, projection,
                                                  renderer=self.p.ER_TINY_RENDERER)[2], dtype=np.uint8).reshape(360, width, 4)
            images.append(rgba[:, :, :3])
        picture = Image.fromarray(np.concatenate(images, axis=1))
        draw = ImageDraw.Draw(picture)
        draw.rectangle((0, 0, 800, 22), fill="black")
        draw.text((8, 5), f"PyBullet executed state | {phase} | {self.step_index * self.config.timestep_s:.2f}s | seed close-up", fill="white")
        return np.asarray(picture)

    def advance(self, command: dict[str, float], seconds: float, phase: str, writer: Any = None) -> None:
        """Advance a commanded phase, sampling every physics step and camera interval."""
        self.drive(command)
        interval = round(1 / (self.config.timestep_s * self.config.video_fps))
        for _ in range(round(seconds / self.config.timestep_s)):
            if self.step_index >= round(self.manifest.benchmark.simulation.timeout_s.value / self.config.timestep_s):
                raise TimeoutError("Trial reached frozen benchmark timeout")
            self.p.stepSimulation()
            self.step_index += 1
            observation = self.observe(phase)
            if self.step_index % interval == 0:
                self.frames.append(self.frame(observation))
                if writer is not None:
                    writer.append_data(self.render(phase))


class CartesianPlanner:
    """Bounded numerical IK using the pinned URDF FK in a separate kinematic model."""

    def __init__(self, contract: RobotContract, robot: Any) -> None:
        """Retain the loaded model; planning never writes into the Bullet trial world."""
        self.contract, self.robot = contract, robot
        self.names = [n for n in contract.reference_pose_rad if n != "gripper"]
        self.previous = np.zeros(len(self.names))

    def solve(self, xyz: np.ndarray, gripper: float) -> tuple[dict[str, float], float]:
        """Prioritize TCP position, with a soft downward-axis preference and joint limits."""
        from scipy.optimize import least_squares

        def residual(q: np.ndarray) -> np.ndarray:
            """Compute metre position and softly weighted axis residuals from source FK."""
            self.robot.update_cfg({**dict(zip(self.names, q)), "gripper": gripper})
            matrix = self.robot.get_transform("gripper_frame_link")
            return np.r_[matrix[:3, 3] - xyz, .005 * (matrix[:3, 2] - [0, 0, -1])]

        lo = [self.contract.joints[n].lower_rad for n in self.names]
        hi = [self.contract.joints[n].upper_rad for n in self.names]
        alternate = {"shoulder_pan": 0., "shoulder_lift": -.5, "elbow_flex": .5,
                     "wrist_flex": 1.5, "wrist_roll": 0.}
        solutions = [least_squares(residual, guess, bounds=(lo, hi), max_nfev=200,
                                   ftol=1e-9, xtol=1e-9, gtol=1e-9)
                     for guess in [self.previous, np.array([alternate[n] for n in self.names])]]
        solution = min(solutions, key=lambda s: float(np.linalg.norm(s.fun)))
        error = float(np.linalg.norm(residual(solution.x)[:3]))
        self.previous = solution.x
        return {**dict(zip(self.names, map(float, solution.x))), "gripper": gripper}, error


def prepare_assets(manifest: TrialManifest, config: SimulationConfig, robot: Any,
                   source_root: Path, lock_path: Path, fixture_archive: Path,
                   output: Path) -> dict[str, Any]:
    """Export checked collision geometry and local-link CAD meshes for OI replay."""
    assets = output / "assets"
    assets.mkdir()
    fixture = extract_fixture(fixture_archive, assets)
    seat = trimesh.load_mesh(assets / "fixture.stl")
    seat.apply_scale(.001)
    support = trimesh.creation.box(extents=[.04, .03, config.fixture_xyz_m[2]])
    support.apply_translation([*config.fixture_xyz_m[:2], config.fixture_xyz_m[2] / 2])
    table = trimesh.creation.box(extents=[1.0, 1.0, .03])
    table.apply_translation([.15, 0, -.018])
    meshes = {"tray": tray_geometry(manifest), "fixture": seat, "support": support, "table": table}
    for name, mesh in meshes.items():
        mesh.export(assets / f"{name}.obj")
    radius = manifest.benchmark.simulation.geometry.seed_diameter_mm.value / 2000
    meshes["seed"] = trimesh.creation.icosphere(subdivisions=2, radius=radius)
    urdf_dir = contained(source_root, read_lock(lock_path)["urdf"]).parent
    for name, link in robot.link_map.items():
        parts = []
        for visual in link.visuals:
            mesh = trimesh.load_mesh(contained(urdf_dir, visual.geometry.mesh.filename))
            if visual.geometry.mesh.scale is not None:
                mesh.apply_scale(visual.geometry.mesh.scale)
            mesh.apply_transform(visual.origin)
            parts.append(mesh)
        if parts:
            meshes[name] = trimesh.util.concatenate(parts)
    # CAD document is in link-local Z-up millimetres; each replay item gets its
    # executed Bullet world transform, with OI's recentering explicitly corrected.
    for name, mesh in meshes.items():
        write_json(assets / f"{name}.forma.json", {"title": name, "project_ir": {"cad_model": {"meshes": [
            {"name": name, "vertices": (mesh.vertices * 1000).reshape(-1).tolist(),
             "faces": mesh.faces.reshape(-1).tolist()}]}}})
    write_json(assets / "static-poses.json", {"tray": config.world_from_tray,
               "fixture": pose_matrix(config.fixture_xyz_m, [0, 0, 0, 1]).tolist(),
               "support": np.eye(4).tolist(), "table": np.eye(4).tolist()})
    return fixture


def materialize_manifest(definition: TrialManifest, config: SimulationConfig, contract_path: Path,
                         lock_path: Path, fixture_archive: Path, output: Path) -> TrialManifest:
    """Pin all seven runtime components while preserving the frozen benchmark definition."""
    artifacts = output / "artifacts"
    artifacts.mkdir()
    (artifacts / "executed_implementation.py").write_bytes(Path(__file__).read_bytes())
    (artifacts / "source-lock.json").write_bytes(lock_path.read_bytes())
    code_hash = digest(artifacts / "executed_implementation.py")
    records = {
        "robot": json.loads(contract_path.read_text()),
        "tool": {"kind": "unaltered_stock_urdf_gripper", "source_lock_sha256": digest(lock_path),
                 "open_rad": config.gripper_open_rad, "closed_rad": config.gripper_closed_rad},
        "policy": {"kind": "bounded_fk_ik_position_motor_baseline_v1", "implementation_sha256": code_hash,
                   "config": config.model_dump(), "no_retry": True, "seed_attachment": False},
        "evaluator": {"kind": "observed_state_settling_window_v1", "implementation_sha256": code_hash,
                      "damage_observable": False, "can_establish_full_acceptance": False,
                      "settled_speed_limit_m_s": .002, "floor_penetration_tolerance_m": .0001},
        "environment": {"kind": "pybullet_rigidbody", "config": config.model_dump(),
                        "fixture_archive_sha256": digest(fixture_archive),
                        "assets": {p.name: digest(p) for p in sorted((output / "assets").glob("*.obj"))},
                        "libraries": {n: version(n) for n in ("pybullet", "numpy", "scipy", "yourdfpy", "trimesh")}},
        "calibration": {"basis": "simulation_assumption", "world_from_tray": config.world_from_tray,
                        "fixture_xyz_m": config.fixture_xyz_m,
                        "home_rad": {**json.loads(contract_path.read_text())["reference_pose_rad"], "gripper": config.gripper_open_rad},
                        "oi_basis": "Y-up metres [x,z,-y]", "oi_commit": OI_COMMIT},
        "cameras": {"kind": "pybullet_tiny_renderer", "video_fps": config.video_fps,
                    "size_px": [800, 360], "wide": {"target": [.17, 0, .05], "distance_m": .8, "yaw_deg": 45, "pitch_deg": -40},
                    "closeup": {"target": "observed_seed", "distance_m": .085, "yaw_deg": 30, "pitch_deg": -30},
                    "fov_deg": 50, "near_m": .001, "far_m": 3}}
    payload = definition.model_dump()
    payload.update(experiment_id="so101-pybullet-stock-baseline-v1", evidence_kind="simulation", execution_requested=True)
    for name, record in records.items():
        path = artifacts / f"{name}.json"
        write_json(path, record)
        payload["components"][name] = {"id": f"so101-runtime-{name}", "version": "1", "availability": "materialized",
                                        "path": str(path.relative_to(output)), "sha256": digest(path)}
    write_json(output / "manifest.json", payload)
    validate_manifest(output / "manifest.json")
    return TrialManifest.model_validate_json((output / "manifest.json").read_text())


def execute_trial(world: SeedWorld, planner: CartesianPlanner, target: tuple[int, int],
                  trial_seed: int, output: Path, *, keep_open: bool = False, video: bool = True) -> dict[str, Any]:
    """Execute one attempt through motors, stopping on missed pickup without retrying."""
    import imageio.v2 as imageio

    output.mkdir()
    # Frozen v1 has no random perturbations. Retain explicit reseeding for schedule identity.
    np.random.seed(trial_seed)
    cfg, manifest = world.config, world.manifest
    initial = world.initial_observation
    world.observations.append(initial)
    world.frames.append(world.frame(initial))
    pickup = np.array(initial["seed_xyz_m"])
    planner_errors = []
    picked_up = False
    timed_out = False
    writer = imageio.get_writer(output / "trial.mp4", fps=cfg.video_fps, codec="libx264", macro_block_size=1) if video else None

    def move(xyz: np.ndarray, opening: float, phase: str) -> None:
        """Plan bounded setpoints, retaining unreachable residuals rather than hiding them."""
        command, error = planner.solve(xyz, opening)
        planner_errors.append({"phase": phase, "target_xyz_m": xyz.tolist(), "ik_position_error_m": error})
        world.advance(command, cfg.phase_seconds, phase, writer)

    try:
        if writer is not None:
            writer.append_data(world.render("ready"))
        move(pickup + [0, 0, cfg.approach_height_m], cfg.gripper_open_rad, "approach")
        move(pickup, cfg.gripper_open_rad, "descend")
        command = dict(world.command)
        command["gripper"] = cfg.gripper_open_rad if keep_open else cfg.gripper_closed_rad
        world.advance(command, 1, "close_suppressed" if keep_open else "close", writer)
        move(pickup + [0, 0, cfg.lift_height_m], command["gripper"], "lift")
        # Require sustained bilateral contact AND an actual rise while near the TCP.
        lift_window = [s for s in world.observations if s["phase"] == "lift"][-24:]
        fingers = {world.links["gripper_link"], world.links["moving_jaw_so101_v1_link"]}
        picked_up = bool(lift_window) and all(
            fingers.issubset(s["seed_robot_contact_links"]) and s["seed_xyz_m"][2] > pickup[2] + .01
            and np.linalg.norm(np.array(s["seed_xyz_m"]) - s["tcp_xyz_m"]) < .02 for s in lift_window)
        if picked_up:
            geometry = manifest.benchmark.simulation.geometry
            row, col = target
            destination = (np.asarray(cfg.world_from_tray) @ [col * geometry.pitch_x_mm.value / 1000,
                           row * geometry.pitch_y_mm.value / 1000, .02, 1])[:3]
            move(destination + [0, 0, cfg.lift_height_m], command["gripper"], "transport")
            move(destination, command["gripper"], "place")
            opened = {**world.command, "gripper": cfg.gripper_open_rad}
            world.advance(opened, 1, "release", writer)
            move(destination + [0, 0, cfg.lift_height_m], cfg.gripper_open_rad, "retract")
            world.advance({**world.contract.reference_pose_rad, "gripper": cfg.gripper_open_rad},
                          cfg.phase_seconds, "home", writer)
        world.advance(world.command, manifest.benchmark.simulation.settling_time_s.value, "settle", writer)
    except TimeoutError:
        timed_out = True
    finally:
        if writer is not None:
            writer.close()
        with (output / "trajectory.jsonl").open("w") as stream:
            for observation in world.observations:
                stream.write(json.dumps(observation, allow_nan=False, separators=(",", ":")) + "\n")
        write_json(output / "frames.json", world.frames)
    duration = world.observations[-1]["time_s"]
    result = assess_placement(manifest, np.asarray(cfg.world_from_tray), world.observations, target,
                              picked_up, world.collision_seen, timed_out or duration >= manifest.benchmark.simulation.timeout_s.value)
    result.update(trial_seed=trial_seed, target=list(target), intervention="keep_gripper_open" if keep_open else "none",
                  evidence_kind="simulation", cycle_seconds=duration, physics_steps=world.step_index,
                  reset_verified=True, reset_in_cycle=False, reset=world.reset_report, planner=planner_errors,
                  reference_frame_max_matrix_error=world.reference_frame_max_error,
                  maximum_joint_motion_rad=max(abs(s["joint_position_rad"][n] - initial["joint_position_rad"][n])
                                               for s in world.observations for n in world.joints),
                  final_seed_lift_m=world.observations[-1]["seed_xyz_m"][2] - pickup[2])
    write_json(output / "result.json", result)
    return result


def trajectory_difference(first: Path, second: Path) -> float:
    """Compare every recorded executed state and action, not merely final acceptance."""
    a = [json.loads(line) for line in first.read_text().splitlines()]
    b = [json.loads(line) for line in second.read_text().splitlines()]
    if len(a) != len(b):
        return math.inf
    maximum = 0.
    for left, right in zip(a, b):
        if left["phase"] != right["phase"] or left["seed_robot_contact_links"] != right["seed_robot_contact_links"]:
            return math.inf
        for key in ("joint_position_rad", "joint_target_rad", "seed_xyz_m", "seed_xyzw", "seed_velocity_m_s", "tcp_xyz_m"):
            x, y = left[key], right[key]
            if isinstance(x, dict):
                x, y = [x[n] for n in sorted(x)], [y[n] for n in sorted(y)]
            maximum = max(maximum, float(np.max(np.abs(np.asarray(x) - np.asarray(y)))))
    return maximum


def run(config_path: Path, benchmark_path: Path, contract_path: Path, lock_path: Path,
        source_root: Path, fixture_archive: Path, output: Path, *, video: bool = True,
        smoke: bool = False) -> dict[str, Any]:
    """Run the frozen schedule, negative control and fresh-world repeat, retaining failures."""
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    config = SimulationConfig.model_validate_json(config_path.read_text())
    validate_manifest(benchmark_path)
    definition = TrialManifest.model_validate_json(benchmark_path.read_text())
    contract, robot = load_robot(contract_path, lock_path, source_root)
    output.mkdir(parents=True)
    fixture = prepare_assets(definition, config, robot, source_root, lock_path, fixture_archive, output)
    manifest = materialize_manifest(definition, config, contract_path, lock_path, fixture_archive, output)
    schedule = [(seed, (target.row, target.column)) for seed in manifest.trial_seeds for target in manifest.targets]
    if smoke:
        schedule = schedule[:1]
    results = []
    cases = [(f"trial-{index:02d}", seed, target, False) for index, (seed, target) in enumerate(schedule)]
    cases.extend([( "negative-open", *schedule[0], True), ("repeat-00", *schedule[0], False)])
    for name, seed, target, keep_open in cases:
        start = time.monotonic()
        try:
            world = SeedWorld(contract, source_root, lock_path, manifest, config, output / "assets", fixture)
            reset_wall_seconds = time.monotonic() - start
        except Exception as error:
            write_json(output / "aborted.json", {"case": name, "failure": "reset_failed", "error": str(error),
                                                "remaining_trials_aborted": True})
            raise
        try:
            planner = CartesianPlanner(contract, robot)
            result = execute_trial(world, planner, target, seed, output / name, keep_open=keep_open, video=video)
            result["case"] = name
            result["reset_wall_seconds"] = reset_wall_seconds
            result["setup_and_execution_wall_seconds"] = time.monotonic() - start
            results.append(result)
            print(json.dumps({"case": name, "failure": result["failure"], "picked_up": result["picked_up"],
                              "cycle_seconds": result["cycle_seconds"]}), flush=True)
        except Exception as error:
            write_json(output / "aborted.json", {"case": name, "failure": "execution_error", "error": str(error),
                                                "remaining_trials_aborted": True})
            raise
        finally:
            world.close()
    difference = trajectory_difference(output / "trial-00/trajectory.jsonl", output / "repeat-00/trajectory.jsonl")
    negative = next(r for r in results if r["case"] == "negative-open")
    summary = {"status": "executed", "evidence_kind": "simulation", "schedule_complete": not smoke,
               "nominal_trials": len(schedule), "results": results, "repeat_max_state_difference": difference,
               "repeat_passed": difference <= 1e-9,
               "deliberate_failure_passed": not negative["accepted"] and not negative["picked_up"],
               "runtime_manifest_sha256": digest(output / "manifest.json"),
               "video_recorded": video,
               "physical_execution": False, "live_provider_execution": False,
               "limitations": config.notes + ["Native OI replay verification is a separate required bridge step."]}
    write_json(output / "summary.json", summary)
    if not summary["repeat_passed"] or not summary["deliberate_failure_passed"]:
        raise ValueError("Executed repeat or negative control failed; inspect retained artifacts")
    return summary



def verify_output(output: Path) -> dict[str, Any]:
    """Require full executed evidence and native OI replay, then hash the retained bundle."""
    import imageio.v2 as imageio

    validate_manifest(output / "manifest.json")
    manifest = TrialManifest.model_validate_json((output / "manifest.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    oi = json.loads((output / "oi-report.json").read_text())
    policy = json.loads((output / "artifacts/policy.json").read_text())
    if digest(output / "artifacts/executed_implementation.py") != policy["implementation_sha256"]:
        raise ValueError("Executed source snapshot does not match runtime policy")
    schedule = [(seed, [target.row, target.column]) for seed in manifest.trial_seeds for target in manifest.targets]
    if (not summary["schedule_complete"] or not summary["video_recorded"] or not summary["repeat_passed"]
            or not summary["deliberate_failure_passed"] or len(summary["results"]) != len(schedule) + 2):
        raise ValueError("Incomplete executed schedule, repeat, negative control or video")
    expected_names = [f"trial-{i:02d}" for i in range(len(schedule))] + ["negative-open", "repeat-00"]
    if [r["case"] for r in summary["results"]] != expected_names:
        raise ValueError("Executed case identity mismatch")
    if oi["status"] != "native_oi_executed_replay_verified" or oi["oi_commit"] != OI_COMMIT:
        raise ValueError("Native OI replay verification missing or wrong revision")
    reports = {r["case"]: r for r in oi["reports"]}
    if set(reports) != set(expected_names):
        raise ValueError("OI verification does not cover every executed case")
    for index, result in enumerate(summary["results"]):
        directory = output / result["case"]
        if index < len(schedule) and (result["trial_seed"], result["target"]) != schedule[index]:
            raise ValueError("Executed schedule differs from frozen manifest")
        if (digest(directory / "replay.oi.json") != reports[result["case"]]["replay_sha256"]
                or digest(directory / "frames.json") != reports[result["case"]]["executed_frames_sha256"]):
            raise ValueError("OI replay is not bound to executed frames")
        stored_result = json.loads((directory / "result.json").read_text())
        if any(result[key] != value for key, value in stored_result.items()):
            raise ValueError("Per-trial result disagrees with summary")
        trace = [json.loads(line) for line in (directory / "trajectory.jsonl").read_text().splitlines()]
        checked = assess_placement(manifest, np.asarray(policy["config"]["world_from_tray"]), trace,
                                   tuple(result["target"]), result["picked_up"], result["collision"], result["timeout"])
        if any(result[key] != value for key, value in checked.items()):
            raise ValueError("Stored evaluator outcome differs from recorded observations")
        if result["case"] == "negative-open" and any(
                s["joint_target_rad"]["gripper"] != policy["config"]["gripper_open_rad"] for s in trace):
            raise ValueError("Negative control did not hold the gripper open")
        reader = imageio.get_reader(directory / "trial.mp4")
        try:
            if reader.count_frames() != reports[result["case"]]["frame_count"] or reader.get_meta_data()["size"] != (800, 360):
                raise ValueError("Video does not cover the recorded frames")
        finally:
            reader.close()
    if trajectory_difference(output / "trial-00/trajectory.jsonl", output / "repeat-00/trajectory.jsonl") > 1e-9:
        raise ValueError("Executed reset repeat is not deterministic")
    files = {str(p.relative_to(output)): {"sha256": digest(p), "bytes": p.stat().st_size}
             for p in sorted(output.rglob("*")) if p.is_file() and p.name != "evidence.json"}
    report = {"status": "executed_evidence_verified", "evidence_kind": "simulation", "files": files,
              "nominal_trials": len(schedule), "negative_controls": 1, "reset_repeats": 1,
              "physical_execution": False, "live_provider_execution": False}
    destination = output / "evidence.json"
    if destination.exists():
        if json.loads(destination.read_text()) != report:
            raise ValueError("Retained evidence changed after hashing")
    else:
        write_json(destination, report)
    print(json.dumps({k: v for k, v in report.items() if k != "files"}), flush=True)
    return report


def main() -> None:
    """Execute the baseline using explicit local source inputs and a fresh output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("examples/so101-simulation/config.json"))
    parser.add_argument("--benchmark", type=Path, default=Path("examples/so101-benchmark/manifest.json"))
    parser.add_argument("--contract", type=Path, default=Path("examples/so101-robot/robot-contract.json"))
    parser.add_argument("--lock", type=Path, default=Path("examples/so101-robot/source-lock.json"))
    parser.add_argument("--fixture", type=Path, default=Path("examples/so101-fixture/candidate-v1.zip"))
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-output", type=Path, help="Verify and hash a complete executed bundle after OI replay")
    parser.add_argument("--no-video", action="store_true", help="Diagnostic only; not completion evidence")
    parser.add_argument("--smoke", action="store_true", help="Only first pair plus repeat/negative; not full schedule")
    args = parser.parse_args()
    if args.verify_output:
        verify_output(args.verify_output)
        return
    if args.source_root is None or args.output is None:
        parser.error("Execution requires --source-root and --output")
    run(args.config, args.benchmark, args.contract, args.lock, args.source_root, args.fixture,
        args.output, video=not args.no_video, smoke=args.smoke)


if __name__ == "__main__":
    main()
