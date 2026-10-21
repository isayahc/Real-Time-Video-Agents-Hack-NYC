# SPDX-License-Identifier: MPL-2.0
"""End-to-end iteration tests: lineage, observations, revisions and economics."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from protocol_pipeline.evaluation import evaluate_process
from protocol_pipeline.iteration import (
    DeviationTolerance, OutcomeRequest, PredictionRequest, RevisionRequest,
    differences, load_record, observe, predict, revise,
)
from test_investment import comparison, quantity


def prediction_request() -> PredictionRequest:
    """Make an explicitly synthetic process/investment prediction."""
    investment = comparison()
    return PredictionRequest(process=investment.candidate.process, investment=investment,
                             conditions="Synthetic benchmark batch of 100 attempts")


def outcome_request() -> OutcomeRequest:
    """Make fabricated observations explicitly labeled illustrative, not physical."""
    process = prediction_request().process.model_copy(deep=True)
    process.inputs['labor_s'] = quantity(1200, 'operator-s')
    process.inputs['loaded_labor_rate'] = quantity(30, 'USD/operator-hour')
    process.inputs['elapsed_s'] = quantity(4500, 's')
    return OutcomeRequest(process=process, evidence_kind='illustrative',
        evidence_refs=['Synthetic unit-test fixture; no physical or simulated run'],
        conditions='Synthetic benchmark batch of 100 attempts')


class IterationTests(unittest.TestCase):
    """Verify the feedback loop never replaces prediction evidence with outcomes."""

    def setUp(self) -> None:
        """Create an isolated append-only store for each test."""
        self.folder = tempfile.TemporaryDirectory()
        self.store = Path(self.folder.name)

    def tearDown(self) -> None:
        """Remove only the test store after each case."""
        self.folder.cleanup()

    def test_full_loop(self) -> None:
        """Preserve v1, compare outcome, and reevaluate revised process and investment."""
        first = predict(self.store, 'p1', prediction_request())
        original = (self.store / 'p1.json').read_bytes()
        observed = observe(self.store, 'o1', 'p1', outcome_request())
        self.assertTrue(observed.record.deviation.metrics['accepted_outputs_per_hour'].outside_tolerance)
        self.assertEqual(observed.record.deviation.metrics['cost_usd_per_accepted'].compared_value, 2.1)
        self.assertEqual(observed.record.investment_report.base.metrics['annual_operating_saving'].value, 27000)
        proposal = prediction_request()
        proposal.process.inputs['labor_s'] = quantity(600, 'operator-s')
        proposal.process.inputs['loaded_labor_rate'] = quantity(30, 'USD/operator-hour')
        # Deep copies avoid dependence on Pydantic object-sharing semantics.
        proposal.investment.candidate.process = proposal.process.model_copy(deep=True)
        updated = revise(self.store, 'p2', 'p1', 'o1', RevisionRequest(prediction=proposal,
            rationale='Reduce attended work after slower synthetic outcome', proposed_changes=['Change handling fixture']))
        self.assertEqual(updated.record.version, 2)
        self.assertEqual(updated.record.parent.sha256, first.sha256)
        self.assertEqual(updated.record.responding_to.sha256, observed.sha256)
        self.assertIn('labor_s_per_accepted', updated.record.revision.predicted_improvements)
        self.assertEqual(updated.record.investment_report.base.metrics['annual_operating_saving'].value, 27500)
        self.assertEqual((self.store / 'p1.json').read_bytes(), original)
        self.assertEqual(load_record(self.store, 'p2').sha256, updated.sha256)

    def test_duplicate_id_and_unsafe_path(self) -> None:
        """Duplicate IDs cannot overwrite, and unsafe IDs cannot escape the store."""
        predict(self.store, 'p1', prediction_request())
        before = (self.store / 'p1.json').read_bytes()
        with self.assertRaises(FileExistsError):
            predict(self.store, 'p1', prediction_request())
        self.assertEqual((self.store / 'p1.json').read_bytes(), before)
        with self.assertRaises(ValidationError):
            predict(self.store, '../escape', prediction_request())

    def test_tampering_detected(self) -> None:
        """Editing a prediction causes a canonical digest validation failure."""
        predict(self.store, 'p1', prediction_request())
        path = self.store / 'p1.json'
        raw = json.loads(path.read_text())
        raw['record']['request']['conditions'] = 'changed'
        path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            load_record(self.store, 'p1')

    def test_ancestor_tampering_detected(self) -> None:
        """Loading an outcome checks its referenced prediction, not only its own hash."""
        predict(self.store, 'p1', prediction_request())
        observe(self.store, 'o1', 'p1', outcome_request())
        path = self.store / 'p1.json'
        raw = json.loads(path.read_text())
        raw['record']['version'] = 9
        path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            load_record(self.store, 'o1')

    def test_outcome_mismatch(self) -> None:
        """Reject another apparatus or a different process boundary as this outcome."""
        predict(self.store, 'p1', prediction_request())
        outcome = outcome_request()
        outcome.process.configuration_id = 'different-machine'
        with self.assertRaises(ValueError):
            observe(self.store, 'o1', 'p1', outcome)

    def test_wrong_parent_outcome(self) -> None:
        """A revision must respond to an outcome of exactly its own parent."""
        predict(self.store, 'p1', prediction_request())
        predict(self.store, 'other', prediction_request())
        observe(self.store, 'o1', 'p1', outcome_request())
        with self.assertRaises(ValueError):
            revise(self.store, 'p2', 'other', 'o1', RevisionRequest(prediction=prediction_request(),
                rationale='test', proposed_changes=['test']))

    def test_physical_outcome_cannot_be_assumed(self) -> None:
        """Illustrative inputs cannot be relabeled physical without actual measurements."""
        payload = outcome_request().model_dump()
        payload['evidence_kind'] = 'physical'
        with self.assertRaises(ValidationError):
            OutcomeRequest.model_validate(payload)
        payload['evidence_kind'] = 'simulation'
        with self.assertRaises(ValidationError):
            OutcomeRequest.model_validate(payload)

    def test_partial_observation(self) -> None:
        """Missing costs stay unknown rather than becoming improvements or failures."""
        predict(self.store, 'p1', prediction_request())
        request = outcome_request()
        del request.process.inputs['stock_cost']
        outcome = observe(self.store, 'o1', 'p1', request)
        difference = outcome.record.deviation.metrics['cost_usd_per_accepted']
        self.assertIsNone(difference.absolute_delta)
        self.assertEqual(difference.direction, 'unknown')
        self.assertEqual(outcome.record.investment_report.base.decision, 'undetermined')

    def test_zero_prediction_absolute_tolerance(self) -> None:
        """Zero prediction uses absolute tolerance without inventing relative error."""
        predicted = prediction_request().process
        outcome = outcome_request().process
        delta = differences(evaluate_process(predicted), evaluate_process(outcome),
            {'labor_s_per_accepted': DeviationTolerance(absolute=20, relative=0.1)}).metrics['labor_s_per_accepted']
        self.assertIsNone(delta.relative_delta)
        self.assertEqual(delta.absolute_delta, 12)
        self.assertFalse(delta.outside_tolerance)

    def test_investment_candidate_must_match(self) -> None:
        """A process prediction cannot quietly evaluate another investment candidate."""
        request = prediction_request().model_dump()
        request['process']['inputs']['stock_cost']['value'] = 123
        with self.assertRaises(ValidationError):
            PredictionRequest.model_validate(request)

    def test_revision_cannot_drop_economics(self) -> None:
        """Preserve investment reevaluation when a parent includes investment metrics."""
        predict(self.store, 'p1', prediction_request())
        observe(self.store, 'o1', 'p1', outcome_request())
        proposal = prediction_request()
        proposal.investment = None
        with self.assertRaises(ValueError):
            revise(self.store, 'p2', 'p1', 'o1', RevisionRequest(prediction=proposal,
                rationale='test', proposed_changes=['test']))

    def test_unknown_revision_is_insufficient(self) -> None:
        """Unknown objectives cannot be reported as an improvement or stable result."""
        predict(self.store, 'p1', prediction_request())
        outcome = outcome_request()
        for item in outcome.process.inputs.values():
            item.value, item.basis, item.source = None, 'unknown', None
        observe(self.store, 'o1', 'p1', outcome)
        proposal = prediction_request()
        for item in proposal.process.inputs.values():
            item.value, item.basis, item.source = None, 'unknown', None
        proposal.investment.candidate.process = proposal.process.model_copy(deep=True)
        result = revise(self.store, 'p2', 'p1', 'o1', RevisionRequest(prediction=proposal,
            rationale='Wait for missing evidence', proposed_changes=['Collect a new measured run']))
        self.assertEqual(result.record.revision.conclusion, 'insufficient_evidence')

    def test_measured_partial_run_allowed(self) -> None:
        """Physical records can retain unknown costs while using measured physical quantities."""
        predict(self.store, 'p1', prediction_request())
        payload = outcome_request().model_dump()
        for key, item in payload['process']['inputs'].items():
            item['basis'] = 'measured'
            item['source'] = 'Synthetic test of measurement provenance validation'
        payload['evidence_kind'] = 'physical'
        payload['process']['inputs']['stock_cost'] = {'value': None, 'unit': 'USD/batch', 'basis': 'unknown'}
        result = observe(self.store, 'o1', 'p1', OutcomeRequest.model_validate(payload))
        self.assertEqual(result.record.deviation.metrics['cost_usd_per_accepted'].direction, 'unknown')


if __name__ == '__main__':
    unittest.main()
