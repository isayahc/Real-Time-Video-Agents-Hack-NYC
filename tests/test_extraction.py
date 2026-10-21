"""Verify provider extraction, grounding, failure evidence and secret-free traces."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from protocol_pipeline.compiler import ProtocolSpecification
from protocol_pipeline.extraction import (NebiusProvider, ReplayProvider, create_provider,
                                         extract_protocol, validate_extraction)
from protocol_pipeline.models import ObservationGraph
from protocol_pipeline.pipeline import NebiusClient, ingest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/extraction"


class ExtractionTests(unittest.TestCase):
    """Exercise the actual Nebius adapter with mocked HTTP and deterministic replay."""

    def response(self) -> dict:
        """Read the committed explicitly synthetic response fixture."""
        return json.loads((FIXTURE / "recorded-response.json").read_text())["responses"][0]["response"]

    def test_nebius_text_request_and_compiler_handoff(self) -> None:
        """Send numbered source lines and compile validated JSON without leaking keys."""
        response = {"model":"selected-model", "choices":[{"finish_reason":"stop", "message":{"content":json.dumps(self.response())}}]}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"NEBIUS_API_KEY":"TEST_KEY_DO_NOT_PERSIST"}):
            with patch("protocol_pipeline.pipeline.urlopen", return_value=BytesIO(json.dumps(response).encode())) as request:
                result = extract_protocol(NebiusProvider(), "selected-model", Path(folder)/"run", text_path=FIXTURE/"procedure.txt")
            sent = json.loads(request.call_args.args[0].data)
            self.assertIn("L1:", sent["messages"][1]["content"][0]["text"])
            self.assertEqual(sent["model"], "selected-model")
            self.assertTrue(result["live_inference"])
            self.assertFalse(result["physical_validation"])
            for path in (Path(folder)/"run").rglob("*"):
                if path.is_file():
                    self.assertNotIn(b"TEST_KEY_DO_NOT_PERSIST", path.read_bytes())
            summary = json.loads((Path(folder)/"run/compiled/summary.json").read_text())
            self.assertFalse(summary["accounting"]["acceptance_verified"])

    def test_invalid_provenance_and_fabricated_values_rejected(self) -> None:
        """Reject invented source lines, reviewed claims and numerical imputation."""
        original = self.response()
        mutations = [
            lambda d: d["operations"][0].update(source_refs=["text:L99-L100"]),
            lambda d: d["operations"][0].update(basis="reviewed_source"),
            lambda d: d["operations"][0].update(attended_range_s=[1,2]),
            lambda d: d["resource_inputs"]["electricity_wh"].update(value=5,basis="assumed",source="invented"),
            lambda d: d["links"][0].update(basis="reviewed_source"),
        ]
        for mutation in mutations:
            data = copy.deepcopy(original)
            mutation(data)
            with self.assertRaises(ValueError):
                validate_extraction(ProtocolSpecification.model_validate(data), "text", 7)

    def test_failed_extraction_never_creates_compiled_success(self) -> None:
        """Invalid inference leaves input evidence and a failure marker, no plan."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            response = self.response()
            response["operations"][0]["source_refs"] = ["text:L80-L80"]
            fixture = root/"invalid.json"
            fixture.write_text(json.dumps({"responses":[{"contract":"ProtocolSpecification","response":response}]}))
            with self.assertRaises(ValueError):
                extract_protocol(ReplayProvider(fixture),"fixture",root/"run",text_path=FIXTURE/"procedure.txt")
            self.assertTrue((root/"run/extraction-failure.json").exists())
            self.assertFalse((root/"run/compiled").exists())
            self.assertFalse((root/"run/extraction-summary.json").exists())

    def test_no_implicit_provider_fallback_or_overwrite(self) -> None:
        """Missing keys/provider configuration fail; prior evidence is preserved."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                create_provider("nebius")
        with self.assertRaises(ValueError):
            create_provider("nebius", FIXTURE/"recorded-response.json")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"run"
            result = extract_protocol(create_provider("replay",FIXTURE/"recorded-response.json"),"fixture",path,text_path=FIXTURE/"procedure.txt")
            self.assertFalse(result["live_inference"])
            with self.assertRaises(FileExistsError):
                extract_protocol(create_provider("replay",FIXTURE/"recorded-response.json"),"fixture",path,text_path=FIXTURE/"procedure.txt")

    def test_malformed_provider_completion_is_rejected(self) -> None:
        """Malformed envelope and truncation fail before compiler output is accepted."""
        for raw in ({}, {"choices":[{"finish_reason":"stop","message":None}]}, {"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}):
            with patch("protocol_pipeline.pipeline.urlopen",return_value=BytesIO(json.dumps(raw).encode())):
                with self.assertRaises(ValueError):
                    NebiusClient("fixture").complete("model",ProtocolSpecification,"fixture",[])

    def test_incomplete_completion_retains_provider_diagnostics(self) -> None:
        """Preserve token exhaustion evidence, never emitting a compiled success."""
        raw = {"model": "served-compiler", "usage": {"completion_tokens": 12000},
               "choices": [{"finish_reason": "length", "message": {"content": "{partial"}}]}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"NEBIUS_API_KEY": "FIXTURE_KEY"}), \
             patch("protocol_pipeline.pipeline.urlopen", return_value=BytesIO(json.dumps(raw).encode())):
            output = Path(folder) / "failed"
            with self.assertRaisesRegex(ValueError, "finish_reason='length'"):
                extract_protocol(create_provider("nebius"), "compiler", output, text_path=FIXTURE / "procedure.txt")
            failure = json.loads((output / "extraction-failure.json").read_text())
            self.assertEqual(failure["provider_trace"]["usage"]["completion_tokens"], 12000)
            self.assertEqual(failure["provider_trace"]["message"]["content"], "{partial")
            self.assertNotIn("FIXTURE_KEY", json.dumps(failure))
            self.assertFalse((output / "compiled").exists())

    def test_source_citation_correction_is_bounded_and_preserved(self) -> None:
        """A live bad citation gets one evidence-bound correction; repeat failure stays failed."""
        good = self.response()
        bad = copy.deepcopy(good)
        bad["operations"][0]["source_refs"] = ["text:L999-L999"]
        envelope = lambda value: BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}).encode())
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"NEBIUS_API_KEY": "FIXTURE_KEY"}):
            root = Path(folder)
            stages = []
            with patch("protocol_pipeline.pipeline.urlopen", side_effect=[envelope(bad), envelope(good)]) as calls:
                extract_protocol(NebiusProvider(), "compiler", root / "corrected", text_path=FIXTURE / "procedure.txt", progress=stages.append)
            self.assertEqual(calls.call_count, 2)
            self.assertIn("correcting_protocol", stages)
            self.assertIn("text:L999-L999", calls.call_args.args[0].data.decode())
            self.assertTrue((root / "corrected/provider-candidate-1.json").exists())
            self.assertTrue((root / "corrected/provider-candidate-2.json").exists())
            self.assertTrue((root / "corrected/compiled/report.md").exists())
            with patch("protocol_pipeline.pipeline.urlopen", side_effect=[envelope(bad), envelope(bad)]) as calls:
                with self.assertRaisesRegex(ValueError, "text:L999-L999.*operation"):
                    extract_protocol(NebiusProvider(), "compiler", root / "failed", text_path=FIXTURE / "procedure.txt")
            self.assertEqual(calls.call_count, 2)
            self.assertFalse((root / "failed/compiled").exists())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"ffmpeg/ffprobe required")
    def test_video_pipeline_grounds_frames_without_annotation_leak(self) -> None:
        """Execute two real adapter stages with synthetic decoded frames and responses."""
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{"NEBIUS_API_KEY":"FIXTURE_KEY"}):
            root=Path(folder)
            video=root/"fixture.mp4"
            annotation=root/"fixture.json"
            subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=size=160x120:rate=5","-t","2","-pix_fmt","yuv420p",str(video)],check=True,capture_output=True)
            annotation.write_text(json.dumps({"video_id":"fixture","caption":"SECRET_GROUND_TRUTH_DO_NOT_SEND","objects":[]}))
            run=root/"ingested"
            ingest(video,annotation,run,count=2)
            frames=json.loads((run/"manifest.json").read_text())["frames"]
            refs=[frame["id"] for frame in frames]
            evidence={"evidence_frame_ids":refs,"confidence":0.5,"interpretation":"Synthetic test inference"}
            graph={"objects":[{**evidence,"id":"tube","description":"synthetic tube"}],"actions":[{**evidence,"id":"transfer","action":"transfer","object_ids":["tube"],"start_s":0,"end_s":frames[-1]["timestamp_s"]}],"state_changes":[],"limitations":["Synthetic fixture, not real video interpretation"]}
            spec=self.response()
            op=spec["operations"][3]
            op.update(object_ids=["tube"],source_refs=["action:transfer"])
            spec["operations"]=[op];spec["links"]=[]
            cap=spec["capabilities"][3];cap["operation_ids"]=[op["id"]];spec["capabilities"]=[cap]
            criterion=spec["acceptance_criteria"][1]
            criterion.update(operation_ids=[op["id"]],source_refs=["hypothesis:handling requires inspection"])
            spec["acceptance_criteria"]=[criterion]
            envelopes=[{"choices":[{"finish_reason":"stop","message":{"content":json.dumps(value)}}]} for value in [graph,spec]]
            with patch("protocol_pipeline.pipeline.urlopen",side_effect=[BytesIO(json.dumps(value).encode()) for value in envelopes]) as calls:
                extract_protocol(NebiusProvider(),"compiler-model",root/"extracted",run=run,vision_model="vision-model")
            self.assertEqual(calls.call_count,2)
            for call in calls.call_args_list:
                self.assertNotIn("SECRET_GROUND_TRUTH_DO_NOT_SEND",call.args[0].data.decode())
            observed=ObservationGraph.model_validate(graph)
            invalid=ProtocolSpecification.model_validate(spec)
            invalid.operations[0].source_refs=["action:invented"]
            with self.assertRaises(ValueError):
                validate_extraction(invalid,"video",graph=observed)
            empty={"objects":[],"actions":[],"state_changes":[],"limitations":["No visible action evidence"]}
            response={"choices":[{"finish_reason":"stop","message":{"content":json.dumps(empty)}}]}
            with patch("protocol_pipeline.pipeline.urlopen",return_value=BytesIO(json.dumps(response).encode())):
                with self.assertRaisesRegex(ValueError,"No source-supported actions"):
                    extract_protocol(NebiusProvider(),"compiler-model",root/"no-actions",run=run,vision_model="vision-model")
            self.assertFalse((root/"no-actions/compiled").exists())


if __name__ == "__main__":
    unittest.main()
