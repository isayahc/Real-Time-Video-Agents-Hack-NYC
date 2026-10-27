# SPDX-License-Identifier: MPL-2.0
"""Exercise preset requests and verification gates with explicitly mocked HTTP."""
from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.request import Request

import pytest
from fastapi.testclient import TestClient

from protocol_pipeline.__main__ import main
from protocol_pipeline.model_config import DEFAULT_COMPILER_MODEL, DEFAULT_VISION_MODEL
from protocol_pipeline.pipeline import NebiusClient, ProviderResponseError
from protocol_pipeline.web import create_app
from scripts.verify_nebius import CompletionProbe, verify_nebius

ROOT = Path(__file__).resolve().parents[1]


def response(content: Any, model: str | None = DEFAULT_COMPILER_MODEL,
             finish: str = "stop") -> BytesIO:
    """Build a synthetic provider envelope; it is never live verification evidence."""
    return BytesIO(json.dumps({
        "id": "synthetic-test-response", "model": model,
        "usage": {"completion_tokens": 12},
        "choices": [{"finish_reason": finish, "message": {"content": json.dumps(content)}}],
    }).encode())


@pytest.mark.parametrize("model,settings", [
    (DEFAULT_COMPILER_MODEL, {"enable_thinking": False}),
    (DEFAULT_VISION_MODEL, {"thinking_mode": "disabled"}),
    ("custom/model", None),
])
def test_model_specific_payload(monkeypatch: pytest.MonkeyPatch, model: str,
                                settings: dict[str, Any] | None) -> None:
    """Verify the actual HTTP payload and trace, leaving unknown models untouched."""
    calls: list[dict[str, Any]] = []

    def send(request: Request, **kwargs: Any) -> BytesIO:
        """Capture the request body without storing authentication headers."""
        calls.append(json.loads(request.data))
        return response({"ready": True}, model)

    monkeypatch.setattr("protocol_pipeline.pipeline.urlopen", send)
    _, trace = NebiusClient("DO_NOT_SAVE").complete(model, CompletionProbe, "probe", [], 512)
    assert calls[0].get("chat_template_kwargs") == settings
    assert "response_format" not in calls[0]  # MiniMax uses prompted, strictly validated JSON.
    assert trace["finish_reason"] == "stop" and trace["max_tokens"] == 512
    assert trace["generation_settings"].get("chat_template_kwargs") == settings
    assert "DO_NOT_SAVE" not in json.dumps(trace)


@pytest.mark.parametrize("served,finish", [("Qwen/fallback", "stop"), (None, "stop"),
                                           (DEFAULT_COMPILER_MODEL, "length")])
def test_nvidia_identity_and_completion_gate(monkeypatch: pytest.MonkeyPatch,
                                           served: str | None, finish: str) -> None:
    """Reject substituted/missing identities and incomplete output, without fallback."""
    calls = []

    def send(request: Request, **kwargs: Any) -> BytesIO:
        """Return one deliberately invalid envelope."""
        calls.append(request)
        return response({"ready": True}, served, finish)

    monkeypatch.setattr("protocol_pipeline.pipeline.urlopen", send)
    with pytest.raises(ProviderResponseError) as caught:
        NebiusClient("secret").complete(DEFAULT_COMPILER_MODEL, CompletionProbe, "probe", [])
    assert len(calls) == 1
    assert caught.value.trace["served_model"] == served
    assert caught.value.trace["generation_settings"]["chat_template_kwargs"]["enable_thinking"] is False


@pytest.mark.parametrize("configured,expected", [
    (None, DEFAULT_COMPILER_MODEL), ("  ", DEFAULT_COMPILER_MODEL), (" Qwen/custom ", "Qwen/custom"),
])
def test_compiler_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                         configured: str | None, expected: str) -> None:
    """Expose nonblank defaults and deliberate overrides without changing presets."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NEBIUS_COMPILER_MODEL", raising=False)
    if configured is not None:
        monkeypatch.setenv("NEBIUS_COMPILER_MODEL", configured)
    with TestClient(create_app(tmp_path / "runs")) as client:
        config = client.get("/api/config").json()
        assert config["model"] == expected
        assert config["presets"] == {"model": DEFAULT_COMPILER_MODEL, "vision_model": DEFAULT_VISION_MODEL}


def test_verifier_without_key_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing credentials must fail before network access, never skip successfully."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_TOKEN_FACTORY_KEY", raising=False)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        """Any network call would violate the credential gate."""
        pytest.fail("Network called without credentials")

    monkeypatch.setattr("protocol_pipeline.pipeline.urlopen", forbidden)
    with pytest.raises(ValueError, match="Set NEBIUS"):
        verify_nebius(tmp_path / "out", DEFAULT_COMPILER_MODEL, ROOT / "examples/extraction/procedure.txt")
    result = json.loads((tmp_path / "out/verification.json").read_text())
    assert result["status"] == "failed" and result["failed_stage"] == "credentials"
    assert result["nvidia_model_verified"] is False


@pytest.mark.parametrize("catalog_present", [True, False])
def test_verifier_compiles_actual_contract_with_mocked_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, catalog_present: bool,
) -> None:
    """Exercise catalog → probe → extraction → real compiler using synthetic HTTP."""
    monkeypatch.setenv("NEBIUS_API_KEY", "TEST_SECRET_NOT_EVIDENCE")
    spec = json.loads((ROOT / "examples/extraction/recorded-response.json").read_text())["responses"][0]["response"]
    calls: list[Request] = []

    def send(request: Request, **kwargs: Any) -> BytesIO:
        """Supply only synthetic responses and record the real request sequence."""
        calls.append(request)
        if request.get_method() == "GET":
            return BytesIO(json.dumps({"data": [{"id": DEFAULT_COMPILER_MODEL}] if catalog_present else []}).encode())
        return response({"ready": True} if len(calls) == 2 else spec)

    monkeypatch.setattr("protocol_pipeline.pipeline.urlopen", send)
    out = tmp_path / "out"
    if not catalog_present:
        with pytest.raises(ValueError, match="not in this account"):
            verify_nebius(out, DEFAULT_COMPILER_MODEL, ROOT / "examples/extraction/procedure.txt")
        assert len(calls) == 1
        assert json.loads((out / "verification.json").read_text())["nvidia_model_verified"] is False
        return
    result = verify_nebius(out, DEFAULT_COMPILER_MODEL, ROOT / "examples/extraction/procedure.txt")
    assert len(calls) == 3 and result["operation_count"] == 7
    assert (out / result["report"]).is_file()
    assert result["traces"][0]["served_model"] == DEFAULT_COMPILER_MODEL
    for path in out.rglob("*"):
        if path.is_file():
            assert b"TEST_SECRET_NOT_EVIDENCE" not in path.read_bytes()
    with pytest.raises(FileExistsError):
        verify_nebius(out, DEFAULT_COMPILER_MODEL, ROOT / "examples/extraction/procedure.txt")


@pytest.mark.parametrize("catalog_present", [True, False])
def test_catalog_only_never_calls_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, catalog_present: bool,
) -> None:
    """Catalog evidence must never imply inference success or issue a POST."""
    monkeypatch.setenv("NEBIUS_API_KEY", "TEST_SECRET_NOT_EVIDENCE")
    calls: list[Request] = []

    def send(request: Request, **kwargs: Any) -> BytesIO:
        """Reject inference requests even when the requested model is present."""
        assert request.get_method() == "GET"
        calls.append(request)
        return BytesIO(json.dumps({"data": [{"id": DEFAULT_COMPILER_MODEL}]
                                  if catalog_present else []}).encode())

    monkeypatch.setattr("protocol_pipeline.pipeline.urlopen", send)
    out = tmp_path / "catalog"
    if catalog_present:
        result = verify_nebius(out, DEFAULT_COMPILER_MODEL, tmp_path / "unused.txt", catalog_only=True)
        assert result["status"] == "catalog_verified"
        assert result["artifact_sha256"]["catalog.json"]
        with pytest.raises(FileExistsError):
            verify_nebius(out, DEFAULT_COMPILER_MODEL, tmp_path / "unused.txt", catalog_only=True)
    else:
        with pytest.raises(ValueError, match="not in this account"):
            verify_nebius(out, DEFAULT_COMPILER_MODEL, tmp_path / "unused.txt", catalog_only=True)
    record = json.loads((out / "verification.json").read_text())
    assert record["nvidia_model_verified"] is False
    assert record["live_inference"] is False
    assert record["verification_scope"] == "catalog"
    assert len(calls) == 1
    assert not (out / "probe.json").exists()
    assert not (out / "extraction").exists()
    assert "TEST_SECRET_NOT_EVIDENCE" not in json.dumps(record)


def test_cli_extraction_uses_preset_without_model_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive the CLI into real compilation with the preset and mocked model output."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NEBIUS_API_KEY", "test-only")
    monkeypatch.delenv("NEBIUS_COMPILER_MODEL", raising=False)
    spec = json.loads((ROOT / "examples/extraction/recorded-response.json").read_text())["responses"][0]["response"]

    def send(request: Request, **kwargs: Any) -> BytesIO:
        """Assert the CLI-selected model reaches the HTTP boundary."""
        assert json.loads(request.data)["model"] == DEFAULT_COMPILER_MODEL
        return response(spec)

    monkeypatch.setattr("protocol_pipeline.pipeline.urlopen", send)
    monkeypatch.setattr(sys, "argv", ["protocol_pipeline", "extract-protocol", "--provider", "nebius",
                                    "--text", str(ROOT / "examples/extraction/procedure.txt"),
                                    "--output", str(tmp_path / "out")])
    main()
    assert (tmp_path / "out/compiled/report.md").is_file()
