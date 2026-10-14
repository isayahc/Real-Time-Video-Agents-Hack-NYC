# Fixed coil protocol → apparatus requirements → resource report

Run from the repository root:

```bash
python -m protocol_pipeline coil-offline --output runs/coil-offline-001
```

This Python-only command needs the normal Pydantic dependency, with no Nebius key, GPU, Forma runtime or OpenIndustries checkout. It loads the existing CW-02 planning protocol and preparation document, and carries five finishing/maintenance candidates from the manual workflow for review. It does not extract instructions from video.

The executed [report](report.md) and [summary](summary.json) are included here. The source protocol remains a proposed implementation of the T1 wire-winding task; actual video review and output acceptance remain unresolved.

## What connects

- 19 operation nodes: nine preparation candidates, five machine protocol operations and five finishing/maintenance candidates.
- One candidate capability per operation, with source field references and suggested equipment. The generated `apparatus-requirements.json` conforms to the existing design handoff contract and can be supplied to `build --requirements ...` when a design runtime is available.
- Proposed process links distinguish tension maintenance **during** winding from operations ordered **before** others. The graph is incomplete and requires review; it is not an executable schedule.
- A full-process input template goes through the existing resource evaluator with unknown values preserved.
- Existing winding-only assumptions are evaluated separately in the structured summary and report. They never populate full-process totals, rates or yield.
- A field-by-field measurement checklist connects physical quantities to operation IDs and explains counts, overlapping attendance, elapsed time and scrap accounting.

Preparation ranges are unmeasured attended-time hypotheses. Threading, clamping, cutting and inspection may overlap existing allowances, so no aggregate preparation/winding total is invented. Candidate equipment is not a verified BOM. Trial coils may repeat core operations; their frequency, scrap and accounting treatment must be reviewed.

## Fill measurements later

The run writes `full-process-input.json` with the consistent full-batch boundary. Set supported values with their units, a basis such as `measured`, and an evidence source. Keep unavailable values null with basis `unknown`. Accepted counts require an actual acceptance method; declare `acceptance_verified` only with a supporting `acceptance_source`.

Then use the existing evaluator:

```bash
python -m protocol_pipeline evaluate \
  --input runs/coil-offline-001/full-process-input.json \
  --output runs/coil-offline-001/measured-resource-report.json
```

This evaluates supplied batch values. It does not automatically aggregate task durations or infer measurements from the graph. Use a new output path; the commands preserve prior evidence.

## Verification

All 64 Python tests passed, including five new tests for boundary separation, operation/source/capability mapping, concurrent tension maintenance, network-blocked execution, output preservation and invalid graph/protocol rejection. See [checks](checks.json).
