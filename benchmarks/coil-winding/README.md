# Coil-winding manual baseline

Tracks RE-01/RE-02/RE-03 in [epic #17](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/17). **The baseline is defined but not measured.** The source video and original annotation have not been reviewed in this run. No manual throughput, total unit cost or resource savings are established.

## Comparable output

Use one **accepted released coil** as the functional unit. Resolve actual material, geometry/tolerances, damage/contamination criteria and any downstream performance test from the source protocol before comparing manual winding with CW-02. The v2 dimensions are design assumptions. A visually similar coil is insufficient to establish experimental equivalence.

## Workflow boundary

Start at stock verification and station preparation; end after accepted parts are stored, scrap is accounted for and the station is reset. `baseline.json` defines 15 candidate stages with frequency, tools, applicability checks and unknown measurements:

| Scope | Stages |
| --- | --- |
| Batch preparation | Stock check, fixture preparation, containers/labels, trial coils |
| Each attempt | Measure/cut, prepare ends if needed, load/secure, wind, release/finish, inspect |
| Conditional/product | Rework, label/store accepted output |
| Batch/periodic close | Scrap segregation/recovery, cleanup, maintenance |

The winding task comes from the T1 description. Other stages are hypotheses requiring confirmation. Machine axis homing/calibration does not belong in the manual baseline. Cutting order and end preparation must be verified; record each actual action once.

## Existing estimates

The v1 preparation totals (18–51 minutes per batch; 20–65 seconds per attempt) mix candidate tasks for manual and apparatus workflows. They remain illustrative and must not populate this baseline as observations. The v2 15-second operator touch allowance can overlap cutting, loading and release. Reconcile event boundaries before adding any allowance. Human costs include setup, trial/rework, inspection, cleanup and supervision where attended.

## Record the first full run

1. Obtain the source T1 video/annotation through the existing ingestion workflow; retain hashes and actual timestamps. Review the source against the model observations. Off-camera tasks remain unknown until separately observed or documented.
2. Resolve an acceptance specification and review method. Record whether the source experiment needs a downstream functional test.
3. Copy `measurement-template.json` to a new file under `runs/`. Replace empty fields with evidence-backed data. Keep private operator identities and source assets outside committed benchmark metadata.
4. Observe preparation, all attempts, rejects/rework, product handling and cleanup. Record event start/end, operator attendance, station/resource occupancy and evidence references. A short dataset clip alone cannot establish the full production baseline.
5. Measure input, retained product, scrap/recovery and waste; record electricity and any cleaning utilities. Inventory remaining in process or returned to stock must be explicit.
6. Obtain tool prices/life, loaded labor rate and utility rates with dated sources. Procurement cost and consumed material cost are separate.
7. Review counts, mass balance and labor overlap, then compute metrics. Publish only reviewed aggregate results with provenance.

The template is an empty collection form, not a measured run. Actual observations require the source files and/or a full physical run; none are bundled here.

## Accounting rules

- A reworked coil keeps its attempt ID. Final accepted/rejected/in-process counts partition the attempted count.
- Sum the union of attended intervals for each operator, then sum across operators. Concurrent machine operation can overlap operator work; neither is counted as extra labor. Paid coverage/supervision is a separate allocation.
- Batch elapsed time includes preparation, processing, queues and closeout. Do not estimate it by summing overlapping event durations.
- Distinguish recoverable scrap from unrecovered waste. Recoverable material is not automatically a realized cost credit.
- Unknown values are null. Zero requires evidence; inapplicable stages require an explicit applicability decision.
- Initial machine development/design/build labor stays separate from recurring production labor. Tooling life, maintenance, facility and embodied impacts need explicit allocations for broader cost/lifecycle claims.
- Compare manual and apparatus configurations using the same acceptance specification, batch demand, utilization assumptions and system boundary.

## Metrics after validation

For accepted count A > 0 and run elapsed duration T:

| Metric | Calculation |
| --- | --- |
| Labor seconds per accepted coil | Total operator attendance seconds / A |
| Accepted coils/hour | 3600 × A / T |
| Electricity Wh per accepted coil | Complete boundary electricity Wh / A |
| Input grams per accepted coil | Stock consumed grams / A |
| Unrecovered waste grams per accepted coil | Unrecovered waste grams / A |
| Unit production cost | (Consumed stock + labor + electricity + consumables + allocated tooling + maintenance + facility − realized recovery credit) / A |

Labor cost = attended seconds × loaded USD/hour / 3600, plus explicitly allocated paid coverage. Electricity cost = Wh × USD/kWh / 1000. Do not compute a complete cost or improvement percentage when a required category is unknown. If A = 0, per-accepted metrics are undefined.

Check input mass against accepted products + recoverable scrap + unrecovered waste + returned stock + net inventory change, using a consistently defined input basis. If consumed stock excludes returned stock, do not subtract that stock a second time. Record measurement uncertainty and investigate residuals.

## Ready for comparison when

Acceptance criteria, full workflow applicability, reviewed run measurements and cost sources are complete. Then compare CW-02 and manual winding for resource use per accepted output; report tradeoffs and uncertainty even if manual winding remains preferable.
