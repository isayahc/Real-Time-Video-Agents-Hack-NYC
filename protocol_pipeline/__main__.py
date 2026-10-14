"""CLI for ingestion and explicitly requested live Nebius analysis."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from .pipeline import analyze, ingest


def main() -> None:
    """Parse commands and execute one pipeline stage with clear failure status."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("ingest", help="Preserve annotations and sample timestamped video frames; no model calls")
    read.add_argument("--video", type=Path, required=True)
    read.add_argument("--annotation", type=Path, required=True)
    read.add_argument("--output", type=Path, required=True)
    read.add_argument("--frames", type=int, default=8)
    read.add_argument("--engineering-inputs", type=Path)
    infer = commands.add_parser("analyze", help="Make live vision and NVIDIA compiler calls through Nebius")
    infer.add_argument("--run", type=Path, required=True)
    infer.add_argument("--vision-model", required=True)
    infer.add_argument("--compiler-model", required=True)
    infer.add_argument("--annotation-grounding", action="store_true", help="Supply first-frame object annotation hints; never procedure ground truth")
    args = parser.parse_args()
    try:
        if args.command == "ingest":
            ingest(args.video, args.annotation, args.output, args.frames, args.engineering_inputs)
        else:
            analyze(args.run, args.vision_model, args.compiler_model, args.annotation_grounding)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Pipeline failed: {error}\n")


if __name__ == "__main__":
    main()
