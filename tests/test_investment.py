"""Independent investment arithmetic, sensitivity and feasibility tests."""
from __future__ import annotations

import unittest

from pydantic import ValidationError

from protocol_pipeline.evaluation import UNITS, ProcessEvaluationInput
from protocol_pipeline.investment import (
    InvestmentComparisonInput, InvestmentOption, SensitivityScenario,
    UPFRONT_KEYS, compare_investment,
)
from protocol_pipeline.models import EngineeringValue


def quantity(value: float | None, unit: str) -> EngineeringValue:
    """Create explicitly sourced test assumptions or a true unknown."""
    return EngineeringValue(value=value, unit=unit, basis="unknown" if value is None else "assumed",
                            source=None if value is None else "Synthetic test assumption")


def option(name: str, unit_cost: float, capital: float, fixed: float) -> InvestmentOption:
    """Build a synthetic full variable-cost batch yielding 100 accepted units/hour."""
    numbers = {key: 0.0 for key in UNITS}
    numbers.update(accepted_count=100, attempted_count=100, elapsed_s=3600, stock_cost=unit_cost * 100)
    process = ProcessEvaluationInput(configuration_id=name, functional_unit="One accepted test part",
        boundary="Complete recurring production process", acceptance_verified=True,
        acceptance_source="Synthetic shared quality specification",
        inputs={key: quantity(value, UNITS[key]) for key, value in numbers.items()})
    return InvestmentOption(process=process, cost_model_source="Synthetic constant variable cost",
        capacity_model_source="Nominal rate excludes utilization/downtime losses",
        upfront={key: quantity(capital if key == "equipment" else 0, "USD") for key in UPFRONT_KEYS},
        annual_fixed_cost=quantity(fixed, "USD/year"), scheduled_hours=quantity(1000, "h/year"),
        utilization=quantity(1, "fraction"), downtime=quantity(0, "fraction"), useful_life=quantity(10, "years"))


def comparison() -> InvestmentComparisonInput:
    """Provide an independent case: 3 USD/unit savings, 2000 fixed, 10000 capital."""
    return InvestmentComparisonInput(baseline=option("manual", 5, 0, 1000),
        candidate=option("machine", 2, 10000, 3000),
        equivalence_verified=True, equivalence_source="Synthetic equivalence evidence",
        annual_demand=quantity(10000, "accepted outputs/year"), horizon_years=quantity(5, "years"))


class InvestmentTests(unittest.TestCase):
    """Check formulas against independent expected results and blocking gates."""

    def test_arithmetic(self) -> None:
        """Account for fixed and variable costs, capital and horizon exactly once."""
        result = compare_investment(comparison()).base
        self.assertEqual(result.status, "calculated")
        self.assertEqual(result.decision, "candidate_lower_cost")
        self.assertEqual(result.metrics["baseline.annual_operating_cost"].value, 51000)
        self.assertEqual(result.metrics["candidate.annual_operating_cost"].value, 23000)
        self.assertEqual(result.metrics["incremental_upfront"].value, 10000)
        self.assertEqual(result.metrics["horizon_net_saving"].value, 130000)
        self.assertAlmostEqual(result.metrics["simple_payback_years"].value, 10000 / 28000)
        self.assertAlmostEqual(result.metrics["horizon_break_even_annual_volume"].value, 4000 / 3)

    def test_missing_deployment_cost(self) -> None:
        """Missing installation cannot become zero or an investment recommendation."""
        data = comparison()
        del data.candidate.upfront["installation"]
        report = compare_investment(data)
        self.assertEqual(report.base.status, "insufficient_evidence")
        self.assertEqual(report.base.decision, "undetermined")
        self.assertIsNone(report.base.metrics["horizon_net_saving"].value)
        self.assertIsNone(report.base.metrics["simple_payback_years"].value)

    def test_capacity(self) -> None:
        """Cheap infrastructure still fails if it cannot serve the demand."""
        data = comparison()
        data.candidate.utilization = quantity(0.1, "fraction")
        data.candidate.downtime = quantity(0.1, "fraction")
        result = compare_investment(data).base
        self.assertEqual(result.metrics["candidate.annual_capacity"].value, 9000)
        self.assertEqual(result.status, "infeasible_capacity")
        self.assertEqual(result.decision, "undetermined")

    def test_equivalence(self) -> None:
        """Matching text alone does not verify physical output equivalence."""
        data = comparison()
        data.equivalence_verified = False
        self.assertEqual(compare_investment(data).base.status, "insufficient_evidence")
        data = comparison()
        data.candidate.process.acceptance_verified = False
        self.assertEqual(compare_investment(data).base.decision, "undetermined")

    def test_short_life(self) -> None:
        """Reject cost conclusions that require an unmodeled replacement."""
        data = comparison()
        data.candidate.useful_life = quantity(2, "years")
        self.assertEqual(compare_investment(data).base.status, "unsupported_horizon")

    def test_no_recurring_savings(self) -> None:
        """Do not divide by negative or zero annual savings to invent payback."""
        data = comparison()
        data.candidate = option("machine", 6, 10000, 3000)
        result = compare_investment(data).base
        self.assertEqual(result.decision, "baseline_lower_cost")
        self.assertEqual(result.metrics["simple_payback_years"].status, "undefined")
        self.assertEqual(result.horizon_break_even_direction, "no_volumes")

    def test_lower_capital_higher_operating_cost(self) -> None:
        """Reverse break-even direction when lower capital offsets higher unit cost."""
        data = comparison()
        data.baseline = option("manual", 2, 10000, 1000)
        data.candidate = option("machine", 3, 0, 1000)
        result = compare_investment(data).base
        self.assertEqual(result.horizon_break_even_direction, "below")
        self.assertEqual(result.metrics["horizon_break_even_annual_volume"].value, 2000)
        self.assertEqual(result.decision, "baseline_lower_cost")

    def test_no_unit_difference(self) -> None:
        """Equal unit costs use capital/fixed burden without dividing by zero."""
        data = comparison()
        data.candidate = option("machine", 5, 10000, 1000)
        result = compare_investment(data).base
        self.assertEqual(result.horizon_break_even_direction, "no_volumes")
        self.assertEqual(result.metrics["horizon_break_even_annual_volume"].status, "undefined")

    def test_sensitivity(self) -> None:
        """Independent overrides change economics/capacity without mutating base inputs."""
        data = comparison()
        data.scenarios = [SensitivityScenario(name="low demand", overrides={
            "annual_demand": quantity(100, "accepted outputs/year")}),
            SensitivityScenario(name="low utilization", overrides={"candidate.utilization": quantity(0.05, "fraction")})]
        report = compare_investment(data)
        self.assertEqual(report.base.decision, "candidate_lower_cost")
        self.assertEqual(report.scenarios["low demand"].decision, "baseline_lower_cost")
        self.assertEqual(report.scenarios["low utilization"].status, "infeasible_capacity")
        self.assertEqual(data.annual_demand.value, 10000)

    def test_invalid_contracts(self) -> None:
        """Reject mismatched outputs, bad units/ranges and capital double counting."""
        for mutation in ("boundary", "fixed", "fraction", "unit", "scenario"):
            payload = comparison().model_dump()
            if mutation == "boundary":
                payload["candidate"]["process"]["boundary"] = "different"
            elif mutation == "fixed":
                payload["candidate"]["process"]["inputs"]["allocated_tooling_cost"]["value"] = 1
            elif mutation == "fraction":
                payload["candidate"]["downtime"]["value"] = 2
            elif mutation == "unit":
                payload["annual_demand"]["unit"] = "count"
            else:
                payload["scenarios"] = [{"name": "bad", "overrides": {"invented": quantity(1, "USD").model_dump()}}]
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                InvestmentComparisonInput.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
