# SPDX-License-Identifier: MPL-2.0
"""Regression checks for observed outcomes and the real motor-driven baseline."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("yourdfpy")
import numpy as np

from protocol_pipeline.seed_benchmark import TrialManifest, validate_manifest
from protocol_pipeline.seed_simulation import SimulationConfig, assess_placement, run, trajectory_difference
from protocol_pipeline.seed_simulation import execute_trial, release_tracking_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def manifest() -> TrialManifest:
    """Load the immutable benchmark definition."""
    return TrialManifest.model_validate_json((ROOT / "examples/so101-benchmark/manifest.json").read_text())


def observations(xyz: list[float], *, speed: float = 0, duration: float = 1) -> list[dict]:
    """Build evaluator input only; these synthetic observations are never execution evidence."""
    return [{"time_s": float(t), "seed_xyz_m": xyz, "seed_velocity_m_s": [speed, 0, 0]}
            for t in np.linspace(0, duration, 241)]


def test_geometric_placement_cannot_imply_damage_acceptance(manifest: TrialManifest) -> None:
    """A centred, settled seed still lacks a damage channel."""
    result = assess_placement(manifest, np.eye(4), observations([0, 0, -.0385]), (0, 0), True, False, False)
    assert result["geometric_placement_pass"]
    assert not result["accepted"]
    assert result["damage"] == "unknown"
    assert result["failure"] == "invalid_observation"


@pytest.mark.parametrize("xyz,speed,duration", [([.006, 0, -.0385], 0, 1), ([0, 0, .001], 0, 1),
                                               ([0, 0, -.045], 0, 1), ([0, 0, -.0385], .003, 1),
                                               ([0, 0, -.0385], 0, .5)])
def test_reject_outside_unsettled_or_incomplete_window(manifest: TrialManifest, xyz: list[float],
                                                      speed: float, duration: float) -> None:
    """Fail tolerance, rim, floor, velocity and incomplete settling independently."""
    result = assess_placement(manifest, np.eye(4), observations(xyz, speed=speed, duration=duration), (0, 0), True, False, False)
    assert not result["geometric_placement_pass"]
    assert not result["accepted"]


def test_transform_and_full_window(manifest: TrialManifest) -> None:
    """Use the tray frame and the full interval, not a convenient last sample."""
    transform = np.array([[0, -1, 0, .35], [1, 0, 0, -.22], [0, 0, 1, .06], [0, 0, 0, 1]])
    xyz = (transform @ [.2, .08, -.0385, 1])[:3].tolist()
    data = observations(xyz)
    assert assess_placement(manifest, transform, data, (2, 5), True, False, False)["geometric_placement_pass"]
    data[10]["seed_xyz_m"] = [.8, .8, .8]
    assert not assess_placement(manifest, transform, data, (2, 5), True, False, False)["geometric_placement_pass"]


@pytest.mark.parametrize("picked,collision,timeout,failure", [(False, False, False, "pickup_miss"),
                         (False, True, False, "collision"), (False, True, True, "timeout")])
def test_failure_precedence(manifest: TrialManifest, picked: bool, collision: bool, timeout: bool, failure: str) -> None:
    """Preserve observed failure causes rather than inventing success from a target."""
    assert assess_placement(manifest, np.eye(4), observations([.4, .4, .1]), (0, 0), picked, collision, timeout)["failure"] == failure


def test_config_rejects_invalid_frame_and_camera_rate() -> None:
    """Reject scale transforms and camera timing that cannot align with physics."""
    raw = json.loads((ROOT / "examples/so101-simulation/config.json").read_text())
    raw["world_from_tray"][0][0] = 2
    with pytest.raises(ValueError):
        SimulationConfig.model_validate(raw)
    raw = json.loads((ROOT / "examples/so101-simulation/config.json").read_text())
    raw["video_fps"] = 17
    with pytest.raises(ValueError):
        SimulationConfig.model_validate(raw)
    raw = json.loads((ROOT / "examples/so101-simulation/config.json").read_text())
    raw["physics_substeps"] = 4
    with pytest.raises(ValueError):
        SimulationConfig.model_validate(raw)


def test_executed_baseline_reset_negative_and_repeat(tmp_path: Path) -> None:
    """Run real Bullet motor/contact steps; inspect actions and observations after reset."""
    pytest.importorskip("pybullet")
    source = os.environ.get("SO101_SOURCE_ROOT")
    if not source:
        pytest.skip("Set SO101_SOURCE_ROOT to the hash-verified source model")
    output = tmp_path / "executed"
    summary = run(ROOT / "examples/so101-simulation/config.json", ROOT / "examples/so101-benchmark/manifest.json",
                  ROOT / "examples/so101-robot/robot-contract.json", ROOT / "examples/so101-robot/source-lock.json",
                  Path(source), ROOT / "examples/so101-fixture/candidate-v1.zip", output, video=False, smoke=True)
    assert summary["repeat_passed"] and summary["deliberate_failure_passed"]
    assert summary["repeat_max_state_difference"] == 0
    assert not summary["schedule_complete"] and not summary["video_recorded"]
    validate_manifest(output / "manifest.json")
    nominal = [json.loads(line) for line in (output / "trial-00/trajectory.jsonl").read_text().splitlines()]
    negative = [json.loads(line) for line in (output / "negative-open/trajectory.jsonl").read_text().splitlines()]
    assert len(nominal) > 1000
    assert summary["results"][0]["maximum_joint_motion_rad"] > .5
    assert any(s["joint_target_rad"]["gripper"] == 0 for s in nominal)
    assert all(s["joint_target_rad"]["gripper"] == .8 for s in negative)
    assert trajectory_difference(output / "trial-00/trajectory.jsonl", output / "negative-open/trajectory.jsonl") > .1
    assert all(not s["accepted"] and not s["damage_observable"] for s in summary["results"])
    # Modifying an executed observation must break repeat verification.
    repeat = output / "repeat-00/trajectory.jsonl"
    data = [json.loads(line) for line in repeat.read_text().splitlines()]
    data[300]["seed_xyz_m"][0] += .01
    repeat.write_text("\n".join(json.dumps(row) for row in data))
    assert trajectory_difference(output / "trial-00/trajectory.jsonl", repeat) >= .009


@pytest.mark.parametrize("invalid", ["missing", "nan", "outside"])
def test_invalid_action_rejected_before_motor_call(invalid: str) -> None:
    """An invalid partial or nonfinite command must not partially actuate the robot."""
    from protocol_pipeline.robot_contract import RobotContract
    from protocol_pipeline.seed_simulation import SeedWorld

    world = SeedWorld.__new__(SeedWorld)
    world.contract = RobotContract.model_validate_json((ROOT / "examples/so101-robot/robot-contract.json").read_text())
    world.joints = {name: index for index, name in enumerate(world.contract.reference_pose_rad)}
    # No physics client is assigned: reaching a motor API would fail the test.
    command = dict(world.contract.reference_pose_rad)
    if invalid == "missing":
        command.pop("gripper")
    else:
        command["gripper"] = float("nan") if invalid == "nan" else 20.0
    with pytest.raises(ValueError, match="Action must|Invalid joint"):
        world.drive(command)


@pytest.mark.parametrize("fault", [None, "position", "joint", "missing", "nan", "short"])
def test_release_requires_sustained_measured_tracking(fault: str | None) -> None:
    """Reject target misses, a transient joint error, missing data and short windows."""
    cfg = SimulationConfig.model_validate_json((ROOT / "examples/so101-comparison/config.json").read_text())
    samples = [{"time_s": float(t), "phase": "place", "grasp_xyz_m": [.1, .2, .08],
                "joint_position_rad": {"joint": 0.}, "joint_target_rad": {"joint": 0.}}
               for t in np.linspace(0, .1, 25)]
    if fault == "position":
        samples[10]["grasp_xyz_m"][2] -= .019
    elif fault == "joint":
        samples[10]["joint_position_rad"]["joint"] = .1
    elif fault == "missing":
        samples[10].pop("grasp_xyz_m")
    elif fault == "nan":
        samples[10]["joint_position_rad"]["joint"] = float("nan")
    elif fault == "short":
        samples = samples[1:]
    world = SimpleNamespace(config=cfg, observations=samples, joints={"joint": 0})
    report = release_tracking_report(world, np.array([.1, .2, .08]))
    assert report["passed"] is (fault is None)
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("placement_tracks", [False, True])
def test_release_is_conditional_on_placement_tracking(tmp_path: Path, manifest: TrialManifest,
                                                     placement_tracks: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise both release and failure-stop paths after synthetic pickup."""
    cfg = SimulationConfig.model_validate_json((ROOT / "examples/so101-comparison/config.json").read_text())
    # Offline CI has no video extras; both control paths must work without them.
    monkeypatch.setitem(sys.modules, "imageio", None)
    monkeypatch.setitem(sys.modules, "imageio.v2", None)

    class MotorSpy:
        """Synthetic control-flow fixture, not simulation evidence."""

        def __init__(self) -> None:
            """Supply the minimal trial interface and record every phase."""
            self.config, self.manifest = cfg, manifest
            self.command = {"gripper": cfg.gripper_open_rad}
            self.joints = {"gripper": 0}
            self.links = {"gripper_link": 4, "moving_jaw_so101_v1_link": 6}
            self.contract = SimpleNamespace(reference_pose_rad=dict(self.command))
            self.observations, self.frames, self.phases = [], [], []
            self.collision_seen = False
            self.reset_report = {}
            self.reference_frame_max_error = 0.
            self.step_index = 0
            self.initial_observation = self.sample(0., "ready")

        def sample(self, time_s: float, phase: str) -> dict:
            """Use a lifted seed but an erroneous measured placement point."""
            grasp = [.35, -.22, .08] if placement_tracks and phase == "place" else [0, 0, .1]
            return {"time_s": time_s, "phase": phase, "seed_xyz_m": [0, 0, .1 if phase != "ready" else .07],
                    "tcp_xyz_m": [0, 0, .1], "grasp_xyz_m": grasp,
                    "seed_velocity_m_s": [0, 0, 0], "seed_robot_contact_links": [4, 6],
                    "joint_position_rad": dict(self.command), "joint_target_rad": dict(self.command)}

        def frame(self, observation: dict) -> dict:
            """Frames are irrelevant to this orchestration test."""
            return {}

        def advance(self, command: dict, seconds: float, phase: str, writer: object = None) -> None:
            """Record commands and produce a full observation window."""
            self.phases.append(phase)
            self.command = command
            for _ in range(round(seconds / cfg.timestep_s)):
                self.step_index += 1
                self.observations.append(self.sample(self.step_index * cfg.timestep_s, phase))

    world = MotorSpy()
    planner = SimpleNamespace(solve=lambda xyz, opening: ({"gripper": opening}, 0.))
    result = execute_trial(world, planner, (0, 0), 7, tmp_path / "trial", video=False)
    assert result["picked_up"]
    if placement_tracks:
        assert result["release_tracking"]["passed"]
        assert "release" in world.phases and "home" in world.phases
        assert world.command["gripper"] == cfg.gripper_open_rad
    else:
        assert result["release_inhibited"]
        assert result["motion_failure"] == "placement_tracking_failed"
        assert result["failure"] == "invalid_observation"
        assert world.phases[-1] == "place"
        assert "release" not in world.phases and "home" not in world.phases
        assert world.command["gripper"] == cfg.gripper_closed_rad
    assert (tmp_path / "trial/trajectory.jsonl").is_file()
