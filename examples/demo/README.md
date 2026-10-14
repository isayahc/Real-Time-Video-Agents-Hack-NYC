# Single-command resource-efficiency demo

Runs the implemented prediction → illustrative outcome → deviation → revision → reevaluation loop, then replays the existing CW-02 concept through native Forma validation and OpenIndustries scene import. Writes a self-contained HTML report, Markdown report and machine-readable summary.

Read the executed [sample report](sample-report.md) or [structured summary](sample-summary.json) directly in the repo. The sample excludes runtime record/scene files; the command below creates the complete linked artifact directory.

## Full demo

From the repo root, with the Forma runtime and OpenIndustries checkout dependencies installed:

```bash
python -m protocol_pipeline demo \
  --output runs/demo-001 \
  --forma-root /path/to/forma-oss \
  --oi-root /path/to/open-industries
```

The default coil artifact is `snapshots/v2/coil-winder.forma.json`. Override with `--coil-project /path/to/coil-winder.forma.json` when needed. An installed compatible Forma package can replace `--forma-root`. No generation-provider key is needed because the scene stage explicitly replays the existing concept; it makes no live model calls or cloud writes. OpenIndustries creates/reads a local planning room through its actual stdio MCP server.

The default example directory is `examples/`; use `--examples-root` when running outside the repo. The demo expects the bundled illustrative fixtures and unresolved coil prediction, not production observations.

## Accounting-only demo

Without the optional Forma/Node/OpenIndustries runtimes:

```bash
python -m protocol_pipeline demo \
  --output runs/demo-accounting-001 --accounting-only
```

This explicitly skips scene/MCP work and labels it as skipped in the report. The full demo never silently falls back to this mode.

## Outputs

| Path | Contents |
| --- | --- |
| `report.html` | Self-contained responsive report with resource/investment tables, coil status and expandable evidence details |
| `report.md` | Readable report with record and scene links |
| `demo-summary.json` | Metrics, investment results, source fixture hashes, lineage digests and scene evidence |
| `records/p1.json`, `o1.json`, `p2.json` | Preserved illustrative prediction, outcome and revision |
| `records/coil-p1.json` | Coil concept prediction with unknown operating inputs |
| `coil-design/` | Native Forma/OI artifacts, validation, MCP room provenance and artifact hashes in full mode |
| `demo-failure.json` | Failed-stage marker if execution stops; completed evidence remains available |

Open `report.html` in a browser or read `report.md`. Import `coil-design/apparatus.oi.json` into the OpenIndustries workbench. Reports use values returned by the evaluators rather than separate UI calculations. Zero, unknown and undefined values are displayed distinctly. The HTML escapes source-derived labels and loads no external assets or scripts.

Every output path must be new. Reusing a directory fails without overwriting evidence. Runtime outputs are excluded from Git by the existing `runs/` rule.

## What the demonstration establishes

The accounting fixture's fabricated outcomes and proposed changes exercise both evaluators and the iteration controller. Its revision reduces predicted cost/labor while increasing electricity, so the report identifies a tradeoff.

The coil concept is a separate evidence lane: the replay preserves 12 BOM lines and 33 schematic mesh parts through the real native import/portable roundtrip. The apparatus is schema-valid but has deterministic validation findings. Its operating costs, full-process performance and equivalent accepted output remain unresolved.

The illustrative economics are not assigned to CW-02. This is a software integration demonstration, not a live inference run, physical experiment or demonstrated economic improvement. The HTML and Markdown preserve that distinction prominently.

## Verification

59 Python tests pass. The full CLI command was executed against the actual local Forma/OI runtimes; the HTML was rendered and checked. `checks.json` records these checks. Tests cover actual accounting orchestration, unchanged prior outputs, explicit skipped mode, stage failure, HTML escaping and zero/unknown/undefined formatting, in addition to the existing contracts and evaluators.
