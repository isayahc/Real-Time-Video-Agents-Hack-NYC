# Compare apparatus alternatives without credits

Compare three proposed coil-winding configurations:

| Option | What is delegated to the apparatus | What remains operator work |
| --- | --- | --- |
| Manual fixture | Forming surface only | Rotation, pitch, tension, cutting, release, inspection |
| Simple motorized winder | Rotation and speed control | Wire guidance/pitch, tension adjustment, stop/turn control, cutting, release, inspection |
| CW-02 coordinated winder | Proposed spindle/traverse coordination and tension/inspection sensing | Loading, setup/calibration, cutting, release, final acceptance |

These are candidate architectures, not a verified hardware specification or demonstrated automation coverage.

For the next evidence step, use the [full-workflow measurement intake](../../docs/decision-proof-roadmap.md).
It connects sourced batch records to these same alternatives, reconciles the 15-step
baseline and avoids double-counting overlapping operator attendance. Incomplete
coverage keeps total labor unknown and cannot establish a winning intervention.

## Current evidence

```bash
python -m protocol_pipeline compare-alternatives \
  --input examples/apparatus-alternatives/evidence-input.json \
  --output runs/apparatus-evidence-001
```

The [evidence report](evidence-report.md) keeps actual full-process quantities unknown. All three pairwise decisions are undetermined. The existing CW-02 equipment midpoint ($877.60) is a concept assumption; installation, integration and training remain unknown. There are no procurement quotes, verified equivalent-output results or measured savings.

## Hypothetical tradeoff exploration

```bash
python -m protocol_pipeline compare-alternatives \
  --input examples/apparatus-alternatives/illustrative-input.json \
  --output runs/apparatus-illustrative-001
```

The [illustrative report](illustrative-report.md) evaluates five shared-demand/rate scenarios with the existing resource and investment evaluators. Each pair uses the same functional unit, full-process boundary, annual demand and horizon. Scenario rate overrides apply to every option. Output acceptance/equivalence remain unverified, so economic arithmetic cannot become an investment recommendation.

**The scenario performance and manual/motorized budgets are invented inputs for exploration, not estimates of actual apparatus performance or market prices.** CW-02 equipment cost reuses the existing conceptual midpoint. Assumed full-batch timings replace neither source review nor physical measurements. Zero deployment costs are explicit scenario assumptions, not evidence of zero implementation effort.

| Shared scenario input | Value / meaning |
| --- | --- |
| Batch | 100 attempts, 95 assumed accepted for all options; no yield benefit assigned to automation |
| Manual / motorized / CW-02 equipment | $100 / $300 / $877.60, before explicitly zero-assumed deployment costs |
| Manual elapsed / attended seconds per batch | 10,000 / 9,000 |
| Motorized elapsed / attended seconds per batch | 8,000 / 7,000 |
| CW-02 elapsed / attended seconds per batch | 6,000 / 5,000 |
| Electricity per batch | 10 / 30 / 50 Wh respectively |
| Base rates | $18/operator-hour and $0.20/kWh; labor sensitivities at $0 and $30 |
| Annual fixed costs | $50 / $75 / $125 respectively |
| Capacity factors | 1,000 scheduled hours/year × 0.8 utilization × (1 − 0.1 additional downtime) |
| Horizon / life | 3 years / assumed 5 years with no replacement |
| Stock, accepted fraction and waste | Held equal across options; no waste or quality improvement claimed |

Conditional findings from these inputs:

- At 1,000 coils/year, the motorized option has the lowest modeled three-year cost, narrowly below manual; CW-02 does not recover its additional cost within the horizon.
- At 10,000 coils/year, CW-02 has the lowest conditional horizon cost because assumed labor savings outweigh its extra capital and annual fixed costs.
- Manual → motorized crosses at about 871 coils/year; manual → CW-02 at 1,588; motorized → CW-02 at 2,305, before capacity/equivalence checks. These thresholds belong only to this scenario.
- With labor priced at zero, manual has the lowest conditional cost. Its attended-time burden remains; unpriced labor is not labor-free production.
- At 30,000 coils/year, the assumed single manual station lacks capacity. The report blocks the pairwise decision rather than silently adding stations or overtime.
- Higher assumed automation reduces attended seconds but raises electricity in this fixture. Shared stock/waste assumptions prevent a claim of material efficiency improvement.

Source inputs are preserved in the JSON fixtures. Reports expose missing evidence and all conditional arithmetic. Edit a copied input to explore different rates, full-batch times or deployment costs; do not relabel hypothetical values as measured.

## Verification

70 tests passed without skips. Six new tests cover current-evidence unknowns, shared rate sensitivities, unpriced labor, input immutability, demand-dependent economic reversal, capacity shortfall, boundary/ID/unit checks, rejected synthetic verification, and network-blocked replay/output protection. [Checks](checks.json) preserve the executed evidence and illustrative run hashes.
