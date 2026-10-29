"""Contract rejection and opt-in native exchange/fit regression tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from typing import Any

import pytest

from protocol_pipeline.seed_fixture import (
    FixtureSpec, build_fixture, check_geometry, interface_metadata, make_program, verify_bundle,
)
from protocol_pipeline.opencad_program import build_program, validate_program

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/so101-fixture"


def spec_data() -> dict[str, Any]:
    """Read the committed candidate input, not a duplicate set of dimensions."""
    return json.loads((EXAMPLE / "spec.json").read_text())


@pytest.mark.parametrize("changes", [
    {"seat_mouth_radius_mm": 0.5}, {"seat_mouth_radius_mm": 2.5},
    {"post_radius_mm": 2.0}, {"post_height_mm": 2.0}, {"base_x_mm": 5.0},
    {"revision": 2}, {"parent_bundle_sha256": "a" * 64},
    {"seed_diameter_mm": float("nan")}, {"seed_diameter_mm": True},
    {"seed_diameter_mm": "3.0"}, {"unrecognized": 1},
])
def test_reject_invalid_spec(changes: dict[str, Any]) -> None:
    """Reject infeasible seats, hidden changes, bad units/types and orphan lineage."""
    with pytest.raises(ValueError):
        FixtureSpec.model_validate({**spec_data(), **changes})


def test_source_and_consumer_transforms() -> None:
    """Use the existing bounded CAD source contract and shared mm/Z-up conversion."""
    spec = FixtureSpec.model_validate(spec_data())
    validate_program(make_program(spec))
    assert (EXAMPLE / "assembly.py").read_text() == make_program(spec).python_source
    frames = interface_metadata(spec, {})["fixture_from_seed_center"]
    assert frames["opencad_z_up_mm"][2][3] == pytest.approx(12.72132034356)
    assert frames["oi_y_up_m"][1][3] == pytest.approx(0.01272132034356)
    assert interface_metadata(spec, {})["attachment_tcp"] is None


def test_changed_inputs_fail_before_cad(tmp_path: Path) -> None:
    """Do not regenerate from a different robot or silently drift the benchmark."""
    fake = tmp_path / "bad.json"
    fake.write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_fixture(EXAMPLE / "spec.json", fake, fake, fake, tmp_path, tmp_path / "result")
    assert not (tmp_path / "result").exists()


def test_revision_requires_real_parent(tmp_path: Path) -> None:
    """A syntactically valid parent hash alone cannot establish revision lineage."""
    changed = tmp_path / "spec.json"
    changed.write_text(json.dumps({**spec_data(), "revision": 2, "parent_bundle_sha256": "a" * 64}))
    with pytest.raises(ValueError, match="exact parent"):
        build_fixture(changed, changed, changed, changed, tmp_path, tmp_path / "result")


NATIVE = os.getenv("SO101_FIXTURE_NATIVE_TESTS") == "1"


@pytest.fixture(scope="module")
def native_bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Execute real OpenCAD, then reopen exported solids with the pinned robot."""
    if not NATIVE:
        pytest.skip("Set SO101_FIXTURE_NATIVE_TESTS=1 with OpenCAD/OCCT and SO101_SOURCE_ROOT")
    output = tmp_path_factory.mktemp("seed-fixture") / "bundle"
    build_fixture(EXAMPLE / "spec.json", ROOT / "examples/so101-benchmark/manifest.json",
                  ROOT / "examples/so101-robot/robot-contract.json",
                  ROOT / "examples/so101-robot/source-lock.json",
                  Path(os.environ["SO101_SOURCE_ROOT"]), output)
    return output


def test_native_seed_seat_and_exports(native_bundle: Path) -> None:
    """Verify a loaded native body supports the sphere without blocking its lift."""
    report = verify_bundle(native_bundle)
    assert report["seed_overlap_mm3"] < 1e-6
    assert report["support_probe_overlap_mm3"] > 1e-5
    assert report["lift_sweep_overlap_mm3"] < 1e-6
    assert report["seed_equator_above_rim_mm"] > 0.7
    assert report["robot_gripper_fit"] == "unknown"
    assert not report["physical_validation"]
    assert json.loads((native_bundle / "fit-report.json").read_text())["robot_geometry_unchanged"]


@pytest.mark.parametrize("corruption", ["solid_seat", "filled_stl_seat", "shift_step", "scale_stl", "frame", "tcp", "hash"])
def test_native_reject_invalid_exports(native_bundle: Path, tmp_path: Path, corruption: str) -> None:
    """Plausible bounding boxes alone must not pass target or frame compatibility."""
    import cadquery as cq
    import trimesh

    output = tmp_path / "broken"
    shutil.copytree(native_bundle, output)
    spec = FixtureSpec.model_validate(spec_data())
    interfaces = json.loads((output / "interfaces.json").read_text())
    if corruption in ("solid_seat", "filled_stl_seat"):
        source = make_program(spec).model_copy(update={"python_source": make_program(spec).python_source.replace(
            'return base.cut(seat, name="45-degree seed seat")', 'return base')})
        bad = tmp_path / "solid"
        build_program(source, bad, runtime="opencad")
        for name in (("machine.step", "machine.stl") if corruption == "solid_seat" else ("machine.stl",)):
            shutil.copyfile(bad / name, output / name)
    elif corruption == "shift_step":
        shape = cq.importers.importStep(str(output / "machine.step")).val().translate((1, 0, 0))
        cq.exporters.export(shape, str(output / "machine.step"))
    elif corruption == "scale_stl":
        mesh = trimesh.load_mesh(output / "machine.stl")
        mesh.apply_scale(0.001)
        mesh.export(output / "machine.stl")
    elif corruption == "frame":
        interfaces["fixture_from_seed_center"]["opencad_z_up_mm"][2][3] += 1
    elif corruption == "tcp":
        interfaces["unchanged_robot_tcp"]["matrix_m"][0][3] += 1
        (output / "interfaces.json").write_text(json.dumps(interfaces))
    else:
        (output / "machine.py").write_text("changed")
    with pytest.raises(ValueError):
        if corruption in ("hash", "tcp"):
            verify_bundle(output)
        else:
            check_geometry(output, spec, interfaces)


def test_revision_lineage(native_bundle: Path, tmp_path: Path) -> None:
    """Retain the exact preceding bundle when a geometry parameter changes."""
    from protocol_pipeline.robot_contract import digest

    data = {**spec_data(), "revision": 2, "parent_bundle_sha256": digest(native_bundle / "bundle.json"),
            "base_x_mm": 44.0}
    changed = tmp_path / "spec.json"
    changed.write_text(json.dumps(data))
    output = tmp_path / "revision-2"
    build_fixture(changed, ROOT / "examples/so101-benchmark/manifest.json",
                  ROOT / "examples/so101-robot/robot-contract.json",
                  ROOT / "examples/so101-robot/source-lock.json", Path(os.environ["SO101_SOURCE_ROOT"]),
                  output, native_bundle / "bundle.json")
    assert digest(output / "parent-bundle.json") == data["parent_bundle_sha256"]
    assert verify_bundle(output)["bounds_mm"][1][0] == 22.0


def test_archived_candidate(native_bundle: Path, tmp_path: Path) -> None:
    """The committed deliverable must be independently loadable and hash-verifiable."""
    import zipfile

    output = tmp_path / "archived"
    with zipfile.ZipFile(EXAMPLE / "candidate-v1.zip") as archive:
        archive.extractall(output)
    assert (output / "bundle.json").read_bytes() == (EXAMPLE / "executed-bundle.json").read_bytes()
    assert verify_bundle(output)["status"] == "pass"
