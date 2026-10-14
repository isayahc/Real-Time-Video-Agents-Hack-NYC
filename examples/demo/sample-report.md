# Resource-efficiency loop demo — executed sample

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

Mode: **replay** (existing concept replay; no generation call).

Native OpenIndustries scene roundtrip: **True**; 33 mesh parts and 12 retained BOM lines.

Forma schema valid: **True**. Deterministic design validation passed: **False**.

The meshes are schematic concept geometry. Electrical/mechanical completion, requirement coverage, collision/clearance and physical equivalence are unverified.

OpenIndustries MCP created/read a local empty planning room; native import/export populated the portable scene. No cloud scene was published.

The full run writes `coil-design/apparatus.oi.json` and `coil-design/design-manifest.json`. Reproduce them with the command in this directory’s README.

## Record lineage and artifacts

| Record | Meaning | SHA-256 |
| --- | --- | --- |
| p1 | Illustrative prediction v1 | `785a7b38d3b9ed5dde24e12217bbdf9a940c3bf0b26964d5a00107cdbacaf9a2` |
| o1 | Fabricated illustrative outcome | `098b477cb856f109cd1b98f090b2180a934b0e7f9e0a95a32fa5c49b12cc5a6b` |
| p2 | Illustrative revision v2 | `50a76fb4418521d096f9c2d74d9960b50c3918d122d9c7250833f5c1e40ac1dc` |
| coil-p1 | Actual coil concept: unknown operating inputs | `c824893b4c6c4bc3e4b81f4944a4d9985c5ddc432834b312e1eafa9967160447` |

[Machine-readable summary](sample-summary.json)

## Remaining evidence

- Review the actual video and source protocol, including off-camera preparation.
- Verify released-coil acceptance criteria and downstream functional equivalence.
- Measure the full manual/apparatus workflow: labor, elapsed time, energy, input material and waste.
- Source deployment, maintenance, facility and labor prices and verify production demand/capacity.
- Configure a live generation provider for actual synthesis; record another measured run to test revisions.

No fabricated observation is promoted to physical evidence. Original predictions remain unchanged.

This checked-in report preserves a verified demonstration summary. Runtime scene and record files stay in the generated run directory; they are omitted from this sample.
