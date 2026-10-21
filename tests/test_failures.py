# SPDX-License-Identifier: MPL-2.0
"""Verify step-evidence distinctions and resource deviations in failure replay."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from protocol_pipeline.failures import StepObservation, assess_steps, run_failures

ROOT = Path(__file__).resolve().parents[1]


class FailureReplayTests(unittest.TestCase):
    """Check actual outcomes rather than accepting a completed run as correctness."""

    def test_explicit_skip_differs_from_absent_evidence(self) -> None:
        """A missing observation is unknown while an explicit skip is flagged."""
        required = ["prepare", "wind"]
        observed = [StepObservation(operation_id="wind", status="completed", evidence_refs=["fixture"])]
        result = assess_steps(required, observed, set(required))
        self.assertEqual(result["unknown_required"], ["prepare"])
        self.assertEqual(result["skipped_required"], [])
        observed.append(StepObservation(operation_id="prepare", status="skipped", evidence_refs=["fixture"]))
        result = assess_steps(required, observed, set(required))
        self.assertEqual(result["unknown_required"], [])
        self.assertEqual(result["skipped_required"], ["prepare"])

    def test_invalid_step_evidence_rejected(self) -> None:
        """Unknown, duplicate or blank-evidence observations cannot enter the trace."""
        observation = StepObservation(operation_id="prepare", status="completed", evidence_refs=["fixture"])
        with self.assertRaises(ValueError):
            assess_steps(["prepare"], [observation, observation], {"prepare"})
        with self.assertRaises(ValueError):
            assess_steps(["prepare"], [observation], {"wind"})
        observation.evidence_refs = [" "]
        with self.assertRaises(ValueError):
            assess_steps(["prepare"], [observation], {"prepare"})

    def test_failure_cases_preserve_unknowns_and_boundaries(self) -> None:
        """Delays/rejects flag differences; absent data stays unknown without false skips."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "run"
            result = run_failures(ROOT, output)
            cases = result["cases"]
            self.assertEqual(cases["missed_preparation"]["steps"]["skipped_required"], ["prep_verify_stock"])
            delay = cases["delayed_batch"]["deviations"]["metrics"]
            self.assertTrue(delay["accepted_outputs_per_hour"]["outside_tolerance"])
            self.assertEqual(delay["accepted_outputs_per_hour"]["direction"], "worsened")
            rejects = cases["excess_rejects"]
            self.assertTrue(rejects["deviations"]["metrics"]["cost_usd_per_accepted"]["outside_tolerance"])
            self.assertIsNone(rejects["process_report"]["metrics"]["unrecovered_waste_g_per_accepted"]["value"])
            absent = cases["incomplete_observations"]
            self.assertEqual(absent["steps"]["unknown_required"], ["prep_verify_stock"])
            self.assertEqual(absent["steps"]["skipped_required"], [])
            self.assertTrue(all(metric["outside_tolerance"] is None for metric in absent["deviations"]["metrics"].values()))
            self.assertTrue(all(case["evidence_kind"] == "illustrative" for case in cases.values()))
            before = (output / "summary.json").read_bytes()
            with self.assertRaises(FileExistsError):
                run_failures(ROOT, output)
            self.assertEqual(before, (output / "summary.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
