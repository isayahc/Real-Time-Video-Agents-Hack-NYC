"""Exercise the native Python SDK against a mock OpenCode server transport."""
import copy
import importlib.util
import json
import tempfile
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")
sdk = pytest.importorskip("opencode_ai")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("opencode_example", ROOT / "examples/debug-extraction/run-opencode.py")
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


def test_sdk_extraction_corrects_capability_coverage_and_compiles():
    candidate = json.loads((ROOT / "examples/extraction/recorded-response.json").read_text())["responses"][0]["response"]
    incomplete = copy.deepcopy(candidate)
    incomplete["capabilities"] = incomplete["capabilities"][:1]
    incomplete["operations"].append(dict(incomplete["operations"][0], id="unmapped-operation"))
    prompts = []

    def handle(request):
        if request.url.path == "/session":
            return httpx.Response(200, json={"id": "ses_mock"})
        assert request.url.path == "/session/ses_mock/message"
        body = json.loads(request.content)
        assert body["model"]["modelID"] == "test-model"
        assert body["format"]["type"] == "json_schema"
        prompts.append(body["parts"][0]["text"])
        return httpx.Response(200, json={"info": {
            "modelID": "test-model",
            "structured_output": incomplete if len(prompts) == 1 else candidate,
        }, "parts": []})

    with sdk.Opencode(base_url="http://mock", http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "run"
            example.extract_protocol(example.SDKProvider(client), "test-model", output, text_path=example.SOURCE)
            assert (output / "compiled/report.md").exists()
            summary = json.loads((output / "extraction-summary.json").read_text())
            assert summary["traces"][0]["attempt_count"] == 2
    assert "L1:" in prompts[0]
    assert "Every operation requires a capability mapping" in prompts[1]
