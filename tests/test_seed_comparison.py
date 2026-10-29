# SPDX-License-Identifier: MPL-2.0
"""Reject mismatched tool comparisons and preserve failures and unknown accounting inputs."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("yourdfpy")
from protocol_pipeline.robot_contract import digest, write_json
from protocol_pipeline.seed_benchmark import TrialManifest
from protocol_pipeline.seed_comparison import execute, gripper_audit, matched_inputs, summarize_candidate

ROOT = Path(__file__).resolve().parents[1]


def input_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Materialize synthetic contract-only fixtures; never treat these as executed trials."""
    roots = (tmp_path / "baseline", tmp_path / "candidate")
    for index, root in enumerate(roots):
        (root / "assets").mkdir(parents=True)
        (root / "assets/fixture.obj").write_text(f"contract-only tool {index}")
        (root / "assets/tray.obj").write_text("contract-only shared tray")
        data = json.loads((ROOT / "examples/so101-benchmark/manifest.json").read_text())
        data.update(experiment_id=root.name, evidence_kind="simulation", execution_requested=True)
        for role in data["components"]:
            path = root / f"{role}.json"
            record = {"contract_fixture": role}
            if role == "tool":
                record["fixture_mesh_sha256"] = digest(root / "assets/fixture.obj")
            if role == "environment":
                record["assets"] = {"tray.obj": digest(root / "assets/tray.obj")}
            write_json(path, record)
            data["components"][role] = {"id": role, "version": "test", "availability": "materialized",
                                        "path": path.name, "sha256": digest(path)}
        write_json(root / "manifest.json", data)
    return roots


def test_tool_only_variation_allowed(tmp_path: Path) -> None:
    """Different passive tools may share all other experiment controls."""
    a, b = input_pair(tmp_path)
    matched_inputs(a, b)


@pytest.mark.parametrize("role", ["robot", "policy", "evaluator", "environment", "calibration", "cameras"])
def test_changed_control_rejected(tmp_path: Path, role: str) -> None:
    """A self-consistently rehashed control change is still not a matched comparison."""
    a, b = input_pair(tmp_path)
    artifact = b / f"{role}.json"
    record = json.loads(artifact.read_text()); record["changed"] = True
    artifact.write_text(json.dumps(record))
    path = b / "manifest.json"; data = json.loads(path.read_text())
    data["components"][role]["sha256"] = digest(artifact)
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Incompatible"):
        matched_inputs(a, b)


@pytest.mark.parametrize("mutation", ["seed", "target", "tool_mesh", "tray_mesh", "same_tool"])
def test_schedule_and_geometry_mismatch_rejected(tmp_path: Path, mutation: str) -> None:
    """Hold seed order, targets and actual mesh identities constant beyond the tool change."""
    a, b = input_pair(tmp_path)
    path = b / "manifest.json"; data = json.loads(path.read_text())
    if mutation == "seed":
        data["trial_seeds"].reverse()
    elif mutation == "target":
        data["targets"].reverse()
    elif mutation in ("tool_mesh", "tray_mesh"):
        (b / "assets" / ("fixture.obj" if mutation == "tool_mesh" else "tray.obj")).write_text("changed")
    else:
        (b / "assets/fixture.obj").write_bytes((a / "assets/fixture.obj").read_bytes())
        (b / "tool.json").write_bytes((a / "tool.json").read_bytes())
        data["components"]["tool"]["sha256"] = digest(b / "tool.json")
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        matched_inputs(a, b)


def test_failed_attempts_and_unknown_accounting(tmp_path: Path) -> None:
    """Synthetic outcome records test aggregation, not physics success."""
    a, b = input_pair(tmp_path)
    manifest = matched_inputs(a, b)[0]
    results = []
    for index, (seed, target) in enumerate((s, t) for s in manifest.trial_seeds for t in manifest.targets):
        case = f"trial-{index:02d}"; folder = a / case; folder.mkdir()
        for file in ("result.json", "trajectory.jsonl", "trial.mp4", "replay.oi.json"):
            (folder / file).write_text("synthetic aggregation input only")
        results.append({"case": case, "trial_seed": seed, "target": [target.row, target.column],
                        "accepted": False, "geometric_placement_pass": False, "picked_up": False,
                        "failure": "collision", "collision": True, "timeout": False,
                        "cycle_seconds": 8., "reset_wall_seconds": 3.})
    write_json(a / "summary.json", {"schedule_complete": True, "results": results,
                                    "repeat_passed": True, "deliberate_failure_passed": True})
    report = summarize_candidate(a, manifest)
    assert report["attempted"] == 9 and report["accepted"] == 0
    assert report["failure_counts"] == {"collision": 9, "pickup_miss": 9}
    assert report["cycle_simulation_s"]["total"] == 72
    accounting = report["accounting_report"]
    assert not accounting["acceptance_verified"]
    assert accounting["metrics"]["accepted_outputs_per_hour"]["status"] == "unknown"
    assert accounting["metrics"]["cost_usd_per_accepted"]["value"] is None
    results.pop()
    (a / "summary.json").write_text(json.dumps({"schedule_complete": True, "results": results}))
    with pytest.raises(ValueError, match="Incomplete"):
        summarize_candidate(a, manifest)


def test_native_geometry_audit_and_matched_execution(tmp_path: Path) -> None:
    """Exercise both actual presentation tools, negative controls and fresh resets."""
    pytest.importorskip("pybullet")
    source = os.getenv("SO101_SOURCE_ROOT")
    if not source:
        pytest.skip("Set SO101_SOURCE_ROOT to the pinned source checkout")
    output = tmp_path / "pair"
    execute(ROOT / "examples/so101-comparison/config.json", Path(source), output, video=False, smoke=True)
    matched_inputs(output / "reference_pocket", output / "cad_seat")
    audit = json.loads((output / "gripper-audit.json").read_text())
    assert audit["sections"][0]["x_gap_m"] == pytest.approx(.0158, abs=1e-6)
    assert 0 < audit["sections"][1]["x_gap_m"] < .003
    for tool in ("reference_pocket", "cad_seat"):
        summary = json.loads((output / tool / "summary.json").read_text())
        assert summary["repeat_passed"] and summary["deliberate_failure_passed"]
        assert all(not r["accepted"] for r in summary["results"])
        trajectory = [json.loads(line) for line in (output / tool / "trial-00/trajectory.jsonl").read_text().splitlines()]
        assert any(row["joint_target_rad"]["gripper"] < -.17 for row in trajectory)
