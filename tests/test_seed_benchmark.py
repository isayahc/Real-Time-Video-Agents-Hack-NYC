# SPDX-License-Identifier: MPL-2.0
"""Exercise the frozen seed benchmark, execution gates and comparison invariants."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from protocol_pipeline.seed_benchmark import (
    Components, TrialManifest, comparison_key, require_matched_trials, validate_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "examples/so101-benchmark"


def payload() -> dict[str, Any]:
    """Load a fresh input so negative tests never alter the checked-in fixture."""
    return json.loads((CASE / "manifest.json").read_text())


def test_fixture_report_and_schema_are_reproducible() -> None:
    """Validate exact artifact bytes and ensure recorded outputs match actual checks."""
    report = validate_manifest(CASE / "manifest.json")
    assert report == json.loads((CASE / "validation-report.json").read_text())
    assert TrialManifest.model_json_schema() == json.loads((CASE / "manifest.schema.json").read_text())
    assert report["status"] == "contract_valid"
    assert report["execution_blockers"]
    assert not report["trial_execution_performed"]
    assert not report["provider_execution_verified"]
    assert not report["physical_performance_established"]


@pytest.mark.parametrize("role", list(Components.model_fields))
@pytest.mark.parametrize("field", ["id", "version", "sha256", "path"])
def test_missing_or_empty_identity_rejected(role: str, field: str) -> None:
    """Every experimental dependency needs a version and content identity."""
    data = payload()
    del data["components"][role][field]
    with pytest.raises(ValidationError):
        TrialManifest.model_validate(data)
    data = payload()
    data["components"][role][field] = " "
    with pytest.raises(ValidationError):
        TrialManifest.model_validate(data)


@pytest.mark.parametrize("change", ["reset_in_cycle", "cycle_end", "retry_policy"])
def test_incompatible_boundaries_rejected(change: str) -> None:
    """Shortening the cycle or hiding retries cannot reuse this benchmark."""
    data = payload()
    data["boundaries"][change] = True if change == "reset_in_cycle" else "different_boundary"
    with pytest.raises(ValidationError):
        TrialManifest.model_validate(data)


@pytest.mark.parametrize("case", ["missing_source", "null_assumption", "invented_unknown", "nan",
                                 "negative", "unit", "fractional_cells", "tolerance", "overlap",
                                 "zero_settle", "timeout", "string_number", "boolean_number"])
def test_invalid_numerical_inputs_rejected(case: str) -> None:
    """Reject invented measurements, invalid units and physically inconsistent rules."""
    data = payload()
    acceptance = data["benchmark"]["simulation"]
    q = acceptance["geometry"]["pitch_x_mm"]
    if case == "missing_source":
        del q["source"]
    elif case == "null_assumption":
        q["value"] = None
    elif case == "invented_unknown":
        q["basis"] = "unknown"
    elif case in ("nan", "negative", "string_number", "boolean_number"):
        q["value"] = {"nan": float("nan"), "negative": -1, "string_number": "40", "boolean_number": True}[case]
    elif case == "unit":
        q["unit"] = "s"
    elif case == "fractional_cells":
        acceptance["geometry"]["rows"]["value"] = 6.5
    elif case == "tolerance":
        acceptance["radial_tolerance_mm"]["value"] = 20
    elif case == "overlap":
        acceptance["geometry"]["cell_opening_mm"]["value"] = 50
    elif case == "zero_settle":
        acceptance["settling_time_s"]["value"] = 0
    else:
        acceptance["timeout_s"]["value"] = 0.5
    with pytest.raises(ValidationError):
        TrialManifest.model_validate(data)


@pytest.mark.parametrize("kind", ["assumption", "simulation", "physical"])
def test_definition_only_inputs_cannot_execute(kind: str) -> None:
    """A valid authored protocol cannot masquerade as a ready robot experiment."""
    data = payload()
    data.update(evidence_kind=kind, execution_requested=True)
    with pytest.raises(ValidationError, match="Execution blocked"):
        TrialManifest.model_validate(data)


def test_physical_unknowns_block_even_with_materialized_components() -> None:
    """Changing component availability does not fill missing physical measurements."""
    data = payload()
    data.update(evidence_kind="physical")
    for component in data["components"].values():
        component["availability"] = "materialized"
    manifest = TrialManifest.model_validate(data)
    assert "physical.radial_tolerance_mm is unknown" in manifest.execution_blockers()
    assert "physical seed lot is unknown" in manifest.execution_blockers()
    assert manifest.benchmark.physical.geometry.seed_diameter_mm.value is None
    data["execution_requested"] = True
    with pytest.raises(ValidationError, match="Execution blocked"):
        TrialManifest.model_validate(data)


def test_physical_observation_cannot_reuse_simulator_rules() -> None:
    """Physical acceptance must use physical inspection, not a simulator flag."""
    data = payload()
    data["benchmark"]["physical"]["observation"] = "simulator_state"
    with pytest.raises(ValidationError, match="another evidence kind"):
        TrialManifest.model_validate(data)


@pytest.mark.parametrize("change", ["seed_duplicate", "target_duplicate", "target_outside", "bool_seed",
                                  "negative_seed", "missing_failure", "duplicate_failure", "extra_field"])
def test_invalid_schedule_or_failure_vocabulary(change: str) -> None:
    """Retain complete failure accounting and unambiguous target/seed pairs."""
    data = payload()
    if change == "seed_duplicate":
        data["trial_seeds"].append(7)
    elif change == "target_duplicate":
        data["targets"].append(data["targets"][0])
    elif change == "target_outside":
        data["targets"][0]["row"] = 6
    elif change == "bool_seed":
        data["trial_seeds"] = [True]
    elif change == "negative_seed":
        data["trial_seeds"] = [-1]
    elif change == "missing_failure":
        data["benchmark"]["failure_categories"].pop()
    elif change == "duplicate_failure":
        data["benchmark"]["failure_categories"].append("timeout")
    else:
        data["success_rate"] = 1
    with pytest.raises(ValidationError):
        TrialManifest.model_validate(data)


def test_only_tool_and_experiment_identity_may_vary() -> None:
    """Tooling changes are allowed while seeds, policy and all controls stay fixed."""
    baseline = TrialManifest.model_validate(payload())
    candidate = payload()
    candidate["experiment_id"] = "custom-tool"
    candidate["components"]["tool"]["version"] = "v2"
    require_matched_trials(baseline, TrialManifest.model_validate(candidate))
    for role in Components.model_fields:
        if role == "tool":
            continue
        changed = copy.deepcopy(candidate)
        changed["components"][role]["version"] = "v2"
        with pytest.raises(ValueError, match="Incompatible"):
            require_matched_trials(baseline, TrialManifest.model_validate(changed))
    for key, value in (("trial_seeds", [3, 2, 1]), ("evidence_kind", "simulation"),
                       ("targets", [{"row": 0, "column": 1}])):
        changed = copy.deepcopy(candidate)
        changed[key] = value
        with pytest.raises(ValueError, match="Incompatible"):
            require_matched_trials(baseline, TrialManifest.model_validate(changed))
    mutated = baseline.model_copy(deep=True)
    mutated.trial_seeds = [7, 7]
    with pytest.raises(ValidationError):
        comparison_key(mutated)


def test_artifact_tampering_and_path_escape_rejected(tmp_path: Path) -> None:
    """Validate actual dependency bytes and contain artifact paths to the bundle."""
    bundle = tmp_path / "case"
    shutil.copytree(CASE, bundle)
    artifact = bundle / "artifacts/robot.json"
    original = artifact.read_bytes()
    artifact.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_manifest(bundle / "manifest.json")
    artifact.write_bytes(original)
    data = payload()
    data["components"]["robot"]["path"] = "../escaped.json"
    (bundle / "manifest.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="inside manifest directory"):
        validate_manifest(bundle / "manifest.json")


def test_cli_success_failure_and_no_overwrite(tmp_path: Path) -> None:
    """Exercise the documented entrypoint and protect previously recorded evidence."""
    report = tmp_path / "report.json"
    command = [sys.executable, "-m", "protocol_pipeline.seed_benchmark", "--manifest",
               str(CASE / "manifest.json"), "--output", str(report)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    original = report.read_bytes()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 1
    assert report.read_bytes() == original
    bad = tmp_path / "bad.json"
    bad.write_text('{}')
    result = subprocess.run(command[:4] + [str(bad)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 1
    assert "validation failed" in result.stderr
