"""Check evidence grounding, annotation separation and actual frame sampling."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from protocol_pipeline.models import EngineeringValue, Frame, ObservationGraph, ProtocolPlan
from protocol_pipeline.pipeline import NebiusClient, ingest, load_annotation, validate_graph, validate_plan, vision_content


def sample_graph() -> ObservationGraph:
    """Return an explicitly synthetic graph for reference-integrity checks."""
    evidence = {"evidence_frame_ids": ["f0", "f1"], "confidence": 0.7, "interpretation": "Synthetic fixture"}
    return ObservationGraph.model_validate({
        "objects": [{**evidence, "id": "wire", "description": "wire"}],
        "actions": [{**evidence, "id": "wind", "action": "wind", "object_ids": ["wire"], "start_s": 0, "end_s": 1}],
        "state_changes": [{**evidence, "id": "coil", "object_id": "wire", "before": "straight", "after": "helical", "action_ids": ["wind"]}],
        "limitations": ["Synthetic fixture; no live inference"]})


class PipelineTests(unittest.TestCase):
    """Meaningful contract failures and one real ffmpeg ingestion smoke path."""

    def frames(self) -> list[Frame]:
        """Provide two synthetic frame records for pure reference validation."""
        return [Frame(id=f"f{i}", path=f"{i}.jpg", timestamp_s=i, source_pts_s=i,
                      source_frame_index=i, sha256="0" * 64) for i in range(2)]

    def test_valid_graph(self) -> None:
        """Accept graph references that resolve to the provided timeline."""
        validate_graph(sample_graph(), self.frames())

    def test_missing_frame_rejected(self) -> None:
        """Reject claims citing pixels never supplied to inference."""
        graph = sample_graph()
        graph.actions[0].evidence_frame_ids = ["invented"]
        with self.assertRaises(ValueError):
            validate_graph(graph, self.frames())

    def test_wrong_interval_rejected(self) -> None:
        """Reject an action whose cited frame lies outside its interval."""
        graph = sample_graph()
        graph.actions[0].start_s = 0.5
        with self.assertRaises(ValueError):
            validate_graph(graph, self.frames())

    def test_capability_needs_source_operation(self) -> None:
        """Do not accept apparatus requirements with fabricated operation IDs."""
        plan = ProtocolPlan.model_validate({"operations": [], "required_capabilities": [
            {"id": "rotate", "name": "rotation", "operation_ids": ["missing"], "rationale": "fixture"}],
            "preprocessing_candidates": [], "unresolved_requirements": [], "limitations": []})
        with self.assertRaises(ValueError):
            validate_plan(plan, sample_graph())

    def test_unknown_is_not_zero(self) -> None:
        """Unknown costs/power cannot silently acquire a numeric zero."""
        with self.assertRaises(ValidationError):
            EngineeringValue(value=0, unit="W", basis="unknown")
        self.assertIsNone(EngineeringValue(unit="W", basis="unknown").value)

    def test_assumed_number_requires_source(self) -> None:
        """Require provenance for assumed engineering numbers."""
        with self.assertRaises(ValidationError):
            EngineeringValue(value=30, unit="W", basis="assumed")

    def test_annotation_alternative_and_preservation(self) -> None:
        """Support reference_procedure lists while preserving source bytes exactly."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scenario01_decoy0.json"
            raw = b'{"video_id":"scenario01_decoy0","objects":[{"description":"wire","position":[0.2,0.5]}],"reference_procedure":["Step A","Step B"],"extra_source_field":123}'
            path.write_bytes(raw)
            annotation, original = load_annotation(path)
            self.assertEqual(original, raw)
            self.assertEqual(annotation.ground_truth_text, "1. Step A\n2. Step B")
            self.assertEqual(annotation.objects[0].id, 1)

    def test_provider_response_validation_and_safe_trace(self) -> None:
        """Validate mocked provider output while retaining model identity and no key."""
        payload = {"id": "synthetic-response", "model": "example-vision", "usage": {"total_tokens": 10},
                   "choices": [{"finish_reason": "stop", "message": {"content": sample_graph().model_dump_json()}}]}
        with patch("protocol_pipeline.pipeline.urlopen", return_value=BytesIO(json.dumps(payload).encode())):
            graph, trace = NebiusClient("SYNTHETIC_SECRET").complete("example-vision", ObservationGraph, "fixture", [])
        self.assertEqual(graph.actions[0].id, "wind")
        self.assertEqual(trace["served_model"], "example-vision")
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(trace))

    def test_truncated_provider_response_rejected(self) -> None:
        """Do not accept incomplete model responses as valid observations."""
        payload = {"usage": {"completion_tokens": 6000, "completion_tokens_details": {"reasoning_tokens": 6000}},
                   "choices": [{"finish_reason": "length", "message": {"content": sample_graph().model_dump_json()}}]}
        with patch("protocol_pipeline.pipeline.urlopen", return_value=BytesIO(json.dumps(payload).encode())):
            with self.assertRaisesRegex(ValueError, "Reasoning consumed the entire output budget") as caught:
                NebiusClient("fixture").complete("example-vision", ObservationGraph, "fixture", [])
        self.assertEqual(caught.exception.trace["finish_reason"], "length")
        self.assertEqual(caught.exception.trace["usage"]["completion_tokens"], 6000)
        self.assertNotIn("Authorization", json.dumps(caught.exception.trace))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
    def test_real_video_ingestion_without_ground_truth_leak(self) -> None:
        """Decode real frames and ensure neither default nor hinted requests leak steps."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / "scenario01_decoy0.mp4"
            annotation_file = root / "scenario01_decoy0.json"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=5",
                            "-t", "2", "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
            annotation_file.write_text(json.dumps({"video_id": video.stem, "caption": "SECRET_GROUND_TRUTH",
                "objects": [{"id": 1, "description": "annotated wire", "position": [0.2, 0.5]}]}))
            run = root / "run"
            ingest(video, annotation_file, run, count=3)
            manifest = json.loads((run / "manifest.json").read_text())
            frames = [Frame.model_validate(frame) for frame in manifest["frames"]]
            self.assertEqual([frame.source_frame_index for frame in frames], [0, 4, 9])
            self.assertAlmostEqual(frames[-1].timestamp_s, 1.8)
            for hints in [False, True]:
                request = json.dumps(vision_content(run, frames, hints))
                self.assertNotIn("SECRET_GROUND_TRUTH", request)
                self.assertEqual("annotated wire" in request, hints)
            self.assertEqual((run / "ground-truth.original.json").read_bytes(), annotation_file.read_bytes())


if __name__ == "__main__":
    unittest.main()
