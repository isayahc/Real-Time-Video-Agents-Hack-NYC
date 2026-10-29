# SPDX-License-Identifier: MPL-2.0
"""Execute and audit matched SO-101 presentation-tool trials without ranking unknowns."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .evaluation import ProcessEvaluationInput, evaluate_process
from .robot_contract import contained, digest, load_robot, read_lock, write_json
from .seed_benchmark import TrialManifest, require_matched_trials, validate_manifest
from .seed_simulation import run, verify_output


TOOLS = ("reference_pocket", "cad_seat")


def verify_files(root: Path) -> dict[str, Any]:
    """Verify complete executed bundles and reject missing, changed or escaping files."""
    report = json.loads((root / "evidence.json").read_text())
    if report["status"] != "executed_evidence_verified":
        raise ValueError("Comparison requires verified executed evidence")
    for relative, record in report["files"].items():
        path = contained(root, relative)
        if path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
            raise ValueError(f"Changed executed evidence: {relative}")
    verify_output(root)
    return report


def matched_inputs(baseline: Path, candidate: Path) -> tuple[TrialManifest, TrialManifest]:
    """Verify materialized components before applying the existing tooling-only guard."""
    manifests = []
    seed_pose_anchors = []
    for root in (baseline, candidate):
        validate_manifest(root / "manifest.json")
        manifest = TrialManifest.model_validate_json((root / "manifest.json").read_text())
        if manifest.evidence_kind != "simulation" or not manifest.execution_requested:
            raise ValueError("Comparison requires executed simulation manifests")
        tool = json.loads((root / manifest.components.tool.path).read_text())
        environment = json.loads((root / manifest.components.environment.path).read_text())
        seed_pose_anchors.append(tool["reference_cad_archive_sha256"])
        if digest(root / "assets/fixture.obj") != tool["fixture_mesh_sha256"]:
            raise ValueError("Tool mesh differs from materialized identity")
        for name, expected in environment["assets"].items():
            if digest(contained(root / "assets", name)) != expected:
                raise ValueError("Environment mesh differs from materialized identity")
        manifests.append(manifest)
    require_matched_trials(*manifests)
    if seed_pose_anchors[0] != seed_pose_anchors[1]:
        raise ValueError("Nominal seed-pose reference archive must remain identical")
    if manifests[0].components.tool.sha256 == manifests[1].components.tool.sha256:
        raise ValueError("Comparison requires distinct tool candidates")
    return tuple(manifests)


def summarize_candidate(root: Path, manifest: TrialManifest) -> dict[str, Any]:
    """Keep failed attempts in denominators and map observed counts into existing accounting."""
    summary = json.loads((root / "summary.json").read_text())
    expected = [(seed, [cell.row, cell.column]) for seed in manifest.trial_seeds for cell in manifest.targets]
    nominal = [r for r in summary["results"] if r["case"].startswith("trial-")]
    if not summary["schedule_complete"] or [(r["trial_seed"], r["target"]) for r in nominal] != expected:
        raise ValueError("Incomplete or reordered nominal schedule")
    attempts = []
    failures: Counter[str] = Counter()
    for result in nominal:
        categories = [result["failure"]]
        if not result["picked_up"]:
            categories.append("pickup_miss")
        if result["collision"]:
            categories.append("collision")
        if result["timeout"]:
            categories.append("timeout")
        categories = sorted(set(categories))
        failures.update(categories)
        directory = root / result["case"]
        refs = {name: {"path": f"{root.name}/{result['case']}/{name}", "sha256": digest(directory / name)}
                for name in ("result.json", "trajectory.jsonl", "trial.mp4", "replay.oi.json")}
        attempts.append({"case": result["case"], "trial_seed": result["trial_seed"], "target": result["target"],
                         "accepted": result["accepted"], "geometric_placement_pass": result["geometric_placement_pass"],
                         "picked_up": result["picked_up"], "cycle_simulation_s": result["cycle_seconds"],
                         "reset_host_wall_s": result["reset_wall_seconds"], "failures": categories,
                         "collision": result["collision"], "evidence": refs})
    accepted = sum(r["accepted"] for r in nominal)
    # Do not combine simulator seconds and host wall-clock reset durations into
    # throughput. Resource/time accounting remains unknown where unmeasured.
    source = f"{root.name}/summary.json#sha256={digest(root / 'summary.json')}"
    accounting = ProcessEvaluationInput(
        configuration_id=root.name, functional_unit="one accepted seed placement",
        boundary="Frozen nine-attempt simulation schedule; cycle and host reset clocks are separate; full elapsed and resources unknown",
        acceptance_verified=False,
        inputs={"attempted_count": {"value": len(nominal), "unit": "count", "basis": "measured", "source": source},
                "accepted_count": {"value": accepted, "unit": "count", "basis": "measured", "source": source}})
    return {"candidate": root.name, "evidence_kind": "simulation", "attempted": len(nominal), "accepted": accepted,
            "accepted_fraction": accepted / len(nominal), "geometric_placements": sum(r["geometric_placement_pass"] for r in nominal),
            "pickups": sum(r["picked_up"] for r in nominal), "collision_attempts": sum(r["collision"] for r in nominal),
            "failure_counts": dict(failures), "cycle_simulation_s": {"total": sum(r["cycle_seconds"] for r in nominal),
                "mean": float(np.mean([r["cycle_seconds"] for r in nominal])), "includes_reset": False},
            "reset_host_wall_s": {"total": sum(r["reset_wall_seconds"] for r in nominal), "comparable_to_simulation_time": False},
            "attempts": attempts, "accounting_input": accounting.model_dump(),
            "accounting_report": evaluate_process(accounting).model_dump(),
            "unknown_resources": ["labor", "electricity", "material_loss", "cost", "physical_throughput"],
            "damage_observable": False, "repeat_passed": summary["repeat_passed"],
            "deliberate_failure_passed": summary["deliberate_failure_passed"],
            "excluded_controls": ["negative-open", "repeat-00"]}


def compare(baseline: Path, candidate: Path, output: Path) -> dict[str, Any]:
    """Reject incompatible or tampered executions before calculating matched paired results."""
    if output.exists():
        raise FileExistsError(output)
    manifests = matched_inputs(baseline, candidate)
    for root in (baseline, candidate):
        verify_files(root)
    reports = [summarize_candidate(root, manifest) for root, manifest in zip((baseline, candidate), manifests)]
    pairs = [{"trial_seed": a["trial_seed"], "target": a["target"],
              "baseline_accepted": a["accepted"], "candidate_accepted": b["accepted"],
              "cycle_delta_simulation_s": b["cycle_simulation_s"] - a["cycle_simulation_s"],
              "baseline_failures": a["failures"], "candidate_failures": b["failures"]}
             for a, b in zip(reports[0]["attempts"], reports[1]["attempts"])]
    result = {"schema_version": 1, "status": "matched_executions_compared", "evidence_kind": "simulation",
              "implementation_sha256": digest(Path(__file__)), "candidates": reports, "pairs": pairs,
              "winner": None, "ranking_status": "not_established",
              "ranking_reason": "Damage acceptance is unobservable; no physical or economic equivalence established",
              "controls": {"only_tool_identity_varies": True, "nominal_seed_pose_shared": True,
                           "settled_pose": "Tool-dependent contact response retained; both use the same 1 mm reset bound",
                           "randomization": "Frozen v1 has no perturbations; nine scheduled cases are not independent reliability samples"},
              "physical_execution": False, "live_provider_execution": False,
              "limitations": ["Corrected grasp configuration is shared by both tools; the archived #64 run is not a comparator.",
                              "Collision geometry, friction, seed mass and grasp calibration remain simulation assumptions.",
                              "No damage model; accepted counts are evaluator decisions, not biological success rates.",
                              "Counts use the published ProcessEvaluationInput/evaluate_process contract; unpublished #62 worker is not available."]}
    write_json(output, result)
    return result


def gripper_audit(contract_path: Path, lock_path: Path, source_root: Path, output: Path) -> dict[str, Any]:
    """Measure source-mesh jaw sections at the virtual TCP; do not infer hardware calibration."""
    contract, robot = load_robot(contract_path, lock_path, source_root)
    source_dir = contained(source_root, read_lock(lock_path)["urdf"]).parent
    meshes = {}
    for name in ("gripper_link", "moving_jaw_so101_v1_link"):
        parts = []
        for collision in robot.link_map[name].collisions:
            shape = collision.geometry.mesh
            mesh = trimesh.load_mesh(contained(source_dir, shape.filename))
            if shape.scale is not None:
                mesh.apply_scale(shape.scale)
            mesh.apply_transform(collision.origin)
            parts.append(mesh)
        meshes[name] = trimesh.util.concatenate(parts)
    z = contract.tcp.matrix_m[2][3]
    sections = []
    for angle in (0., contract.joints["gripper"].lower_rad):
        robot.update_cfg({**contract.reference_pose_rad, "gripper": angle})
        bounds = {}
        for name, mesh in meshes.items():
            moved = mesh.copy()
            moved.apply_transform(np.linalg.inv(robot.get_transform("gripper_link")) @ robot.get_transform(name))
            section = moved.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
            if section is None:
                raise ValueError("Source jaw does not intersect the declared TCP section")
            bounds[name] = section.bounds.tolist()
        gap = bounds["moving_jaw_so101_v1_link"][0][0] - bounds["gripper_link"][1][0]
        sections.append({"gripper_rad": angle, "source_section_bounds_m": bounds, "x_gap_m": gap})
    result = {"evidence_kind": "model_geometry", "robot_contract_sha256": digest(contract_path),
              "tcp_section_z_m": z, "virtual_tcp_x_m": contract.tcp.matrix_m[0][3], "sections": sections,
              "diagnosis": "Zero-radian closure leaves a gap wider than the ideal seed; virtual TCP lies on the fixed inner face.",
              "common_correction": {"grasp_offset_tcp_m": [-.0015, 0., 0.], "closed_rad": contract.joints["gripper"].lower_rad},
              "limitations": ["Section bounds are geometric checks, not a grasp guarantee or calibrated hardware command.",
                              "The original Bullet hull collider can differ from the source triangle surface.",
                              "Corrected motor execution must still be evaluated; no pickup is inferred from geometry."]}
    write_json(output, result)
    return result


def execute(config: Path, source_root: Path, output: Path, *, video: bool = True, smoke: bool = False) -> None:
    """Execute two tools under one pinned configuration and preserve separate input bundles."""
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    contract = Path("examples/so101-robot/robot-contract.json")
    lock = Path("examples/so101-robot/source-lock.json")
    gripper_audit(contract, lock, source_root, output / "gripper-audit.json")
    for tool in TOOLS:
        run(config, Path("examples/so101-benchmark/manifest.json"), contract, lock, source_root,
            Path("examples/so101-fixture/candidate-v1.zip"), output / tool,
            video=video, smoke=smoke, presentation=tool)
    matched_inputs(output / TOOLS[0], output / TOOLS[1])


def main() -> None:
    """Run the pair or validate completed video/OI bundles and produce comparison accounting."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("examples/so101-comparison/config.json"))
    parser.add_argument("--compare-only", action="store_true")
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.compare_only:
        result = compare(args.output / TOOLS[0], args.output / TOOLS[1], args.output / "comparison.json")
        print(json.dumps({"status": result["status"], "winner": result["winner"],
                          "candidates": [{k: r[k] for k in ("candidate", "attempted", "accepted", "collision_attempts")} for r in result["candidates"]]}))
    else:
        if args.source_root is None:
            parser.error("Execution requires --source-root")
        execute(args.config, args.source_root, args.output, video=not args.no_video, smoke=args.smoke)


if __name__ == "__main__":
    main()
