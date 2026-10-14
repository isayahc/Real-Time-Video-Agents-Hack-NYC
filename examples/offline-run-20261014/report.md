# Resource-efficiency loop demo

**Evidence: illustrative arithmetic plus an existing coil concept. No physical experiment, live model inference or demonstrated coil savings.**

## Illustrative accounting loop

The financial fixture exercises predict → attach outcome → compare → revise → reevaluate. Its numbers are fabricated examples and do not describe CW-02.

| Metric | Prediction v1 | Illustrative outcome | Revision v2 prediction |
| --- | ---: | ---: | ---: |
| Cost per accepted output (USD) | 2 | 2.05 | 1.976 |
| Attended labor per accepted output (operator-s) | 9 | 18 | 4.5 |
| Electricity per accepted output (Wh) | 0 | 0 | 5 |
| Consumed stock per accepted output (g) | 0 | 0 | 0 |
| Unrecovered waste per accepted output (g) | 0 | 0 | 0 |
| Accepted outputs per hour | 100 | 80 | 100 |

Revision assessment: **predicted tradeoff**.

Flagged deviations: cost_usd_per_accepted, labor_s_per_accepted, accepted_outputs_per_hour.

Predicted improvements versus illustrative outcome: cost_usd_per_accepted, labor_s_per_accepted, accepted_outputs_per_hour.

Predicted regressions versus illustrative outcome: electricity_wh_per_accepted.

The revised result remains a prediction. Lower labor and cost can coexist with higher electricity use.

### Illustrative investment results

| Metric | Prediction v1 | Illustrative outcome update | Revision v2 |
| --- | ---: | ---: | ---: |
| Annual operating saving (USD/year) | 28,000 | 27,500 | 28,240 |
| Simple payback (years) | 0.3571 | 0.3636 | 0.3541 |
| Undiscounted horizon saving (USD) | 130,000 | 127,500 | 131,200 |

These figures are conditional synthetic calculations. The outcome update retains the prediction’s fixed costs, demand, baseline and capacity factors.

## CW-02 coil concept and scene

**This is a separate evidence lane. The illustrative cost/savings figures above are not assigned to the coil apparatus.**

Actual coil investment decision: **undetermined**.

Actual coil unit cost: **Unknown**. Output equivalence and full-process measurements remain unresolved.

Scene handoff: **explicitly skipped in accounting-only mode**. No scene import/MCP execution is claimed.

## Record lineage and artifacts

| Record | Meaning | SHA-256 |
| --- | --- | --- |
| [p1](records/p1.json) | Illustrative prediction v1 | `8bdc8309580ddb58c18fcc6f33ad23ef98244267795f4c107144ffe10eba1822` |
| [o1](records/o1.json) | Fabricated illustrative outcome | `17221df12d69f1669a00a6700c41b791f737e5b58593edea131f58ca09199306` |
| [p2](records/p2.json) | Illustrative revision v2 | `5a7ccb451cf8303e657fb30dfdfa8ee58af89fb7afa8cbb938c46e358a26f3bd` |
| [coil-p1](records/coil-p1.json) | Actual coil concept: unknown operating inputs | `48c65f6107ae806189f92ba4e2aeb9ec008f4b47171bf294b36a19894c4119ed` |

[Machine-readable summary](demo-summary.json)

## Remaining evidence

- Review the actual video and source protocol, including off-camera preparation.
- Verify released-coil acceptance criteria and downstream functional equivalence.
- Measure the full manual/apparatus workflow: labor, elapsed time, energy, input material and waste.
- Source deployment, maintenance, facility and labor prices and verify production demand/capacity.
- Configure a live generation provider for actual synthesis; record another measured run to test revisions.

No fabricated observation is promoted to physical evidence. Original predictions remain unchanged.
