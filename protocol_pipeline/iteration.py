"""Append-only prediction, observation and revision orchestration.

Records retain complete evaluator outputs and hashed parent links. Observations
never mutate predictions, and revised benefits remain predictions until tested.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .evaluation import ProcessEvaluationInput, ProcessEvaluationReport, evaluate_process
from .investment import InvestmentComparisonInput, InvestmentComparisonReport, compare_investment
from .models import StrictModel

OBJECTIVES = {
    "cost_usd_per_accepted": "lower", "labor_s_per_accepted": "lower",
    "electricity_wh_per_accepted": "lower", "stock_g_per_accepted": "lower",
    "unrecovered_waste_g_per_accepted": "lower", "accepted_outputs_per_hour": "higher",
}


class DeviationTolerance(StrictModel):
    """Absolute metric-unit and relative-fraction thresholds; use the larger."""

    absolute: float = Field(default=0, ge=0)
    relative: float = Field(default=0.1, ge=0)


class PredictionRequest(StrictModel):
    """A process prediction with optional matching investment comparison."""

    process: ProcessEvaluationInput
    investment: InvestmentComparisonInput | None = None
    conditions: str = Field(min_length=1)
    tolerances: dict[str, DeviationTolerance] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_candidate(self) -> PredictionRequest:
        """Require the investment candidate to be exactly the predicted process."""
        if self.investment and self.investment.candidate.process.model_dump() != self.process.model_dump():
            raise ValueError("Investment candidate must match prediction process exactly")
        if set(self.tolerances) - OBJECTIVES.keys():
            raise ValueError("Unsupported deviation metric")
        return self


class OutcomeRequest(StrictModel):
    """Evidence-labeled run; physical/simulation data cannot contain assumed numbers."""

    process: ProcessEvaluationInput
    evidence_kind: Literal["physical", "simulation", "illustrative"]
    evidence_refs: list[str] = Field(min_length=1)
    conditions: str = Field(min_length=1)

    @model_validator(mode="after")
    def observed_values(self) -> OutcomeRequest:
        """Keep fabricated or planning assumptions out of measured run records."""
        if any(not reference.strip() for reference in self.evidence_refs):
            raise ValueError("Evidence references cannot be blank")
        if self.evidence_kind != "illustrative":
            if any(item.basis == "assumed" for item in self.process.inputs.values()):
                raise ValueError("Physical/simulation outcomes cannot contain assumed inputs; leave unmeasured inputs unknown")
            if any(item.basis == "assumed" for item in (self.process.attendance or [])):
                raise ValueError("Observed attendance cannot be assumed")
            for key in ("accepted_count", "attempted_count", "elapsed_s", "labor_s", "electricity_wh", "consumed_stock_g", "recoverable_scrap_g", "unrecovered_waste_g"):
                item = self.process.inputs.get(key)
                if item and item.value is not None and item.basis != "measured":
                    raise ValueError(f"Observed physical quantity {key} must be measured")
        return self


class RevisionRequest(StrictModel):
    """Explicit proposed changes responding to a recorded outcome."""

    prediction: PredictionRequest
    rationale: str = Field(min_length=1)
    proposed_changes: list[str] = Field(min_length=1)


class MetricDifference(StrictModel):
    """Conditional difference without manufacturing values for missing metrics."""

    reference_value: float | None
    compared_value: float | None
    unit: str
    absolute_delta: float | None = None
    relative_delta: float | None = None
    outside_tolerance: bool | None = None
    direction: Literal["improved", "worsened", "unchanged", "unknown"] = "unknown"
    reason: str | None = None


class DeviationReport(StrictModel):
    """Per-output comparison with context/evidence qualifications."""

    metrics: dict[str, MetricDifference]
    warnings: list[str]
    reference_role: Literal["prediction", "outcome"] = "prediction"
    compared_role: Literal["prediction", "outcome"] = "outcome"


class RecordReference(StrictModel):
    """Safe store-local record identity plus a canonical-content digest."""

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class RevisionAssessment(StrictModel):
    """Proposed metric changes relative to the old prediction and observed run."""

    rationale: str
    proposed_changes: list[str]
    against_previous_prediction: DeviationReport
    against_outcome: DeviationReport
    predicted_improvements: list[str]
    predicted_regressions: list[str]
    conclusion: Literal["predicted_tradeoff", "predicted_improvement", "predicted_regression", "no_calculated_change", "insufficient_evidence"]
    note: str = "A revised prediction is not a demonstrated improvement; a new run is required."


class PredictionRecord(StrictModel):
    """One root prediction or branch revision with evaluator outputs and lineage."""

    kind: Literal["prediction"] = "prediction"
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    version: int = Field(ge=1)
    created_at: str
    parent: RecordReference | None = None
    responding_to: RecordReference | None = None
    request: PredictionRequest
    process_report: ProcessEvaluationReport
    investment_report: InvestmentComparisonReport | None = None
    revision: RevisionAssessment | None = None


class OutcomeRecord(StrictModel):
    """Evidence-bound outcome retaining the unchanged referenced prediction."""

    kind: Literal["outcome"] = "outcome"
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    created_at: str
    prediction: RecordReference
    request: OutcomeRequest
    process_report: ProcessEvaluationReport
    investment_report: InvestmentComparisonReport | None = None
    deviation: DeviationReport


Record = Annotated[PredictionRecord | OutcomeRecord, Field(discriminator="kind")]


class StoredRecord(StrictModel):
    """Versioned canonical-hash envelope for a store event."""

    schema_version: Literal[1] = 1
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    record: Record


def digest(payload: dict[str, Any]) -> str:
    """Hash a JSON-compatible record with stable ordering and finite numbers."""
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(content.encode()).hexdigest()


def record_path(store: Path, record_id: str) -> Path:
    """Reject unsafe IDs before constructing any filesystem path."""
    RecordReference(id=record_id, sha256="0" * 64)
    return store / f"{record_id}.json"


def load_record(store: Path, record_id: str) -> StoredRecord:
    """Check stored bytes and all hash-linked ancestors for corruption or cycles."""
    cache: dict[str, StoredRecord] = {}
    def load(current_id: str, seen: set[str]) -> StoredRecord:
        """Recursively validate lineage without trusting a detached parent digest."""
        if current_id in seen:
            raise ValueError("Cycle in iteration record lineage")
        if current_id in cache:
            return cache[current_id]
        raw = json.loads(record_path(store, current_id).read_text(encoding="utf-8"))
        if digest(raw["record"]) != raw["sha256"]:
            raise ValueError(f"Record integrity check failed: {current_id}")
        result = StoredRecord.model_validate(raw)
        if result.record.id != current_id:
            raise ValueError("Record identity does not match filename")
        refs = ([result.record.parent, result.record.responding_to]
                if isinstance(result.record, PredictionRecord) else [result.record.prediction])
        for reference in refs:
            if reference:
                target = load(reference.id, seen | {current_id})
                if target.sha256 != reference.sha256:
                    raise ValueError("Referenced ancestor digest changed")
        cache[current_id] = result
        return result
    return load(record_id, set())


def save_record(store: Path, record: PredictionRecord | OutcomeRecord) -> StoredRecord:
    """Atomically append a new record; never replace an existing record ID."""
    path = record_path(store, record.id)
    store.mkdir(parents=True, exist_ok=True)
    envelope = StoredRecord(sha256=digest(record.model_dump(mode="json")), record=record)
    descriptor, temporary = tempfile.mkstemp(prefix=".iteration-", suffix=".tmp", dir=store)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write(envelope.model_dump_json(indent=2) + "\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return envelope


def differences(predicted: ProcessEvaluationReport, actual: ProcessEvaluationReport,
                tolerances: dict[str, DeviationTolerance],
                reference_role: Literal["prediction", "outcome"] = "prediction",
                compared_role: Literal["prediction", "outcome"] = "outcome") -> DeviationReport:
    """Compare normalized metrics; flag deviations without equating them to failures."""
    result: dict[str, MetricDifference] = {}
    warnings: list[str] = []
    if not predicted.acceptance_verified or not actual.acceptance_verified:
        warnings.append("Output acceptance is unverified; apparent improvements are conditional.")
    if any(metric.basis == "includes_assumptions" for report in (predicted, actual) for metric in report.metrics.values()):
        warnings.append("Comparison includes assumed inputs; differences do not establish demonstrated physical improvement.")
    for key, preferred in OBJECTIVES.items():
        expected, observed = predicted.metrics[key], actual.metrics[key]
        item = MetricDifference(reference_value=expected.value, compared_value=observed.value, unit=expected.unit)
        if expected.value is None or observed.value is None:
            item.reason = "A required metric is unknown or undefined; no deviation can be calculated"
        else:
            delta = observed.value - expected.value
            tolerance = tolerances.get(key, DeviationTolerance())
            item.absolute_delta = delta
            item.relative_delta = delta / abs(expected.value) if expected.value != 0 else None
            item.outside_tolerance = abs(delta) > max(tolerance.absolute, tolerance.relative * abs(expected.value))
            item.direction = ("unchanged" if delta == 0 else "improved"
                              if (delta < 0 and preferred == "lower") or (delta > 0 and preferred == "higher") else "worsened")
            if expected.value == 0:
                item.reason = "Relative deviation is undefined at zero prediction; absolute tolerance is used"
        result[key] = item
    if any(item.direction == "unknown" for item in result.values()):
        warnings.append("Some objectives are unknown; this is a partial tradeoff assessment.")
    return DeviationReport(metrics=result, warnings=warnings, reference_role=reference_role, compared_role=compared_role)


def compatible(prediction: ProcessEvaluationInput, outcome: ProcessEvaluationInput,
               same_configuration: bool = True) -> None:
    """Prevent attaching a different output/boundary or apparatus as the same run."""
    if prediction.functional_unit != outcome.functional_unit or prediction.boundary != outcome.boundary:
        raise ValueError("Functional unit and process boundary must match the prediction")
    if same_configuration and prediction.configuration_id != outcome.configuration_id:
        raise ValueError("Outcome configuration does not match the prediction")


def reference(envelope: StoredRecord) -> RecordReference:
    """Build a lineage reference to exactly the evaluated stored record."""
    return RecordReference(id=envelope.record.id, sha256=envelope.sha256)


def now() -> str:
    """Return a UTC timestamp for event provenance."""
    return datetime.now(timezone.utc).isoformat()


def predict(store: Path, record_id: str, request: PredictionRequest) -> StoredRecord:
    """Evaluate and append a root prediction with optional investment metrics."""
    request = PredictionRequest.model_validate(request.model_dump())
    record = PredictionRecord(id=record_id, version=1, created_at=now(), request=request,
        process_report=evaluate_process(request.process),
        investment_report=compare_investment(request.investment) if request.investment else None)
    return save_record(store, record)


def observe(store: Path, record_id: str, prediction_id: str, request: OutcomeRequest) -> StoredRecord:
    """Attach an independently labeled run and reevaluate process/investment outcomes."""
    request = OutcomeRequest.model_validate(request.model_dump())
    parent = load_record(store, prediction_id)
    if not isinstance(parent.record, PredictionRecord):
        raise ValueError("Outcome must reference a prediction")
    prediction = parent.record
    compatible(prediction.request.process, request.process)
    process = evaluate_process(request.process)
    deviations = differences(prediction.process_report, process, prediction.request.tolerances)
    deviations.warnings.append(f"Evidence kind: {request.evidence_kind}; evidence references are supplied provenance, not independently verified here.")
    if request.conditions != prediction.request.conditions:
        deviations.warnings.append("Run conditions differ from prediction; attribute deviations only after reviewing those differences.")
    for key in ("attempted_count", "accepted_count"):
        left, right = prediction.request.process.inputs.get(key), request.process.inputs.get(key)
        if left and right and left.value != right.value:
            deviations.warnings.append(f"{key} differs; normalized metrics may still depend on batch size and yield.")
    investment = None
    if prediction.request.investment:
        payload = prediction.request.investment.model_dump()
        payload["candidate"]["process"] = request.process.model_dump()
        investment = compare_investment(InvestmentComparisonInput.model_validate(payload))
        deviations.warnings.append("Investment update substitutes the run's process inputs only; demand, baseline, upfront/fixed costs and capacity factors retain prediction assumptions.")
    return save_record(store, OutcomeRecord(id=record_id, created_at=now(), prediction=reference(parent),
        request=request, process_report=process, investment_report=investment, deviation=deviations))


def revise(store: Path, record_id: str, parent_id: str, outcome_id: str, request: RevisionRequest) -> StoredRecord:
    """Evaluate an explicit revision responding to the matching parent outcome."""
    request = RevisionRequest.model_validate(request.model_dump())
    parent, outcome = load_record(store, parent_id), load_record(store, outcome_id)
    if not isinstance(parent.record, PredictionRecord) or not isinstance(outcome.record, OutcomeRecord):
        raise ValueError("Revision requires a prediction parent and an outcome")
    if outcome.record.prediction != reference(parent):
        raise ValueError("Outcome belongs to a different parent prediction")
    compatible(parent.record.request.process, request.prediction.process, same_configuration=False)
    if parent.record.request.investment and not request.prediction.investment:
        raise ValueError("Revision cannot drop the parent's investment comparison")
    process = evaluate_process(request.prediction.process)
    previous = differences(parent.record.process_report, process, request.prediction.tolerances, compared_role="prediction")
    observed = differences(outcome.record.process_report, process, request.prediction.tolerances,
                           reference_role="outcome", compared_role="prediction")
    observed.warnings.append(f"Referenced outcome evidence kind: {outcome.record.request.evidence_kind}")
    if request.prediction.conditions != outcome.record.request.conditions:
        observed.warnings.append("Revision conditions differ from the outcome; metric changes may reflect changed operating assumptions.")
    improvements = [key for key, item in observed.metrics.items() if item.direction == "improved"]
    regressions = [key for key, item in observed.metrics.items() if item.direction == "worsened"]
    conclusion = ("predicted_tradeoff" if improvements and regressions else "predicted_improvement"
                  if improvements else "predicted_regression" if regressions else "insufficient_evidence"
                  if all(item.direction == "unknown" for item in observed.metrics.values()) else "no_calculated_change")
    assessment = RevisionAssessment(rationale=request.rationale, proposed_changes=request.proposed_changes,
        against_previous_prediction=previous, against_outcome=observed, predicted_improvements=improvements,
        predicted_regressions=regressions, conclusion=conclusion)
    return save_record(store, PredictionRecord(id=record_id, version=parent.record.version + 1,
        created_at=now(), parent=reference(parent), responding_to=reference(outcome),
        request=request.prediction, process_report=process,
        investment_report=compare_investment(request.prediction.investment) if request.prediction.investment else None,
        revision=assessment))
