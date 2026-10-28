# Next milestone: a defensible intervention decision

## Dataset-first update

The user selected public recorded data rather than collecting a new hardware
batch. [IndustReal retrieval](industreal-small-sample.md) remains blocked, so the
active baseline now uses [ten HA4M trials from the official CNR host](ha4m-small-sample.md).
Complete action-label timelines align with 42,378 RGB index entries; offline
analysis establishes recorded action-duration allocations, while accepted-output
quality, full-process labor and intervention benefits remain unknown. The coil
intake below remains an implemented reusable capability, rather than a request
for user measurements.

## Checkpoint after PR #56

The BridgeData path demonstrates live observation/protocol/proposal/CAD generation,
live visual correction and an offline lab continuation. That is integration and
visual-quality evidence, not resource-efficiency improvement. It remains separate
from the user-directed stacking animation and the earlier coil planning examples.

The evaluation foundation already exists:

| Existing component | What it does | Evidence boundary |
| --- | --- | --- |
| `evaluation.py` | Batch resources and cost per accepted output; operator-interval unions | Needs complete inputs; missing values stay unknown |
| `investment.py` | Capacity, capital, recurring costs, payback and sensitivities | Acceptance/equivalence and capacity gates remain mandatory |
| `alternatives.py` | Manual fixture vs motorized winder vs CW-02 | Current real-evidence decisions are all undetermined |
| `iteration.py` | Hashed prediction → outcome → revision records | Illustrative/simulation outcomes are not physical measurements |
| `benchmarks/coil-winding/baseline.json` | Fifteen full-workflow steps and evidence gaps | Defined, not measured; source-video review and acceptance criteria unresolved |

Do not rebuild these systems. The missing connection is complete, sourced batch
evidence entering those evaluators. `workflow_measurements.py` and
`scripts/evaluate_workflow_batch.py` now provide that connection, preserving the
existing contracts and decision gates.

## Selected experiment

Continue the coil-winding case named in epic #17, using the existing manual,
motorized and coordinated CW-02 alternatives. Do not infer manual labor from the
robotic BridgeData demonstration or substitute its toy-transfer CAD for coil CAD.
CREOLab publication permissions remain a separate unresolved matter; this offline
work uses repository planning data and publishes no new footage.

**Objective:** choose an intervention that meets the same accepted-output and
production constraints with a defensible resource tradeoff. Keeping the manual
baseline or collecting more evidence are valid decisions.

**Functional unit:** one accepted released coil meeting verified material,
dimensional, damage/contamination and downstream-function requirements. Target
values and tolerances are currently unknown, not invented defaults.

**Boundary:** stock verification and station preparation → preparation/winding →
inspection/rework → storage, scrap accounting and station reset. Capture operator
attendance, setup/trials, exceptions, cleanup and maintenance applicability. Keep
initial deployment and annual fixed costs in the existing investment categories;
do not double-count them as batch costs.

**Unknown user inputs:** actual demand, batch size, horizon, budget, available
equipment/space, rates and acceptance specifications. Existing hypothetical
scenarios can exercise sensitivity arithmetic but do not supply these facts.

## Collect one batch without changing history

Generate a separate template for each option:

```powershell
python scripts/evaluate_workflow_batch.py --option manual --template --output runs/coil-manual-collection-001
python scripts/evaluate_workflow_batch.py --option motorized --template --output runs/coil-motorized-collection-001
python scripts/evaluate_workflow_batch.py --option cw02 --template --output runs/coil-cw02-collection-001
```

Templates deliberately clear inherited process numbers to unknown. A template's
`evidence_kind=physical` describes the intended collection mode, not completed
physical evidence; its status is `needs_measurements`. Copy `batch.json` to a new
working file before filling it. Preserve the generated template and every run.

1. Resolve the baseline step applicability and acceptance specification against
   permitted source evidence/SOP/operator input. Version the baseline if the
   workflow changes; hashes prevent silently attaching a batch to an old contract.
2. Record complete batch start/end and attempted/accepted counts. Annotation
   timestamps, render timelines and model-generated cycle estimates are not batch
   measurements. Count trials/rejects consistently with the declared boundary.
3. For each baseline step, use `observed`, `not_applicable` with a sourced reason,
   or `unobserved`. Never omit a step to make accounting appear complete.
4. Observed steps have `occurrences`: each has `start_s`, `end_s`, `evidence_refs`
   and `attendance`. Attendance records use `operator_id`, `start_s`, `end_s`,
   `basis` and `source` as in the existing evaluator. All times share the batch
   origin. Record separate intervals when an operator leaves a running machine.
5. Reconcile per-attempt/per-accepted occurrences against the supplied counts.
   A per-batch occurrence covers that batch activity, including internal repetitions;
   conditional rework/maintenance occurrences require explicit evidence, even when
   none occurred. Do not duplicate trial/rework time in other steps.
6. Set `attendance_complete` only when all operators and the whole batch have been
   accounted for, with `attendance_source`. Overlapping intervals for one operator
   are unioned; different operators add labor. Step durations are never summed into
   batch elapsed time. Unsupported frequencies or missing coverage keep labor unknown.
7. Add actual material/energy/cost inputs with sources where available. Unknown is
   not zero. Physical/simulation measurements reject assumed physical quantities;
   use `illustrative` for hypothetical arithmetic. Simulation must cite the actual
   simulator/run, not relabeled guessed numbers. References are supplied assertions,
   not independently authenticated by this tool.

Audit the completed copy and feed its process data to the existing comparison:

```powershell
python scripts/evaluate_workflow_batch.py --option manual --input runs/manual-batch-filled.json --output runs/manual-batch-audit-001
```

Outputs include the original collection record, baseline, input alternatives,
coverage blockers, evaluator output, comparison/report and a hashed manifest.
`updated-alternatives.json` is a detached comparison input with that batch applied.
Use it with `--alternatives` on the next option's audit to accumulate evidence;
original inputs remain untouched. Configuration ID, boundary and functional unit
must match. Nonphysical or incomplete-coverage audits cannot inherit physical
equivalence claims. `coverage_reconciled` is only an accounting check, not proof of
accepted outputs, safe machinery, sufficient samples or an investment recommendation.

## Offline results of this pass

- All three real-evidence collection templates identify **17 blockers**: elapsed
  batch time, 15 workflow steps and complete operator attendance. Comparisons stay
  **undetermined**; total labor and full cost are not replaced with partial zeros.
- Re-executed the five existing illustrative sensitivity scenarios. At 1,000
  coils/year, hypothetical motorized-versus-manual three-year saving is about
  **$40.66**, while CW-02-versus-manual is **−$371.27**. At 10,000, the latter is
  **+$5,310.66**. With labor priced at zero it becomes **−$1,005.13**. These are
  conditional arithmetic from existing invented inputs, not new performance evidence.
- The 30,000/year comparisons involving the manual option remain capacity-blocked.
  All scenarios retain `decision=undetermined` because acceptance/equivalence are
  unverified. A numerical sensitivity reversal is not decision proof.
- Full offline suite: **244 passed, 4 skipped, 12 subtests passed**. New checks cover
  overlapping operators, missing occurrences/coverage, hash/boundary mismatches,
  invalid timelines, assumptions posing as measurements, offline CLI execution and
  overwrite protection. No paid inference, new footage or hardware measurements.

## Delivery gates and next smallest action

| Gate from #17 | Current state | Next evidence |
| --- | --- | --- |
| G1: defensible baseline | Defined; collection intake implemented; not measured | Resolve acceptance specs and collect a complete manual batch |
| G2: comparable alternatives | Evaluators implemented; hypothetical scenarios exercised | Equivalent-output evidence and full-process batches for the alternatives |
| G3: decision-driven revision | Visual revision demonstrated separately; resource-driven revision not demonstrated | Independent evaluation identifies a constraint/tradeoff and drives a bounded change |
| G4: outcome feedback | Versioned loop implemented and tested offline | Freeze prediction, import actual or explicitly simulated outcome, evaluate deviation |

Start with the accepted-output specification and one complete manual batch, before
spending more on machine generation. Actual operating evidence is an external
dependency: no additional prompt or CAD detail can manufacture it. A separately
labeled simulation experiment is possible once its timing/resource model is defined.
