# SPDX-License-Identifier: MPL-2.0
"""Verify conditional multi-apparatus comparison without promoting assumptions."""
from __future__ import annotations

import copy
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from protocol_pipeline.alternatives import AlternativeSet, evaluate_alternatives, run_alternatives

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples/apparatus-alternatives"


class AlternativeTests(unittest.TestCase):
    """Exercise three-way economics, shared sensitivities and actual evidence gaps."""

    def fixture(self, name: str = "illustrative-input.json") -> AlternativeSet:
        """Load the exact committed comparison input used by the CLI demo."""
        return AlternativeSet.model_validate_json((FIXTURES / name).read_text())

    def test_actual_evidence_has_no_performance_ranking(self) -> None:
        """Unknown full-process data cannot become a numerical winner or zero cost."""
        result = evaluate_alternatives(self.fixture("evidence-input.json"))
        scenario = result["scenarios"]["current-evidence"]
        self.assertEqual(len(scenario["comparisons"]), 3)
        for pair in scenario["comparisons"]:
            self.assertEqual(pair["result"]["decision"], "undetermined")
            self.assertIsNone(pair["result"]["metrics"]["horizon_net_saving"]["value"])
        for option in scenario["resources"].values():
            self.assertIsNone(option["metrics"]["cost_usd_per_accepted"]["value"])
            self.assertIsNone(option["metrics"]["electricity_wh_per_accepted"]["value"])

    def test_shared_sensitivity_and_unpriced_labor(self) -> None:
        """Apply rates uniformly and retain physical attended time at zero wage."""
        data = self.fixture()
        before = copy.deepcopy(data.model_dump())
        result = evaluate_alternatives(data)
        zero = result["scenarios"]["10000-coils-unpriced-labor"]
        base = result["scenarios"]["10000-coils-per-year"]
        for key in ("manual", "motorized", "cw02"):
            self.assertEqual(zero["resources"][key]["costs_usd_per_batch"]["labor_cost"]["value"], 0)
            self.assertEqual(zero["resources"][key]["metrics"]["labor_s_per_accepted"], base["resources"][key]["metrics"]["labor_s_per_accepted"])
        for pair in zero["comparisons"]:
            self.assertLess(pair["result"]["metrics"]["horizon_net_saving"]["value"], 0)
        self.assertEqual(before, data.model_dump())

    def test_economics_change_with_demand_but_gate_stays(self) -> None:
        """Capital amortization can reverse arithmetic without approving investment."""
        result = evaluate_alternatives(self.fixture())
        low = result["scenarios"]["1000-coils-per-year"]["comparisons"]
        high = result["scenarios"]["10000-coils-per-year"]["comparisons"]
        cw_low = next(pair for pair in low if pair["baseline"] == "manual" and pair["candidate"] == "cw02")
        cw_high = next(pair for pair in high if pair["baseline"] == "manual" and pair["candidate"] == "cw02")
        self.assertLess(cw_low["result"]["metrics"]["horizon_net_saving"]["value"], 0)
        self.assertGreater(cw_high["result"]["metrics"]["horizon_net_saving"]["value"], 0)
        self.assertEqual(cw_high["result"]["decision"], "undetermined")
        self.assertEqual(cw_high["result"]["status"], "insufficient_evidence")

    def test_capacity_shortfall_blocks_comparison(self) -> None:
        """Higher demand cannot silently allocate extra manual stations or overtime."""
        result = evaluate_alternatives(self.fixture())
        pairs = result["scenarios"]["30000-coils-per-year"]["comparisons"]
        manual = [pair for pair in pairs if pair["baseline"] == "manual"]
        self.assertTrue(all(pair["result"]["status"] == "infeasible_capacity" for pair in manual))
        self.assertTrue(all(pair["result"]["decision"] == "undetermined" for pair in manual))

    def test_boundary_ids_units_and_verification_rejected(self) -> None:
        """Reject partial boundaries, duplicate identities, bad rates and fake evidence."""
        original = self.fixture().model_dump()
        mutations = [
            lambda d: d["options"][1]["option"]["process"].update(boundary="winding only"),
            lambda d: d["options"][1].update(id=d["options"][0]["id"]),
            lambda d: d["scenarios"][0]["annual_demand"].update(unit="count"),
            lambda d: d.update(equivalence_verified=True, equivalence_source="synthetic assumption"),
            lambda d: d["options"][0]["option"]["process"].update(acceptance_verified=True, acceptance_source="synthetic"),
        ]
        for mutation in mutations:
            data = copy.deepcopy(original)
            mutation(data)
            with self.assertRaises(ValueError):
                AlternativeSet.model_validate(data)

    def test_network_blocked_replay_and_output_preservation(self) -> None:
        """Execute deterministically without connections or overwriting prior runs."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(socket.socket, "connect", side_effect=AssertionError("network prohibited")), patch("socket.create_connection", side_effect=AssertionError("network prohibited")):
                first = run_alternatives(FIXTURES / "illustrative-input.json", root / "first")
                second = run_alternatives(FIXTURES / "illustrative-input.json", root / "second")
            self.assertEqual(first, second)
            original = (root / "first/summary.json").read_bytes()
            with self.assertRaises(FileExistsError):
                run_alternatives(FIXTURES / "illustrative-input.json", root / "first")
            self.assertEqual(original, (root / "first/summary.json").read_bytes())
            self.assertEqual(json.loads(original)["overall_recommendation"], "undetermined")


if __name__ == "__main__":
    unittest.main()
