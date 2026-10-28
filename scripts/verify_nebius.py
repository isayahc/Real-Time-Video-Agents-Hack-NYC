# SPDX-License-Identifier: MPL-2.0
"""Verify real NVIDIA inference and downstream compilation; never skip or replay."""
from __future__ import annotations

import argparse
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from protocol_pipeline.compiler import ProtocolSpecification
from protocol_pipeline.design import write_json
from protocol_pipeline.environment import load_environment
from protocol_pipeline.extraction import NebiusProvider, extract_protocol
from protocol_pipeline.model_config import model_presets
from protocol_pipeline.models import StrictModel
from protocol_pipeline.pipeline import ProviderResponseError, sha256


class CompletionProbe(StrictModel):
    """Minimal visible-JSON response used before a full protocol request."""

    ready: Literal[True]


def verify_nebius(output: Path, model: str, source: Path, *,
                  catalog_only: bool = False) -> dict[str, Any]:
    """Check the account catalog, probe JSON and compile a real extracted protocol.

    Catalog-only mode makes no inference calls. Otherwise calls are paid when
    credentials are configured. Missing credentials, absent
    models, incomplete output and failed compilation fail instead of skipping.
    Existing output directories are never overwritten. Evidence stays local for
    review before publication; source text and model outputs can be sensitive.
    """
    if not model.startswith("nvidia/"):
        raise ValueError("Choose a canonical nvidia/ model for NVIDIA verification.")
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                            capture_output=True, text=True, check=False)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                            capture_output=True, text=True, check=False)
    record: dict[str, Any] = {
        "schema_version": 1, "run_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested_model": model, "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "working_tree_dirty": bool(status.stdout) if status.returncode == 0 else None,
        "nvidia_model_verified": False, "physical_validation": False,
        "live_inference": False, "verification_scope": "catalog" if catalog_only else "inference",
        "implementation_sha256": {
            str(path.relative_to(root)): sha256(path)
            for path in sorted((root / "protocol_pipeline").glob("*.py"))
        },
        "verifier_sha256": sha256(Path(__file__)),
    }
    stage = "credentials"
    try:
        provider = NebiusProvider()
        stage = "catalog"
        ids = provider.client.available_models()
        write_json(output / "catalog.json", {"model_ids": ids, "inference_verified": False})
        if model not in ids:
            raise ValueError(f"Configured NVIDIA model is not in this account's catalog: {model}")
        if catalog_only:
            record.update({"status": "catalog_verified", "artifact_sha256": {
                "catalog.json": sha256(output / "catalog.json")},
                "limitations": ["Catalog membership does not establish successful NVIDIA inference."]})
            write_json(output / "verification.json", record)
            return record
        stage = "probe"
        probe, trace = provider.client.complete(
            model, CompletionProbe,
            'Return exactly the JSON object {"ready": true}. Do not return a bare boolean.',
            [{"type": "text", "text": 'Respond with {"ready": true}, matching the required object schema.'}],
            max_tokens=512)
        write_json(output / "probe.json", {"result": probe.model_dump(), "trace": trace})
        stage = "extract_and_compile"
        result = extract_protocol(provider, model, output / "extraction", text_path=source)
        spec = ProtocolSpecification.model_validate_json(
            (output / "extraction/extracted-protocol.json").read_bytes())
        record.update({"status": "completed", "nvidia_model_verified": True,
                       "live_inference": True, "source_sha256": sha256(source),
                       "operation_count": len(spec.operations), "traces": result["traces"],
                       "report": "extraction/compiled/report.md",
                       "limitations": ["Text integration smoke only; no vision or semantic accuracy proof.",
                                       "Generated apparatus and resource inputs require review."]})
    except (ValueError, RuntimeError, OSError) as error:
        record.update({"status": "failed", "failed_stage": stage,
                       "error_type": type(error).__name__, "error": str(error)})
        if isinstance(error, ProviderResponseError):
            record["provider_trace"] = error.trace
        write_json(output / "verification.json", record)
        raise
    record["artifact_sha256"] = {
        str(path.relative_to(output)): sha256(path)
        for path in sorted(output.rglob("*")) if path.is_file()
    }
    write_json(output / "verification.json", record)
    return record


def main() -> None:
    """Run the explicitly requested paid verification with preset model selection."""
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=model_presets()["model"])
    parser.add_argument("--catalog-only", action="store_true",
                        help="Record account catalog access without paid inference")
    parser.add_argument("--text", type=Path,
                        default=Path(__file__).resolve().parents[1] / "examples/extraction/procedure.txt")
    args = parser.parse_args()
    try:
        result = verify_nebius(args.output, args.model, args.text, catalog_only=args.catalog_only)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"NVIDIA verification failed: {error}\n")
    print(json.dumps({"status": result["status"], "model": args.model,
                      "evidence": str(args.output / "verification.json")}))


if __name__ == "__main__":
    main()
