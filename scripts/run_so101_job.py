"""Run the existing SO-101 comparison and preserve evidence in local directories."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import TextIO
import uuid


def commands(source: Path, output: Path, oi: Path) -> list[list[str]]:
    """Build the same full evaluation and verification sequence used by CI."""
    python = sys.executable
    steps = [[python, "-m", "protocol_pipeline.seed_comparison",
              "--source-root", str(source), "--output", str(output)]]
    for candidate in ("reference_pocket", "cad_seat"):
        bundle = str(output / candidate)
        steps.append(["node", "--import", str(oi / "node_modules/tsx/dist/loader.mjs"),
                      "protocol_pipeline/seed_oi_bridge.mts", str(oi), bundle])
        steps.append([python, "-m", "protocol_pipeline.seed_simulation",
                      "--verify-output", bundle])
    steps.append([python, "-m", "protocol_pipeline.seed_comparison",
                  "--output", str(output), "--compare-only"])
    return steps


def execute(command: list[str], log: TextIO, timeout: float) -> None:
    """Execute one bounded step, retaining stdout and stderr without a shell."""
    print(json.dumps({"step": command}), flush=True)
    log.write(json.dumps({"step": command}) + "\n")
    log.flush()
    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                   timeout=timeout, check=True)


def run_job(source: Path, oi: Path, output_root: Path, work_root: Path,
            timeout_seconds: int = 2700) -> Path:
    """Run once; copy successful or failed evidence before propagating errors.

    The caller must create a writable output_root. Successful execution
    means verified simulation evidence, not successful planting or hardware proof.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if not output_root.is_dir():
        raise ValueError("Output root must already exist; create a writable local directory")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex
    destination = output_root / run_id
    destination.mkdir()  # Verify storage is writable before starting expensive work.
    local = work_root / run_id
    local.mkdir(parents=True)
    report: dict[str, object] = {
        "run_id": run_id, "status": "running", "evidence_kind": "simulation",
        "live_inference": False, "hardware_execution": False,
        "source_revision": os.environ.get("SOURCE_REVISION", "unrecorded"),
        "completed_steps": 0,
    }
    started = time.monotonic()
    error: Exception | None = None
    try:
        with (local / "job.log").open("w") as log:
            for command in commands(source.resolve(), local / "comparison", oi.resolve()):
                remaining = timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError("Evaluation time budget exhausted")
                execute(command, log, remaining)
                report["completed_steps"] = int(report["completed_steps"]) + 1
        report["status"] = "verified_simulation"
    except Exception as exc:
        error = exc
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        (local / "job.json").write_text(json.dumps(report, indent=2) + "\n")
        # Write the receipt last: its presence confirms the copy finished.
        for child in local.iterdir():
            if child.name == "job.json":
                continue
            if child.is_dir():
                shutil.copytree(child, destination / child.name)
            else:
                shutil.copy2(child, destination / child.name)
        shutil.copy2(local / "job.json", destination / "job.json")
        print(json.dumps({"artifacts": str(destination), **report}), flush=True)
    if error is not None:
        raise error
    return destination


def main() -> None:
    """Read native source, replay runtime and local evidence directory paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("runs/so101-source"))
    parser.add_argument("--oi-root", type=Path, default=Path("runs/oi-runtime"))
    parser.add_argument("--output-root", type=Path, default=Path("runs/so101-output"))
    parser.add_argument("--work-root", type=Path, default=Path("runs/so101-jobs"))
    parser.add_argument("--timeout-seconds", type=int, default=2700)
    args = parser.parse_args()
    run_job(args.source_root.resolve(), args.oi_root.resolve(), args.output_root.resolve(),
            args.work_root.resolve(), args.timeout_seconds)


if __name__ == "__main__":
    main()
