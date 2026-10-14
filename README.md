# Human Procedure → Machine Procedure

Evidence-grounded CREOLab video ingestion and Nebius-assisted protocol/apparatus planning. Existing designs and estimates remain in [snapshots/v1](snapshots/v1/) and [snapshots/v2](snapshots/v2/); the [Nebius epic](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/16) tracks the broader product.

## What the implemented pipeline does

1. Copies the original annotation bytes unchanged and normalizes CREOLab's `video_id`, objects, normalized first-frame positions, `caption`, and alternative `reference_procedure` string/list.
2. Uses ffprobe decoded-frame presentation timestamps and ffmpeg sampling to retain real frame indices, timestamps and SHA-256 hashes.
3. Sends sampled pixels/timestamps to a selected Nebius vision model. Procedure ground truth is never included. Optional object hints are explicitly annotated first-frame positions, not tracks.
4. Validates the returned object/action/state graph against the sampled frames and timeline.
5. Calls an explicitly selected NVIDIA model through Nebius Token Factory to derive embodiment-independent operations and capabilities. Capabilities reference operations; operations reference source actions; actions reference video frames.
6. Stores possible off-camera preparation separately as unverified candidates. Numerical parameters, costs, labor, power and byproducts require separate sourced engineering inputs; unknowns stay null.
7. Exports a generic apparatus requirements request. The current Forma generation API binding, geometry generation, plant simulation and automatic accounting adapters are subsequent integrations. The local process evaluator accepts separately supplied resource/cost inputs.

This is sampled-frame visual reasoning, not continuous YOLO tracking, measured motion/force, physical validation or proof of experiment success. Merely naming a tool does not establish its function. No default model IDs are assumed to be available for your account. Live Nebius inference has not been verified in this checkout; tests exercise deterministic contracts and local ffmpeg ingestion.

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
| `apparatus-request.json` | Generic requirements handoff; not yet sent to Forma. |
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

The [deterministic evaluator](examples/process-evaluation/) calculates recurring cost, labor, energy and material/waste quantities per accepted output from sourced batch inputs. Unknown inputs remain null; operator attendance overlaps are merged; reports preserve inputs and assumptions. Investment comparison is implemented separately below; the feedback controller remains pending.

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
