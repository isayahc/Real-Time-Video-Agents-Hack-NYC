# Predict → observe → compare → revise → reevaluate

The iteration controller connects process resource accounting and investment comparison for [epic #17](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/17). It accepts supplied runs and explicit revision proposals. Data collection, causal diagnosis and Forma/OpenIndustries generation remain separate integrations.

## Run the illustrative loop

From the repository root, use a new store directory:

```bash
python -m protocol_pipeline predict \
  --store runs/iteration-demo --id p1 \
  --input examples/iteration-loop/prediction.json

python -m protocol_pipeline observe \
  --store runs/iteration-demo --id o1 --prediction p1 \
  --input examples/iteration-loop/outcome.json

python -m protocol_pipeline revise \
  --store runs/iteration-demo --id p2 --parent p1 --outcome o1 \
  --input examples/iteration-loop/revision.json
```

Each command prints the record ID, hash and path. This demonstration uses **fabricated illustrative arithmetic data**. It contains no physical test, simulation run or observed coil performance. The synthetic acceptance/equivalence flags belong to its test fixture. The revision demonstrates a predicted labor/throughput benefit with an electricity tradeoff.

For the actual coil's unresolved full-process prediction, use `coil-prediction-unknown.json` in the `predict` command. Unknown quantities remain unknown through both evaluators. An actual coil outcome must be supplied later.

## Records and lineage

| Record | Stored contents |
| --- | --- |
| Root prediction | Version 1, complete input request, process report, optional investment report, conditions and tolerances |
| Outcome | Reference to the exact prediction digest, run inputs, evidence kind/references, process/investment reevaluation and deviations |
| Revision | Parent prediction and responding outcome digests, parent version + 1, explicit rationale/changes, reevaluated reports and predicted tradeoffs |

IDs allow letters, digits, underscores and hyphens, up to 80 characters. Duplicate IDs are rejected. Writes are staged and linked atomically without overwriting existing files. Each envelope carries a SHA-256 digest of canonical record content. Loading verifies that digest and every linked ancestor; edited ancestors invalidate descendants. These checks detect content changes, but are not a digital signature or proof of evidence authenticity.

Versions follow their parent branch, allowing multiple alternative revisions from one prediction. An outcome can attach only to a prediction of the same configuration, functional unit and boundary. A revision can change configuration ID, while preserving functional unit and boundary. It must respond to an outcome of its exact parent. A parent's investment comparison cannot be silently dropped.

The store belongs under `runs/`, which is excluded from Git by default. Evidence references are supplied identifiers/paths; the controller does not open, upload or independently verify their contents. Keep source videos and private/operator data outside committed benchmark examples.

## Requests and Python API

`PredictionRequest` contains:

- `process`: the typed process evaluator input.
- Optional `investment`: typed infrastructure comparison, whose candidate process must match `process` exactly.
- `conditions`: description of workload/operating assumptions.
- Optional per-metric `tolerances`: absolute threshold in that metric's units and relative threshold as a fraction.

`OutcomeRequest` contains process inputs, `conditions`, nonempty `evidence_refs`, and an `evidence_kind` of `physical`, `simulation` or `illustrative`. Physical and simulation records reject assumed numerical inputs. Their known physical quantities must use measured provenance; prices can use measured or supplier provenance. Unmeasured fields remain null. Illustrative records permit assumptions and are explicitly labeled. The software checks these declarations, not the underlying experiment.

`RevisionRequest` contains a new `PredictionRequest`, a rationale and a nonempty list of proposed changes. A revision remains a hypothesis until a new run is attached.

Python functions `predict(store, id, request)`, `observe(store, id, prediction_id, request)`, `revise(store, id, parent_id, outcome_id, request)` and `load_record(store, id)` are in `protocol_pipeline.iteration`. Request and stored-record JSON schemas are exported under `schemas/iteration-*.json`.

## Deviations and tradeoffs

Tracked objectives are cost, attended labor, electricity, consumed stock and unrecovered waste per accepted output (lower preferred), plus accepted outputs/hour (higher preferred).

The report identifies the reference and compared roles. Each metric records `reference_value`, `compared_value`, unit, **signed** `absolute_delta` in metric units, relative delta, preferred direction and an outside-tolerance flag. Signed delta is compared value minus reference value. Relative delta uses the absolute reference magnitude; it is undefined when reference is zero.

Outside tolerance means:

`abs(delta) > max(absolute tolerance, relative tolerance × abs(reference))`

Default tolerance is 10% relative and zero absolute. At a zero prediction, only absolute tolerance applies. A deviation outside tolerance can be favorable or unfavorable; it is not automatically a failure. Unknown or undefined metrics cannot produce deviation percentages or improvement claims.

Run-condition and batch-size/count differences are flagged. Comparisons are normalized per accepted output, but different batch sizes can still change setup allocation and yield. Unverified acceptance and assumed inputs remain visible. There is no automatic causal explanation or weighted objective score.

Revisions are assessed against both the original prediction and the recorded outcome. The summary identifies predicted improvements, regressions and tradeoffs; wholly unknown comparisons return `insufficient_evidence`. Partial tradeoff assessments carry warnings. A predicted improvement does not establish actual quality equivalence or deployed performance.

## Investment feedback

When a prediction includes an investment comparison, an outcome reruns it with the observed process replacing the candidate's process input. Baseline, demand, upfront/fixed costs, useful life and capacity factors retain their prediction values; that limitation is recorded explicitly. Updating these assumptions requires an explicit revision request.

The variable/fixed cost contract of the investment comparator still applies: fixed/capital allocations must stay separate from variable batch cost. Every new revision reruns both evaluators, including sensitivity cases. Investment gates can remain unresolved even if some physical deviations are calculable.

## Verification

```bash
python -m unittest discover -s tests -v
```

Tests cover complete loop execution and investment updates, preserved prior bytes, duplicate/unsafe IDs, altered record/ancestor digests, wrong configuration/parent, mislabeled assumed observations, partial data, zero-reference tolerances, mandatory economics retention and unknown revision results. The CLI example checks predict/observe/revise end to end with illustrative data.
