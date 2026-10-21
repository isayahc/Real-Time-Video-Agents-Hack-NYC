# SPDX-License-Identifier: MPL-2.0
"""Score extraction against independently authored references and explicit reviews.

Semantic alignment and citation support require review. The scorer does not
pretend matching identifiers or valid line spans prove semantic correctness.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .compiler import ProtocolSpecification
from .design import write_json
from .models import StrictModel


class ReferenceStep(StrictModel):
    """Expected source-supported operation, independent of candidate identifiers."""

    id: str
    description: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    phase: Literal["preparation", "processing", "finishing"]
    evidence: Literal["source_supported", "hypothesis"] = "source_supported"


class ReferenceLink(StrictModel):
    """Reviewed expected precedence or concurrent relationship."""

    source: str
    target: str
    relation: Literal["before", "during"]


class ReferenceAcceptance(StrictModel):
    """Expected acceptance check and supporting source evidence."""

    id: str
    description: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class ExtractionReference(StrictModel):
    """Versioned gold reference bound to the exact source bytes."""

    schema_version: Literal[1] = 1
    case_id: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    author: str = Field(min_length=1)
    status: Literal["assistant_authored_reference_requires_user_review", "reviewed_reference"]
    steps: list[ReferenceStep] = Field(min_length=1)
    links: list[ReferenceLink]
    acceptance: list[ReferenceAcceptance] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def identities(self) -> ExtractionReference:
        """Reject duplicate IDs and reference relationships with absent endpoints."""
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)) or len({item.id for item in self.acceptance}) != len(self.acceptance):
            raise ValueError("Reference IDs must be unique")
        if any(link.source not in ids or link.target not in ids or link.source == link.target for link in self.links):
            raise ValueError("Reference links must resolve to distinct steps")
        return self


class ReviewedMatch(StrictModel):
    """An explicit semantic alignment; citation support is a separate judgment."""

    reference_id: str
    candidate_id: str
    grounding_supported: bool | None = None
    rationale: str = Field(min_length=1)


class ExtractionReview(StrictModel):
    """Content-bound judgments; unreviewed candidates/references remain pending."""

    schema_version: Literal[1] = 1
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reference_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: str = Field(min_length=1)
    evidence_kind: Literal["recorded_fixture_review", "live_extraction_review"]
    complete: bool = False
    step_matches: list[ReviewedMatch] = Field(default_factory=list)
    missed_reference_steps: list[str] = Field(default_factory=list)
    unsupported_candidate_steps: list[str] = Field(default_factory=list)
    acceptance_matches: list[ReviewedMatch] = Field(default_factory=list)
    missed_reference_acceptance: list[str] = Field(default_factory=list)
    unsupported_candidate_acceptance: list[str] = Field(default_factory=list)


def score_extraction(candidate: ProtocolSpecification, reference: ExtractionReference,
                     review: ExtractionReview) -> dict[str, Any]:
    """Calculate audited coverage/order/grounding without automatic semantic grading."""
    candidate = ProtocolSpecification.model_validate(candidate.model_dump())
    reference = ExtractionReference.model_validate(reference.model_dump())
    review = ExtractionReview.model_validate(review.model_dump())
    candidate_steps = {op.id: op for op in candidate.operations}
    reference_steps = {step.id: step for step in reference.steps}
    candidate_acceptance = {item.id for item in candidate.acceptance_criteria}
    reference_acceptance = {item.id for item in reference.acceptance}
    dimensions: dict[str, Any] = {}
    for label, matches, missed, unsupported, ref_ids, candidate_ids in (
        ("steps", review.step_matches, review.missed_reference_steps, review.unsupported_candidate_steps, set(reference_steps), set(candidate_steps)),
        ("acceptance", review.acceptance_matches, review.missed_reference_acceptance, review.unsupported_candidate_acceptance, reference_acceptance, candidate_acceptance),
    ):
        mapped_reference = [match.reference_id for match in matches]
        mapped_candidate = [match.candidate_id for match in matches]
        if len(mapped_reference) != len(set(mapped_reference)) or len(mapped_candidate) != len(set(mapped_candidate)):
            raise ValueError("Initial benchmark requires one-to-one reviewed matches; split/merged alignments need explicit future support")
        if not set(mapped_reference + missed).issubset(ref_ids) or not set(mapped_candidate + unsupported).issubset(candidate_ids):
            raise ValueError("Review references unknown benchmark IDs")
        if len(missed) != len(set(missed)) or len(unsupported) != len(set(unsupported)) or set(mapped_reference) & set(missed) or set(mapped_candidate) & set(unsupported):
            raise ValueError("Review classifications overlap or contain duplicates")
        pending_reference = sorted(ref_ids - set(mapped_reference + missed))
        pending_candidate = sorted(candidate_ids - set(mapped_candidate + unsupported))
        pending_grounding = [match.candidate_id for match in matches if match.grounding_supported is None]
        if review.complete and (pending_reference or pending_candidate or pending_grounding):
            raise ValueError("Complete review must classify every item and judge citation support")
        dimensions[label] = {"matched": len(matches), "missed": missed, "unsupported": unsupported,
                             "pending_reference": pending_reference, "pending_candidate": pending_candidate,
                             "recall": len(matches) / len(ref_ids) if not pending_reference else None,
                             "precision": len(matches) / len(candidate_ids) if not pending_candidate else None,
                             "grounding_support": sum(match.grounding_supported is True for match in matches) / len(matches) if matches and not pending_grounding else None,
                             "grounding_pending": pending_grounding,
                             "grounding_failed": [match.candidate_id for match in matches if match.grounding_supported is False]}
    alignment = {match.reference_id: match.candidate_id for match in review.step_matches}
    adjacency: dict[str, set[str]] = {key: set() for key in candidate_steps}
    concurrent = {(link.source, link.target) for link in candidate.links if link.relation == "during"}
    for link in candidate.links:
        if link.relation == "before":
            adjacency[link.source].add(link.target)

    def precedes(start: str, finish: str) -> bool:
        """Accept transitive order without requiring identical graph edge choices."""
        pending = list(adjacency[start])
        visited: set[str] = set()
        while pending:
            key = pending.pop()
            if key == finish:
                return True
            if key not in visited:
                visited.add(key)
                pending.extend(adjacency[key])
        return False

    ordering = []
    for link in reference.links:
        if link.source not in alignment or link.target not in alignment:
            state = "unscorable_missing_step" if link.source in review.missed_reference_steps or link.target in review.missed_reference_steps else "pending_alignment"
        else:
            start, finish = alignment[link.source], alignment[link.target]
            state = "preserved" if (precedes(start, finish) if link.relation == "before" else (start, finish) in concurrent) else "not_preserved"
        ordering.append({**link.model_dump(), "status": state})
    prep = []
    for match in review.step_matches:
        expected = reference_steps[match.reference_id]
        actual = candidate_steps[match.candidate_id]
        # Phase and observation/hypothesis distinction are scored only on explicit reviewed alignments.
        prep.append({"reference_id": expected.id, "candidate_id": actual.id,
                     "phase_correct": expected.phase == actual.phase,
                     "evidence_class_correct": (actual.basis == "workflow_hypothesis") == (expected.evidence == "hypothesis")})
    dimensions["ordering"] = {"checks": ordering, "preserved_fraction": sum(item["status"] == "preserved" for item in ordering) / len(ordering) if ordering and not any(item["status"] == "pending_alignment" for item in ordering) else None}
    dimensions["preparation_and_evidence"] = {"checks": prep,
        "correct_fraction": sum(item["phase_correct"] and item["evidence_class_correct"] for item in prep) / len(reference.steps) if not dimensions["steps"]["pending_reference"] else None}
    return {"schema_version": 1, "case_id": reference.case_id,
            "status": "review_complete" if review.complete else "review_pending",
            "reference_status": reference.status, "review_evidence_kind": review.evidence_kind,
            "live_model_quality_established": False, "physical_validation": False,
            "dimensions": dimensions, "limitations": reference.limitations + [
                "Scores depend on reviewer semantic alignments and citation judgments, not automatic semantic verification.",
                "One-to-one initial matching; split or merged operations require a richer review contract.",
                "One authored text fixture is not evidence of general live-model extraction quality."]}


def benchmark_files(candidate_path: Path, reference_path: Path, source_path: Path,
                    output: Path, review_path: Path | None = None) -> dict[str, Any]:
    """Bind source/candidate/reference bytes, emit a review template or scored report."""
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    candidate_raw, reference_raw = candidate_path.read_bytes(), reference_path.read_bytes()
    candidate = ProtocolSpecification.model_validate_json(candidate_raw)
    reference = ExtractionReference.model_validate_json(reference_raw)
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != reference.source_sha256:
        raise ValueError("Reference source hash does not match supplied source")
    candidate_hash, reference_hash = hashlib.sha256(candidate_raw).hexdigest(), hashlib.sha256(reference_raw).hexdigest()
    review = ExtractionReview.model_validate_json(review_path.read_bytes()) if review_path else ExtractionReview(
        candidate_sha256=candidate_hash, reference_sha256=reference_hash, reviewer="Pending reviewer assignment",
        evidence_kind="recorded_fixture_review", complete=False)
    if review.candidate_sha256 != candidate_hash or review.reference_sha256 != reference_hash:
        raise ValueError("Review hashes do not match candidate/reference; rereview changed content")
    result = score_extraction(candidate, reference, review)
    result["hashes"] = {"candidate_sha256": candidate_hash, "reference_sha256": reference_hash, "source_sha256": reference.source_sha256}
    lines = ["# Extraction benchmark", "", f"**{result['status']}; reference: {reference.status}; evidence: {review.evidence_kind}.**", "",
             "| Dimension | Score | Pending judgments |", "| --- | --- | --- |"]
    for name, score, pending in (
        ("Step recall", result["dimensions"]["steps"]["recall"], len(result["dimensions"]["steps"]["pending_reference"])),
        ("Step precision", result["dimensions"]["steps"]["precision"], len(result["dimensions"]["steps"]["pending_candidate"])),
        ("Step grounding support", result["dimensions"]["steps"]["grounding_support"], len(result["dimensions"]["steps"]["grounding_pending"])),
        ("Ordering preserved", result["dimensions"]["ordering"]["preserved_fraction"], sum(item["status"] == "pending_alignment" for item in result["dimensions"]["ordering"]["checks"])),
        ("Preparation/evidence classification", result["dimensions"]["preparation_and_evidence"]["correct_fraction"], len(result["dimensions"]["steps"]["pending_reference"])),
        ("Acceptance recall", result["dimensions"]["acceptance"]["recall"], len(result["dimensions"]["acceptance"]["pending_reference"])),
    ):
        lines.append(f"| {name} | {'pending' if score is None else f'{score:.1%}'} | {pending} |")
    lines += ["", "## Explicit review differences", ""]
    for dimension in ("steps", "acceptance"):
        values = result["dimensions"][dimension]
        for key in ("missed", "unsupported", "grounding_failed", "pending_reference", "pending_candidate"):
            lines.append("- " + dimension + " " + key + ": " + (", ".join(values[key]) or "none"))
    lines += ["", "Ordering checks:", ""]
    for check in result["dimensions"]["ordering"]["checks"]:
        lines.append(f"- {check['source']} {check['relation']} {check['target']}: {check['status']}")
    lines += ["", "## Limits", ""] + ["- " + item for item in result["limitations"]]
    output.mkdir(parents=True)
    write_json(output / "summary.json", result)
    write_json(output / "review-template.json", review.model_dump())
    (output / "report.md").write_text("\n".join(lines) + "\n")
    return result
