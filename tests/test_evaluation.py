# SPDX-License-Identifier: MPL-2.0
"""Resource accounting tests covering costs, missing evidence and labor overlap."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from protocol_pipeline.evaluation import (
    AttendanceInterval, DIRECT_COSTS, ProcessEvaluationInput, UNITS,
    attendance_seconds, evaluate_file, evaluate_process,
)
from protocol_pipeline.models import EngineeringValue


def fixture() -> ProcessEvaluationInput:
    """Build a complete illustrative batch with independently checkable totals."""
    values = {key: 0.0 for key in UNITS}
    values.update(accepted_count=8, attempted_count=10, elapsed_s=3600,
                  labor_s=1800, electricity_wh=1000, consumed_stock_g=100,
                  recoverable_scrap_g=15, unrecovered_waste_g=5,
                  loaded_labor_rate=20, electricity_rate=0.2, stock_cost=40,
                  consumables_cost=2, allocated_tooling_cost=3, maintenance_cost=1,
                  facility_cost=4, other_utilities_cost=0.5, paid_coverage_cost=5,
                  recovery_credit=2)
    return ProcessEvaluationInput(
        configuration_id="test", functional_unit="one accepted test part",
        boundary="complete test batch", acceptance_verified=True,
        acceptance_source="test specification",
        inputs={key: EngineeringValue(value=value, unit=UNITS[key], basis="assumed",
                                      source="test fixture") for key, value in values.items()},
    )


class EvaluationTests(unittest.TestCase):
    """Check numerical results and refusal to silently invent missing inputs."""

    def test_full_accounting(self) -> None:
        """Charge each component once and subtract recovery once."""
        report = evaluate_process(fixture())
        self.assertAlmostEqual(report.metrics["total_cost_usd_per_batch"].value, 63.7)
        self.assertAlmostEqual(report.metrics["cost_usd_per_accepted"].value, 63.7 / 8)
        self.assertEqual(report.metrics["labor_s_per_accepted"].value, 225)
        self.assertEqual(report.metrics["electricity_wh_per_accepted"].value, 125)
        self.assertEqual(report.metrics["unrecovered_waste_g_per_accepted"].value, 0.625)
        self.assertEqual(report.metrics["accepted_outputs_per_hour"].value, 8)
        self.assertEqual(report.status, "complete_for_declared_boundary")
        self.assertEqual(report.metrics["cost_usd_per_accepted"].basis, "includes_assumptions")

    def test_unknown_cost_does_not_become_total(self) -> None:
        """A partial subtotal never masquerades as a full unit cost."""
        data = fixture()
        del data.inputs["maintenance_cost"]
        report = evaluate_process(data)
        self.assertIsNone(report.metrics["cost_usd_per_accepted"].value)
        self.assertIn("maintenance_cost", report.unknown_cost_components)
        self.assertAlmostEqual(report.known_cost_subtotal_usd_per_batch, 62.7)
        self.assertEqual(report.metrics["labor_s_per_accepted"].value, 225)

    def test_unknown_rate_even_with_zero_consumption(self) -> None:
        """A zero quantity does not silently supply a missing price."""
        data = fixture()
        del data.inputs["electricity_rate"]
        data.inputs["electricity_wh"].value = 0
        self.assertIsNone(evaluate_process(data).costs_usd_per_batch["electricity_cost"].value)

    def test_zero_output_is_undefined(self) -> None:
        """Failed production retains batch costs, without dividing by zero."""
        data = fixture()
        data.inputs["accepted_count"].value = 0
        report = evaluate_process(data)
        self.assertEqual(report.metrics["cost_usd_per_accepted"].status, "undefined")
        self.assertAlmostEqual(report.metrics["total_cost_usd_per_batch"].value, 63.7)

    def test_union_attendance(self) -> None:
        """Overlaps merge for one operator while a second operator adds labor."""
        events = [AttendanceInterval(operator_id=op, start_s=start, end_s=end,
                                     basis="measured", source="test recording")
                  for op, start, end in [("a", 0, 10), ("a", 5, 20), ("b", 0, 10)]]
        self.assertEqual(attendance_seconds(events), 30)
        data = fixture().model_dump()
        del data["inputs"]["labor_s"]
        data.update(attendance=[e.model_dump() for e in events], attendance_source="full attendance review")
        report = evaluate_process(ProcessEvaluationInput.model_validate(data))
        self.assertEqual(report.metrics["labor_s_per_accepted"].value, 30 / 8)

    def test_invalid_contracts(self) -> None:
        """Reject wrong units, negative/fractional counts and unsupported keys."""
        for key, field, value in [("accepted_count", "value", 11),
                                  ("accepted_count", "value", 0.5),
                                  ("labor_s", "value", -1),
                                  ("electricity_wh", "unit", "kWh"),
                                  ("stock_cost", "value", float("nan"))]:
            with self.subTest(key=key, value=value):
                data = fixture().model_dump()
                data["inputs"][key][field] = value
                with self.assertRaises(ValidationError):
                    ProcessEvaluationInput.model_validate(data)
        data = fixture().model_dump()
        data["inputs"]["invented"] = data["inputs"]["stock_cost"]
        with self.assertRaises(ValidationError):
            ProcessEvaluationInput.model_validate(data)

    def test_labor_exclusivity_and_boundary(self) -> None:
        """Prevent interval/aggregate double counting and out-of-run timestamps."""
        data = fixture().model_dump()
        data.update(attendance=[], attendance_source="confirmed none")
        with self.assertRaises(ValidationError):
            ProcessEvaluationInput.model_validate(data)
        del data["inputs"]["labor_s"]
        data["attendance"] = [dict(operator_id="a", start_s=0, end_s=3601,
                                   basis="measured", source="recording")]
        with self.assertRaises(ValidationError):
            ProcessEvaluationInput.model_validate(data)

    def test_empty_attendance_requires_source(self) -> None:
        """Zero labor must be explicit and sourced, not an absent recording."""
        data = fixture().model_dump()
        del data["inputs"]["labor_s"]
        data["attendance"] = []
        with self.assertRaises(ValidationError):
            ProcessEvaluationInput.model_validate(data)

    def test_acceptance_gate_and_snapshot(self) -> None:
        """A fully populated numerical scenario cannot imply verified equivalence."""
        data = fixture()
        data.acceptance_verified = False
        report = evaluate_process(data)
        self.assertEqual(report.status, "partial")
        self.assertEqual(report.input_snapshot.model_dump(), data.model_dump())

    def test_file_refuses_overwrite(self) -> None:
        """CLI report output is deterministic and existing artifacts are preserved."""
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "input.json", Path(folder) / "output.json"
            source.write_text(fixture().model_dump_json())
            evaluate_file(source, output)
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                evaluate_file(source, output)
            self.assertEqual(before, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
