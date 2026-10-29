# SPDX-License-Identifier: MPL-2.0
"""Build and verify a passive seed seat against a frozen SO-101 benchmark.

Checks concern actual exported CAD and an ideal sphere, not robot motion, gripper
contact mechanics, seed damage, a live model provider, or physical fabrication.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .opencad_program import CadComponent, CadProgram, build_program
from .seed_benchmark import Contract, Digest, TrialManifest, validate_manifest
from .robot_contract import RobotContract, consumer_frames, digest, load_robot, verify_sources, write_json


class FixtureSpec(Contract):
    """Versioned design assumptions, with pinned robot and benchmark inputs."""

    schema_version: Literal[1] = 1
    id: Literal["so101-seed-seat"] = "so101-seed-seat"
    revision: int = Field(strict=True, ge=1)
    parent_bundle_sha256: Digest | None
    benchmark_sha256: Digest
    robot_contract_sha256: Digest
    seed_diameter_mm: float = Field(gt=0, le=20)
    base_x_mm: float = Field(gt=0, le=200)
    base_y_mm: float = Field(gt=0, le=200)
    base_thickness_mm: float = Field(gt=0, le=20)
    post_radius_mm: float = Field(gt=0, le=40)
    post_height_mm: float = Field(gt=0, le=100)
    seat_mouth_radius_mm: float = Field(gt=0, le=20)

    @model_validator(mode="after")
    def feasible(self) -> Self:
        """Require a supported cone contact and an exposed seed equator."""
        if (self.revision == 1) != (self.parent_bundle_sha256 is None):
            raise ValueError("Root revision has no parent; later revisions require a parent bundle hash")
        r, mouth = self.seed_diameter_mm / 2, self.seat_mouth_radius_mm
        if not r / math.sqrt(2) < mouth < r * math.sqrt(2):
            raise ValueError("45-degree seat must support the sphere below an exposed equator")
        if mouth >= self.post_radius_mm - 1 or mouth >= self.post_height_mm - 1:
            raise ValueError("Seat requires at least 1 mm radial wall and floor")
        if 2 * self.post_radius_mm + 4 > min(self.base_x_mm, self.base_y_mm):
            raise ValueError("Post requires a surrounding base margin of at least 2 mm")
        return self

    @property
    def top_mm(self) -> float:
        """Return the pedestal rim elevation above the bench datum."""
        return self.base_thickness_mm + self.post_height_mm

    @property
    def seed_center_mm(self) -> float:
        """Return sphere/cone tangency height for the fixed 45-degree seat."""
        return self.top_mm - self.seat_mouth_radius_mm + self.seed_diameter_mm / math.sqrt(2)


def make_program(spec: FixtureSpec) -> CadProgram:
    """Author a self-contained, parameterized OpenCAD body with stable identity."""
    source = f'''"""Passive seed seat; millimetres, Z-up, bottom face at z=0.

Authored assumptions; an ideal seed fit does not establish physical pickup.
"""
from opencad import Part

BASE_X = {spec.base_x_mm!r}
BASE_Y = {spec.base_y_mm!r}
BASE_THICKNESS = {spec.base_thickness_mm!r}
POST_RADIUS = {spec.post_radius_mm!r}
POST_HEIGHT = {spec.post_height_mm!r}
SEAT_MOUTH_RADIUS = {spec.seat_mouth_radius_mm!r}


def build_fixture() -> Part:
    """Join the centered base/post and subtract a 45-degree conical seed seat."""
    base = Part(name="Bench base").box(BASE_X, BASE_Y, BASE_THICKNESS)
    base.translate((0.0, 0.0, BASE_THICKNESS / 2))
    post = Part(name="Seed pedestal").cylinder(POST_RADIUS, POST_HEIGHT)
    post.translate((0.0, 0.0, BASE_THICKNESS + POST_HEIGHT / 2))
    base.union(post, name="Integral pedestal")
    # Cones start at z=0; cylinders and boxes are centered. Extend the cutter
    # 1 mm above the rim, so its cap cannot leave a coincident top face.
    floor_radius = SEAT_MOUTH_RADIUS / 10
    cutter_height = SEAT_MOUTH_RADIUS + 1.0 - floor_radius
    seat = Part(name="Seat cutter").cone(floor_radius, SEAT_MOUTH_RADIUS + 1.0, cutter_height)
    seat.translate((0.0, 0.0, BASE_THICKNESS + POST_HEIGHT - SEAT_MOUTH_RADIUS + floor_radius))
    return base.cut(seat, name="45-degree seed seat")


parts = {{"seed-seat": build_fixture()}}
'''
    return CadProgram(description="Passive single-seed presentation fixture for an unchanged SO-101",
                      python_source=source,
                      components=[CadComponent(id="seed-seat", name="Seed presentation fixture",
                                               role="External bench fixture; no wrist attachment")],
                      assumptions=["Deterministic authored OpenCAD source; no live generation provider",
                                   "Ideal spherical seed from benchmark simulation assumptions",
                                   "45-degree conical seat; physical tolerances and gripping remain unknown"])


def interface_metadata(spec: FixtureSpec, robot_tcp: dict[str, Any]) -> dict[str, Any]:
    """Derive bench/seed transforms from the same parameters as the CAD source."""
    import numpy as np

    seed = np.eye(4)
    seed[2, 3] = spec.seed_center_mm / 1000
    return {"frame_convention": "right-handed; T_parent_child maps child points into parent",
            "fixture_frame": "base bottom center; X along base length; Z up",
            "fixture_from_bench_datum": consumer_frames(np.eye(4)),
            "fixture_from_seed_center": consumer_frames(seed),
            "robot_base_from_fixture": None,
            "placement_basis": "uncalibrated; no reachability or robot pose inferred",
            "robot_mount": None, "attachment_tcp": None,
            "unchanged_robot_tcp": robot_tcp,
            "pickup_target_is_robot_tcp": False,
            "mounting": "External bench fixture, planar bottom datum; clamp or adhesive TBD",
            "utilities": {"electricity": "none", "vacuum": "none", "pneumatics": "none",
                          "replenishment": "manual one-seed loading between trials"}}


def check_geometry(output: Path, spec: FixtureSpec, interfaces: dict[str, Any]) -> dict[str, Any]:
    """Reopen exchange files and fail on missing seat, unsupported seed, or frame drift."""
    import cadquery as cq
    import numpy as np
    import trimesh

    shape = cq.importers.importStep(str(output / "machine.step")).val()
    if not shape.isValid() or len(shape.Solids()) != 1 or shape.Volume() <= 0:
        raise ValueError("Fixture STEP must contain one valid positive-volume solid")
    b = shape.BoundingBox()
    bounds = np.array([[b.xmin, b.ymin, b.zmin], [b.xmax, b.ymax, b.zmax]])
    expected = np.array([[-spec.base_x_mm / 2, -spec.base_y_mm / 2, 0],
                         [spec.base_x_mm / 2, spec.base_y_mm / 2, spec.top_mm]])
    if not np.allclose(bounds, expected, atol=1e-5, rtol=0):
        raise ValueError("STEP bounds disagree with fixture/bench datum")
    mesh = trimesh.load_mesh(output / "machine.stl", process=True)
    if not mesh.is_volume or not np.allclose(mesh.bounds, expected, atol=0.01, rtol=0):
        raise ValueError("STL must be a watertight positive solid in the STEP millimetre frame")
    if not math.isclose(mesh.volume, shape.Volume(), rel_tol=0.002):
        raise ValueError("STL and STEP volumes disagree")
    expected_interfaces = interface_metadata(spec, interfaces["unchanged_robot_tcp"])
    if interfaces != expected_interfaces:
        raise ValueError("Interface transforms disagree with CAD parameters")
    center = interfaces["fixture_from_seed_center"]["opencad_z_up_mm"][2][3]
    radius = spec.seed_diameter_mm / 2
    contact_radius = radius / math.sqrt(2)
    contact_z = center - contact_radius
    angles = np.linspace(0, 2 * math.pi, 32, endpoint=False)
    contact_points = np.column_stack((contact_radius * np.cos(angles),
                                      contact_radius * np.sin(angles), np.full(32, contact_z)))
    _, distances, _ = trimesh.proximity.closest_point_naive(mesh, contact_points)
    mesh_contact_error = float(max(distances))
    if mesh_contact_error > 0.02:
        raise ValueError("STL seat contact surface differs from the declared seed interface")
    seed = cq.Solid.makeSphere(radius, angleDegrees1=-90, angleDegrees2=90).translate((0, 0, center))
    overlap = shape.intersect(seed).Volume()
    below = shape.intersect(seed.translate((0, 0, -0.05))).Volume()
    if overlap > 1e-6 or shape.distance(seed) > 1e-5 or below <= 1e-5:
        raise ValueError("Seed fit requires tangency, no interference, and support below")
    # The swept lower hemisphere plus cylinder and upper cap is a capsule.
    # Check the complete 10 mm upward seed translation, not just sampled poses.
    lift = 10.0
    sweep = seed.fuse(cq.Solid.makeCylinder(radius, lift, cq.Vector(0, 0, center)),
                      seed.translate((0, 0, lift)))
    sweep_overlap = shape.intersect(sweep).Volume()
    if sweep_overlap > 1e-6:
        raise ValueError("Fixture blocks the vertical seed lift envelope")
    return {"status": "pass", "evidence_kind": "executed_native_CAD",
            "target": "ideal spherical seed; benchmark assumption, not measured seed",
            "step_valid": True, "solid_count": 1, "volume_mm3": shape.Volume(),
            "bounds_mm": bounds.tolist(), "stl_watertight": True,
            "stl_volume_mm3": float(mesh.volume), "stl_contact_surface_error_mm": mesh_contact_error,
            "seed_center_z_mm": center,
            "seed_overlap_mm3": overlap, "seed_surface_distance_mm": shape.distance(seed),
            "support_probe_drop_mm": 0.05, "support_probe_overlap_mm3": below,
            "lift_distance_mm": lift, "lift_sweep_overlap_mm3": sweep_overlap,
            "seed_equator_above_rim_mm": center - spec.top_mm,
            "frames_match_geometry": True, "robot_gripper_fit": "unknown",
            "physics_trial_executed": False, "physical_validation": False,
            "live_provider_execution": False}


def build_fixture(spec_path: Path, benchmark: Path, robot_contract: Path,
                  lock_path: Path, source_root: Path, output: Path,
                  parent_bundle: Path | None = None) -> dict[str, Any]:
    """Build a reproducible candidate with unchanged robot inputs and exact export hashes."""
    spec = FixtureSpec.model_validate_json(spec_path.read_bytes())
    if spec.revision > 1:
        if parent_bundle is None or digest(parent_bundle) != spec.parent_bundle_sha256:
            raise ValueError("Revision requires its exact parent bundle")
        parent = json.loads(parent_bundle.read_text())
        if parent.get("id") != spec.id or parent.get("revision") != spec.revision - 1:
            raise ValueError("Parent must be the preceding revision of the same fixture")
    elif parent_bundle is not None:
        raise ValueError("Root revision cannot supply a parent bundle")
    if digest(benchmark) != spec.benchmark_sha256 or digest(robot_contract) != spec.robot_contract_sha256:
        raise ValueError("Pinned benchmark or robot contract hash mismatch")
    validate_manifest(benchmark)
    manifest = TrialManifest.model_validate_json(benchmark.read_bytes())
    if manifest.benchmark.simulation.geometry.seed_diameter_mm.value != spec.seed_diameter_mm:
        raise ValueError("Fixture seed differs from frozen benchmark")
    contract, _ = load_robot(robot_contract, lock_path, source_root)
    metadata = build_program(make_program(spec), output, runtime="opencad")
    write_json(output / "spec.json", spec.model_dump(mode="json"))
    shutil.copyfile(robot_contract, output / "robot-contract.json")
    shutil.copyfile(lock_path, output / "robot-source-lock.json")
    if parent_bundle is not None:
        shutil.copyfile(parent_bundle, output / "parent-bundle.json")
    interfaces = interface_metadata(spec, contract.tcp.model_dump(mode="json"))
    write_json(output / "interfaces.json", interfaces)
    report = check_geometry(output, spec, interfaces)
    verify_sources(lock_path, source_root)
    if digest(robot_contract) != spec.robot_contract_sha256:
        raise ValueError("Robot contract changed during fixture generation")
    report["robot_geometry_unchanged"] = True
    write_json(output / "fit-report.json", report)
    exports = ("spec.json", "program.json", "machine.py", "machine.step", "machine.stl",
               "machine.tree.json", "machine-bodies.json", "machine-validation.json",
               "component-seed-seat.step", "component-seed-seat.stl", "interfaces.json", "fit-report.json",
               "robot-contract.json", "robot-source-lock.json")
    if parent_bundle is not None:
        exports += ("parent-bundle.json",)
    bundle = {"schema_version": 1, "id": spec.id, "revision": spec.revision,
              "parent_bundle_sha256": spec.parent_bundle_sha256,
              "benchmark_sha256": spec.benchmark_sha256,
              "robot_contract_sha256": spec.robot_contract_sha256,
              "robot_source_lock_sha256": digest(lock_path), "robot_urdf_sha256": contract.urdf_sha256,
              "runtime": {"opencad": metadata["opencad_version"], "backend": "occt"},
              "generation": "deterministic parametric authoring; no live provider",
              "fabrication": {"process": "candidate FDM, flat base down", "material": "PLA assumed",
                              "tolerance_mm": None, "print_validated": False,
                              "notes": "Seat resolution, shrinkage, seed friction, clamping and jaw access require measurement"},
              "files": {name: {"sha256": digest(output / name), "bytes": (output / name).stat().st_size}
                        for name in exports}}
    write_json(output / "bundle.json", bundle)
    verify_bundle(output)
    return {"bundle_sha256": digest(output / "bundle.json"), "fit": report}


def verify_bundle(output: Path) -> dict[str, Any]:
    """Verify artifact integrity and recompute fit from saved exchange geometry.

    The returned bundle digest is the revision lineage key. Hashes detect stale
    or corrupt artifacts; they are not a signature or proof of trusted authorship.
    """
    bundle = json.loads((output / "bundle.json").read_text())
    required = {"spec.json", "program.json", "machine.py", "machine.step", "machine.stl",
                "machine.tree.json", "machine-bodies.json", "machine-validation.json",
                "component-seed-seat.step", "component-seed-seat.stl", "interfaces.json",
                "fit-report.json", "robot-contract.json", "robot-source-lock.json"}
    if bundle["parent_bundle_sha256"] is not None:
        required.add("parent-bundle.json")
    if set(bundle["files"]) != required:
        raise ValueError("Bundle must hash every required artifact")
    for name, item in bundle["files"].items():
        path = output / name
        if digest(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise ValueError(f"Bundle artifact hash/size mismatch: {name}")
    spec = FixtureSpec.model_validate_json((output / "spec.json").read_bytes())
    for key in ("id", "revision", "parent_bundle_sha256", "benchmark_sha256", "robot_contract_sha256"):
        if bundle[key] != getattr(spec, key):
            raise ValueError(f"Bundle identity differs from spec: {key}")
    if spec.revision > 1:
        parent = json.loads((output / "parent-bundle.json").read_text())
        if (digest(output / "parent-bundle.json") != spec.parent_bundle_sha256
                or parent["id"] != spec.id or parent["revision"] != spec.revision - 1):
            raise ValueError("Invalid parent revision lineage")
    robot = RobotContract.model_validate_json((output / "robot-contract.json").read_bytes())
    if (digest(output / "robot-contract.json") != spec.robot_contract_sha256
            or digest(output / "robot-source-lock.json") != robot.source_lock_sha256
            or bundle["robot_source_lock_sha256"] != robot.source_lock_sha256
            or bundle["robot_urdf_sha256"] != robot.urdf_sha256):
        raise ValueError("Bundle robot contract or source lock changed")
    interfaces = json.loads((output / "interfaces.json").read_text())
    if interfaces != interface_metadata(spec, robot.tcp.model_dump(mode="json")):
        raise ValueError("Bundle interface metadata differs from pinned robot/CAD parameters")
    return check_geometry(output, spec, interfaces)


def main() -> None:
    """Build a seed fixture only after verifying the frozen benchmark and real robot."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("spec", "benchmark", "robot-contract", "lock", "source-root", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--parent-bundle", type=Path)
    args = parser.parse_args()
    print(json.dumps(build_fixture(args.spec, args.benchmark, args.robot_contract,
                                   args.lock, args.source_root, args.output, args.parent_bundle), indent=2))


if __name__ == "__main__":
    main()
