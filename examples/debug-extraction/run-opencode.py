"""Run extraction with the native opencode-ai Python SDK."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import httpx
from opencode_ai import APIConnectionError, Opencode
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from protocol_pipeline.extraction import extract_protocol

SOURCE = ROOT / "examples" / "extraction" / "procedure.txt"
MODEL = os.environ.get("OPENCODE_MODEL", "Qwen/Qwen3-235B-A22B-Instruct-2507")
PROVIDER = os.environ.get("OPENCODE_PROVIDER", "nebius")
URL = os.environ.get("OPENCODE_URL", "http://127.0.0.1:4096").rstrip("/")


def server_health(client):
    """Check the health endpoint, which has no generated SDK resource method."""
    response = client.get("/global/health", cast_to=httpx.Response)
    return response.json()


@contextmanager
def open_server():
    """Reuse a server or start one locally; clean up only the owned process."""
    process = None
    with Opencode(base_url=URL, timeout=600.0, max_retries=2,
                  default_query={"directory": str(ROOT)}) as client:
        try:
            print(f"Checking OpenCode at {URL}...", flush=True)
            try:
                health = server_health(client.with_options(timeout=2, max_retries=0))
            except APIConnectionError:
                if URL != "http://127.0.0.1:4096":
                    raise RuntimeError(f"Start your OpenCode server at {URL} first") from None
                executable = shutil.which("opencode")
                if executable is None:
                    raise RuntimeError("OpenCode CLI was not found on PATH") from None
                command = [executable, "serve", "--hostname", "127.0.0.1", "--port", "4096"]
                if os.name == "nt" and Path(executable).suffix.lower() in (".cmd", ".bat"):
                    command = [os.environ.get("COMSPEC", "cmd.exe"), "/c", *command]
                print("Starting OpenCode server...", flush=True)
                process = subprocess.Popen(command, cwd=ROOT)
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(f"OpenCode exited with code {process.returncode}")
                    try:
                        health = server_health(client.with_options(timeout=1, max_retries=0))
                        break
                    except APIConnectionError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("OpenCode startup exceeded 30 seconds") from None
                        time.sleep(0.25)
            if not health.get("healthy"):
                raise RuntimeError("OpenCode health check failed")
            print(f"OpenCode ready ({health.get('version', 'unknown version')}).", flush=True)
            yield client
        finally:
            if process is not None and process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


class SDKProvider:
    """Adapt the Python SDK to the existing extraction pipeline."""

    name = "opencode-python-sdk"
    live = True

    def __init__(self, client):
        self.client = client

    def complete(self, model, contract, instruction, content):
        if any(part.get("type") != "text" for part in content):
            raise ValueError("This example supports text extraction only")
        session = self.client.session.create(extra_body={"title": "Protocol extraction"})
        print(f"Session: {session.id}\nRequesting {PROVIDER}/{model}...", flush=True)
        prompt = instruction + "\n\n" + "\n".join(part["text"] for part in content)
        started = time.monotonic()
        # JSON Schema cannot express cross-field rules such as full capability coverage.
        for attempt in range(3):
            # The generated SDK predates nested `model` and `format` fields.
            # extra_body adds those fields; raw response preserves the current
            # {info, parts} envelope rather than the SDK's older message type.
            response = self.client.session.with_raw_response.chat(
                session.id,
                provider_id=PROVIDER,
                model_id=model,
                parts=[{"type": "text", "text": prompt}],
                extra_body={
                    "model": {"providerID": PROVIDER, "modelID": model},
                    "format": {"type": "json_schema", "schema": contract.model_json_schema(), "retryCount": 3},
                },
            ).json()
            info = response.get("info", {})
            if info.get("error"):
                raise RuntimeError(f"OpenCode session {session.id}: {info['error']}")
            structured = info.get("structured_output")
            if structured is None:
                raise ValueError(f"OpenCode session {session.id} returned no structured output")
            try:
                parsed = contract.model_validate(structured)
            except ValidationError as error:
                if attempt == 2:
                    raise
                print("Candidate failed local validation; requesting correction...", flush=True)
                prompt = "Correct the previous candidate using these validation errors:\n" + error.json(include_input=False)
                continue
            print("Candidate validated. Compiling...", flush=True)
            return parsed, {"requested_model": model, "served_model": info.get("modelID"),
                            "provider": PROVIDER, "session_id": session.id, "usage": info.get("tokens"),
                            "latency_s": time.monotonic() - started, "attempt_count": attempt + 1,
                            "provenance": "live_opencode_python_sdk_inference; not source ground truth"}


def main():
    output = ROOT / "runs" / f"opencode-extraction-{datetime.now():%Y%m%d-%H%M%S-%f}"
    print(f"Output: {output}", flush=True)
    with open_server() as client:
        extract_protocol(SDKProvider(client), MODEL, output, text_path=SOURCE)
    print(f"Done: {output / 'compiled' / 'report.md'}", flush=True)


if __name__ == "__main__":
    main()
