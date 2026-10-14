"""Verify extraction scoring depends on explicit semantics and bound evidence."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from protocol_pipeline.benchmark import ExtractionReference, ExtractionReview, benchmark_files, score_extraction
from protocol_pipeline.compiler import ProtocolSpecification

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "examples/extraction-benchmark"
CANDIDATE = ROOT / "examples/extraction/executed/extracted-protocol.json"
SOURCE = ROOT / "examples/extraction/procedure.txt"


class BenchmarkTests(unittest.TestCase):
    """Check pending review, omissions, unsupported output, ordering and grounding."""

    def inputs(self) -> tuple[ProtocolSpecification, ExtractionReference, ExtractionReview]:
        """Load committed candidate/reference/review inputs used by CLI and CI."""
        return (ProtocolSpecification.model_validate_json(CANDIDATE.read_bytes()),
                ExtractionReference.model_validate_json((CASE / "reference.json").read_bytes()),
                ExtractionReview.model_validate_json((CASE / "fixture-review.json").read_bytes()))

    def test_pending_review_cannot_be_a_perfect_score(self) -> None:
        """Valid candidate IDs without semantic judgments produce pending metrics."""
        with tempfile.TemporaryDirectory() as folder:
            result = benchmark_files(CANDIDATE, CASE / "reference.json", SOURCE, Path(folder)/"pending")
            self.assertEqual(result["status"], "review_pending")
            self.assertIsNone(result["dimensions"]["steps"]["recall"])
            self.assertIsNone(result["dimensions"]["acceptance"]["recall"])
            self.assertEqual(len(result["dimensions"]["steps"]["pending_reference"]), 7)

    def test_reviewed_fixture_passes_without_claiming_live_quality(self) -> None:
        """An authored perfect fixture checks arithmetic, not a model accuracy claim."""
        candidate, reference, review = self.inputs()
        result = score_extraction(candidate, reference, review)
        self.assertEqual(result["dimensions"]["steps"]["recall"], 1)
        self.assertEqual(result["dimensions"]["ordering"]["preserved_fraction"], 1)
        self.assertEqual(result["dimensions"]["acceptance"]["recall"], 1)
        self.assertFalse(result["live_model_quality_established"])
        self.assertEqual(result["reference_status"], "assistant_authored_reference_requires_user_review")

    def test_missed_step_is_counted_without_id_matching_shortcuts(self) -> None:
        """Explicitly reviewed omission reduces recall and ordering preservation."""
        candidate, reference, review = self.inputs()
        payload = candidate.model_dump()
        payload["operations"] = [op for op in payload["operations"] if op["id"] != "grip_tube"]
        payload["capabilities"] = [cap for cap in payload["capabilities"] if "grip_tube" not in cap["operation_ids"]]
        payload["links"] = [link for link in payload["links"] if "grip_tube" not in (link["source"],link["target"])]
        for item in payload["acceptance_criteria"]:
            item["operation_ids"] = [key for key in item["operation_ids"] if key != "grip_tube"]
        review.step_matches = [match for match in review.step_matches if match.reference_id != "r3"]
        review.missed_reference_steps = ["r3"]
        result = score_extraction(ProtocolSpecification.model_validate(payload), reference, review)
        self.assertAlmostEqual(result["dimensions"]["steps"]["recall"], 6/7)
        self.assertEqual(result["dimensions"]["steps"]["precision"], 1)
        self.assertLess(result["dimensions"]["ordering"]["preserved_fraction"], 1)

    def test_valid_citations_still_need_semantic_support(self) -> None:
        """Reviewer can reject structurally valid citations; phases/order are separate."""
        candidate, reference, review = self.inputs()
        review.step_matches[0].grounding_supported = False
        candidate.operations[0].phase = "processing"
        candidate.links = [link.model_copy(update={"source":link.target,"target":link.source}) for link in candidate.links]
        candidate = ProtocolSpecification.model_validate(candidate.model_dump())
        result = score_extraction(candidate,reference,review)
        self.assertAlmostEqual(result["dimensions"]["steps"]["grounding_support"],6/7)
        self.assertEqual(result["dimensions"]["ordering"]["preserved_fraction"],0)
        self.assertAlmostEqual(result["dimensions"]["preparation_and_evidence"]["correct_fraction"],6/7)

    def test_unsupported_addition_and_incomplete_review(self) -> None:
        """Extra output lowers precision only after reviewer classification; no silent pass."""
        candidate,reference,review=self.inputs()
        payload=candidate.model_dump()
        extra=copy.deepcopy(payload["operations"][0]);extra.update(id="unsupported_extra",intent="Paint the station")
        payload["operations"].append(extra)
        cap=copy.deepcopy(payload["capabilities"][0]);cap.update(id="cap_extra",operation_ids=["unsupported_extra"])
        payload["capabilities"].append(cap)
        candidate=ProtocolSpecification.model_validate(payload)
        with self.assertRaises(ValueError):
            score_extraction(candidate,reference,review)
        review.unsupported_candidate_steps=["unsupported_extra"]
        result=score_extraction(candidate,reference,review)
        self.assertAlmostEqual(result["dimensions"]["steps"]["precision"],7/8)

    def test_source_review_hashes_and_outputs_are_preserved(self) -> None:
        """Source/candidate tampering cannot reuse old review; duplicate outputs fail."""
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            changed=root/"candidate.json";changed.write_bytes(CANDIDATE.read_bytes()+b" ")
            with self.assertRaisesRegex(ValueError,"Review hashes"):
                benchmark_files(changed,CASE/"reference.json",SOURCE,root/"changed",CASE/"fixture-review.json")
            source=root/"source.txt";source.write_text("changed procedure")
            with self.assertRaisesRegex(ValueError,"source hash"):
                benchmark_files(CANDIDATE,CASE/"reference.json",source,root/"wrong-source")
            output=root/"scored"
            benchmark_files(CANDIDATE,CASE/"reference.json",SOURCE,output,CASE/"fixture-review.json")
            original=(output/"summary.json").read_bytes()
            with self.assertRaises(FileExistsError):
                benchmark_files(CANDIDATE,CASE/"reference.json",SOURCE,output,CASE/"fixture-review.json")
            self.assertEqual(original,(output/"summary.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
