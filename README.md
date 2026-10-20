# Human Procedure → Machine Procedure

Evidence-grounded CREOLab video ingestion and Nebius-assisted protocol/apparatus planning. Existing designs and estimates remain in [snapshots/v1](snapshots/v1/) and [snapshots/v2](snapshots/v2/); the [Nebius epic](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/16) tracks the broader product.

## What the implemented pipeline does

1. Copies the original annotation bytes unchanged and normalizes CREOLab's `video_id`, objects, normalized first-frame positions, `caption`, and alternative `reference_procedure` string/list.
2. Uses ffprobe decoded-frame presentation timestamps and ffmpeg sampling to retain real frame indices, timestamps and SHA-256 hashes.
3. Sends sampled pixels/timestamps to a selected Nebius vision model. Procedure ground truth is never included. Optional object hints are explicitly annotated first-frame positions, not tracks.
4. Validates the returned object/action/state graph against the sampled frames and timeline.
5. Calls an explicitly selected NVIDIA model through Nebius Token Factory to derive embodiment-independent operations and capabilities. Capabilities reference operations; operations reference source actions; actions reference video frames.
6. Stores possible off-camera preparation separately as unverified candidates. Numerical parameters, costs, labor, power and byproducts require separate sourced engineering inputs; unknowns stay null.
7. Exports typed apparatus requirements consumed by the Forma/OpenIndustries build command. Plant simulation and automatic cost/resource adapters remain subsequent integrations; the local evaluator accepts separately supplied resource/cost inputs.

This is sampled-frame visual reasoning, not continuous YOLO tracking, measured motion/force, physical validation or proof of experiment success. Merely naming a tool does not establish its function. No default model IDs are assumed to be available for your account. Live Nebius text extraction has passed a smoke test; live video inference remains unverified. Tests exercise deterministic contracts and local ffmpeg ingestion.

## Install and ingest

Requires Python 3.11+, ffmpeg and ffprobe. On WSL2/Ubuntu, `sudo apt install ffmpeg` supplies both binaries.

```bash
python -m pip install -e .
python -m protocol_pipeline ingest \
  --video /path/to/data/videos/scenario01_decoy0.mp4 \
  --annotation /path/to/data/captions/scenario01_decoy0.json \
  --output runs/t1-001 --frames 8
```

Ingestion is local and makes no model calls. It refuses an existing output directory and mismatched video/annotation take filenames. No CREOLab data is bundled; obtain authorized data from the [upstream dataset](https://github.com/ToyotaCRDL/CREOLab). Its source license limits dataset/code use to noncommercial research; confirm applicable permission before uploading or redistributing source assets.

## Live analysis

Set `NEBIUS_API_KEY` (or `NEBIUS_TOKEN_FACTORY_KEY`) through your environment. Choose canonical vision and NVIDIA open-source compiler model IDs available in your Token Factory catalog. The API URL is `https://api.tokenfactory.nebius.com/v1/chat/completions`.

```bash
python -m protocol_pipeline analyze \
  --run runs/t1-001 \
  --vision-model '<available-vision-model-id>' \
  --compiler-model 'nvidia/<available-open-source-model-id>'
```

Add `--annotation-grounding` deliberately to supply source object labels/first-frame positions. This is an assisted-annotation evaluation mode; compare it separately from the default video-only mode. Both exclude procedure ground truth. API/model requests incur provider usage. Transient HTTP retries are bounded to three attempts; a retry may incur additional usage. Authentication headers are never written to traces. Inference refuses existing successful/partial observation outputs; ingest another run for another attempt.

Outputs are JSON-validated without repairing malformed responses. Empty observations are allowed when evidence is insufficient. Temporal intervals are inferred from sparse images; valid references are necessary, but not sufficient, to establish semantic accuracy.

## Output separation

| Artifact | Meaning |
| --- | --- |
| `ground-truth.original.json` | Exact source bytes, including unknown upstream fields. |
| `ground-truth.normalized.json` | Normalized source procedure/objects for later evaluation. |
| `annotation-object-catalog.json` | Optional first-frame object hints; no procedure text. |
| `frames/`, `manifest.json` | Actual sampled pixels, source PTS/frame indices and hashes. |
| `observations.json` | Model-inferred objects, actions and changes with evidence/confidence. |
| `protocol-plan.json` | Derived operations, apparatus capabilities, preprocessing hypotheses and unknowns. |
| `engineering-inputs.json` | Separately supplied specifications, assumptions and measurements. |
| `apparatus-request.json` | Typed requirements handoff; submit through the build command. |
| `*-provider-trace.json` | Requested/served model, response, token usage and latency. |

## Engineering inputs

Pass a JSON file to ingestion with `--engineering-inputs`. Each category (`parameters`, `costs`, `labor`, `power`, `byproducts`) is a dictionary of explicit values:

```json
{
  "parameters": {
    "wire_diameter": {"value": null, "unit": "mm", "basis": "unknown"}
  },
  "power": {
    "active_input": {"value": 30, "unit": "W", "basis": "assumed", "source": "Illustrative v2 scenario; not measured"}
  }
}
```

Unknown values cannot be numeric zero; non-unknown values require a source description. The pipeline does not turn inferred video descriptions into numerical engineering data. Preprocessing candidates do not receive invented durations or become confirmed annotations.

## Checks

```bash
python -m unittest discover -s tests -v
```

Tests check broken frame/operation references, temporal inconsistency, numerical provenance, annotation alternatives/raw-byte preservation, actual ffmpeg source timestamps, and exclusion of ground truth from both request modes. They do not claim live provider success or scientific validity.

Keep downloaded data, runtime frames, annotations and provider outputs outside Git; `.gitignore` excludes `data/` and `runs/`. The chosen T1 scenario already guided our design and is not an untouched held-out benchmark. Select a distinct procedure for held-out evaluation.

## Full manual baseline

The [coil-winding benchmark](benchmarks/coil-winding/) defines the full manual workflow, human labor/resource boundary, acceptance gates and an event-level measurement template for [epic #17](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/17). Its metrics remain unknown until a reviewed full run is recorded; existing snapshot estimates are not measured baseline values.

## Process evaluation

The [deterministic evaluator](examples/process-evaluation/) calculates recurring cost, labor, energy and material/waste quantities per accepted output from sourced batch inputs. Unknown inputs remain null; operator attendance overlaps are merged; reports preserve inputs and assumptions. Investment comparison is implemented separately below; the iteration controller is implemented below.

```bash
python -m protocol_pipeline evaluate \
  --input examples/process-evaluation/coil-v2-partial.json \
  --output /tmp/coil-process-report.json
```

## Infrastructure investment comparison

The [investment comparator](examples/investment-comparison/) evaluates manual versus apparatus operating costs, upfront deployment, annual capacity, simple payback and horizon break-even demand, including sourced sensitivity cases. Output equivalence, missing inputs, insufficient capacity and unmodeled replacements block a cost decision.

```bash
python -m protocol_pipeline compare \
  --input examples/investment-comparison/synthetic-comparison.json \
  --output /tmp/investment-report.json
```

## Versioned iteration loop

The [iteration controller](examples/iteration-loop/) records predictions, attaches evidence-labeled outcomes, flags deviations and reevaluates explicit revision proposals through process and investment accounting. Records are append-only with hashed lineage; illustrative runs remain distinguished from physical/simulation evidence. The build command links Forma/OpenIndustries artifacts to a prediction/revision and carries proposed changes into synthesis; physical data collection remains separate.

## Apparatus and scene build

The [design adapter](examples/design-handoff/) calls Forma Core and OpenIndustries native import/export plus local MCP room tools, with explicit live/simulation/replay modes. It records validation, source-prediction lineage and artifact hashes. Local simulation and CW-02 replay integration were verified; live generation still needs provider configuration.

## Single-command demo

The [demo runner and executed sample report](examples/demo/) run the illustrative feedback loop and replay CW-02 into a native scene, producing HTML, Markdown and structured results with explicit evidence labels.

```bash
python -m protocol_pipeline demo \
  --output runs/demo-001 \
  --forma-root /path/to/forma-oss --oi-root /path/to/open-industries
```

Use `--accounting-only` to explicitly skip optional scene runtimes. Both modes preserve unknown coil economics and existing records.

## Offline coil protocol workflow

Run the fixed CW-02 protocol through candidate apparatus requirements and resource accounting without credits:

```bash
python -m protocol_pipeline coil-offline --output runs/coil-offline-001
```

See the [executed report and measurement workflow](examples/coil-offline/README.md). Full-process measurements remain unknown; winding-only estimates are reported separately.

## Apparatus alternatives

Compare manual, simple motorized and CW-02 candidate architectures without model calls:

```bash
python -m protocol_pipeline compare-alternatives \
  --input examples/apparatus-alternatives/illustrative-input.json \
  --output runs/apparatus-illustrative-001
```

The [comparison](examples/apparatus-alternatives/README.md) includes a separate current-evidence report with unknown full-process values and explicitly hypothetical volume/labor scenarios. It exposes tradeoffs without declaring verified savings or a procurement recommendation.

## Offline verification and failure replay

```bash
python -m protocol_pipeline failure-replay --output runs/failure-replay-001
python -m scripts.verify_offline --output runs/ci-offline-001
```

The [failure scenarios](examples/failure-replay/README.md) distinguish explicitly skipped steps from missing evidence and exercise delays/rejects through the resource evaluator. GitHub Actions runs tests and all offline workflows on Python 3.11/3.12 and retains the reports as artifacts. Application stages require no provider credits or keys.

## Reusable protocol input

```bash
python -m protocol_pipeline compile-protocol \
  --input examples/protocols/tube-transfer.json --output runs/compiled-transfer-001
```

The [shared protocol format](examples/protocols/README.md) compiles both coil winding and conceptual empty-tube transfer into the same apparatus and resource contracts. Inputs explicitly supply operations, dependencies, candidate equipment, preparation and acceptance checks; no task-specific inference or physical measurements are invented.

## Automatic extraction providers

```bash
python -m protocol_pipeline extract-protocol \
  --text /path/to/procedure.txt --provider nebius \
  --model YOUR_TEXT_MODEL_ID --output runs/text-extraction-001
```

[Extraction](examples/extraction/README.md) supports text and sampled-video input, explicit Nebius model selection, source-grounding checks, and direct compiler handoff. A separate recorded-response replay exercises the integration without credits. A live Nebius text-to-compiled-plan smoke test passed on 2026-10-19; extraction accuracy, live video inference and physical validation remain unverified.

## Extraction accuracy review

The [benchmark workflow](examples/extraction-benchmark/README.md) scores step coverage, ordering, reviewer-assessed grounding, preparation/evidence classification and acceptance checks against a source-bound reference. No review means pending scores. The initial authored text fixture verifies scoring behavior; it does not establish live Nebius quality.

