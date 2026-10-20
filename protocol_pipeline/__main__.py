"""CLI for ingestion and explicitly requested live Nebius analysis."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from .pipeline import analyze, ingest
from .evaluation import evaluate_file
from .investment import compare_file
from .iteration import OutcomeRequest, PredictionRequest, RevisionRequest, observe, predict, revise
from .design import SceneRequest, build_design
from .demo import run_demo
from .offline import run_coil_offline
from .alternatives import run_alternatives
from .failures import run_failures
from .compiler import compile_protocol_file
from .extraction import create_provider, extract_protocol
from .benchmark import benchmark_files


def main() -> None:
    """Parse commands and execute one pipeline stage with clear failure status."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    benchmark = commands.add_parser("benchmark-extraction", help="Score an extraction against a source-bound reference and explicit review")
    benchmark.add_argument("--candidate", type=Path, required=True)
    benchmark.add_argument("--reference", type=Path, required=True)
    benchmark.add_argument("--source", type=Path, required=True)
    benchmark.add_argument("--review", type=Path)
    benchmark.add_argument("--output", type=Path, required=True)
    extraction = commands.add_parser("extract-protocol", help="Extract and compile a candidate protocol using a selected provider")
    sources = extraction.add_mutually_exclusive_group(required=True)
    sources.add_argument("--text", type=Path)
    sources.add_argument("--run", type=Path, help="Existing verified sampled-frame ingestion run")
    extraction.add_argument("--provider", choices=("nebius", "opencode", "replay"), required=True)
    extraction.add_argument("--model", required=True, help="Explicit text/compiler model ID")
    extraction.add_argument("--vision-model", help="Explicit vision model ID for --run")
    extraction.add_argument("--replay", type=Path, help="Recorded responses; only for --provider replay")
    extraction.add_argument("--output", type=Path, required=True)
    compile_command = commands.add_parser("compile-protocol", help="Compile a typed process plan into apparatus requirements and resource reports")
    compile_command.add_argument("--input", type=Path, required=True)
    compile_command.add_argument("--output", type=Path, required=True)
    failures = commands.add_parser("failure-replay", help="Replay illustrative skipped steps, delays, rejects and incomplete observations offline")
    failures.add_argument("--repo-root", type=Path, default=Path("."))
    failures.add_argument("--output", type=Path, required=True)
    alternatives = commands.add_parser("compare-alternatives", help="Compare apparatus concepts using shared boundaries and explicitly supplied assumptions")
    alternatives.add_argument("--input", type=Path, required=True)
    alternatives.add_argument("--output", type=Path, required=True)
    offline = commands.add_parser("coil-offline", help="Map the fixed CW-02 protocol to candidate apparatus and resource reports without model calls")
    offline.add_argument("--repo-root", type=Path, default=Path("."))
    offline.add_argument("--output", type=Path, required=True)
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
    evaluate = commands.add_parser("evaluate", help="Calculate process resources and cost locally; no model calls")
    evaluate.add_argument("--input", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    compare = commands.add_parser("compare", help="Compare process infrastructure cost, capacity and payback locally")
    compare.add_argument("--input", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    demo = commands.add_parser("demo", help="Run the illustrative loop, replay the coil scene and write a readable report")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--examples-root", type=Path, default=Path("examples"))
    demo.add_argument("--forma-root", type=Path)
    demo.add_argument("--oi-root", type=Path)
    demo.add_argument("--coil-project", type=Path, default=Path("snapshots/v2/coil-winder.forma.json"))
    demo.add_argument("--accounting-only", action="store_true", help="Explicitly skip scene/MCP execution")
    build = commands.add_parser("build", help="Generate/validate a Forma apparatus and native local OI scene")
    build.add_argument("--requirements", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--forma-root", type=Path)
    build.add_argument("--oi-root", type=Path, required=True)
    build.add_argument("--mode", choices=("live", "simulation", "replay"), required=True)
    build.add_argument("--brief", required=True)
    build.add_argument("--provider")
    build.add_argument("--model")
    build.add_argument("--project", type=Path)
    build.add_argument("--name", default="Protocol apparatus planning scene")
    build.add_argument("--room", type=float, nargs=3, default=(6, 5, 3), metavar=("WIDTH", "DEPTH", "HEIGHT"))
    build.add_argument("--store", type=Path)
    build.add_argument("--prediction")
    for name, help_text in (("predict", "Save a versioned process/investment prediction"),
                            ("observe", "Attach an evidence-labeled outcome and calculate deviations"),
                            ("revise", "Evaluate a proposed revision responding to an outcome")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--store", type=Path, required=True)
        command.add_argument("--id", required=True)
        command.add_argument("--input", type=Path, required=True)
        if name == "observe":
            command.add_argument("--prediction", required=True)
        if name == "revise":
            command.add_argument("--parent", required=True)
            command.add_argument("--outcome", required=True)
    args = parser.parse_args()
    try:
        if args.command == "benchmark-extraction":
            result = benchmark_files(args.candidate, args.reference, args.source, args.output, args.review)
            print(json.dumps({"status": result["status"], "reference_status": result["reference_status"],
                              "report": str(args.output / "report.md"), "live_model_quality_established": False}))
        elif args.command == "extract-protocol":
            result = extract_protocol(create_provider(args.provider, args.replay), args.model, args.output,
                                      args.text, args.run, args.vision_model)
            print(json.dumps({"status": result["status"], "provider": result["provider"],
                              "live_inference": result["live_inference"], "physical_validation": False,
                              "report": str(args.output / "compiled/report.md")}))
        elif args.command == "compile-protocol":
            result = compile_protocol_file(args.input, args.output)
            print(json.dumps({"protocol_id": result["protocol_id"], "status": result["status"],
                              "report": str(args.output / "report.md"), "physical_validation": False}))
        elif args.command == "failure-replay":
            result = run_failures(args.repo_root, args.output)
            print(json.dumps({"evidence_kind": "illustrative", "cases": len(result["cases"]),
                              "report": str(args.output / "report.md"), "physical_validation": False}))
        elif args.command == "compare-alternatives":
            result = run_alternatives(args.input, args.output)
            print(json.dumps({"evidence_kind": result["evidence_kind"], "recommendation": result["overall_recommendation"],
                              "report": str(args.output / "report.md"), "physical_validation": False}))
        elif args.command == "coil-offline":
            result = run_coil_offline(args.repo_root, args.output)
            print(json.dumps({"status": result["status"], "operations": len(result["workflow"]["nodes"]),
                              "report": str(args.output / "report.md"), "live_inference": False,
                              "physical_validation": False}))
        elif args.command == "ingest":
            ingest(args.video, args.annotation, args.output, args.frames, args.engineering_inputs)
        elif args.command == "analyze":
            analyze(args.run, args.vision_model, args.compiler_model, args.annotation_grounding)
        elif args.command == "evaluate":
            evaluate_file(args.input, args.output)
        elif args.command == "compare":
            compare_file(args.input, args.output)
        elif args.command == "demo":
            result = run_demo(args.output, args.examples_root, args.forma_root, args.oi_root,
                              args.coil_project, args.accounting_only)
            print(json.dumps({"status": result["status"], "report": str(args.output / "report.html"),
                              "markdown": str(args.output / "report.md"), "physical_validation": False}))
        elif args.command == "build":
            result = build_design(args.requirements, args.output, args.forma_root, args.oi_root,
                args.mode, args.brief, SceneRequest(name=args.name, room_m=tuple(args.room)),
                args.provider, args.model, args.project, args.store, args.prediction)
            print(json.dumps({"status": result["status"], "mode": result["mode"],
                              "manifest": str(args.output / "design-manifest.json"),
                              "physical_validation": False}))
        else:
            payload = args.input.read_text()
            if args.command == "predict":
                result = predict(args.store, args.id, PredictionRequest.model_validate_json(payload))
            elif args.command == "observe":
                result = observe(args.store, args.id, args.prediction, OutcomeRequest.model_validate_json(payload))
            else:
                result = revise(args.store, args.id, args.parent, args.outcome, RevisionRequest.model_validate_json(payload))
            print(json.dumps({"id": result.record.id, "kind": result.record.kind,
                              "sha256": result.sha256, "path": str(args.store / (result.record.id + ".json"))}))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Pipeline failed: {error}\n")


if __name__ == "__main__":
    main()

