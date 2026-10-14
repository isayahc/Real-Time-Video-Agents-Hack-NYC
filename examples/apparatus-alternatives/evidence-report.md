# Apparatus alternatives: manual fixture, motorized winder, CW-02

**Evidence: unmeasured_concepts. Physical validation: false. Recommendation: undetermined.**

Actual evidence lane: proposed manual, simple motorized and CW-02 configurations. Full-process quantities are unknown. The CW-02 equipment midpoint is an existing concept assumption, not installed cost.

## Shared comparison boundary

One accepted released coil meeting verified source protocol requirements

Stock verification and station preparation through accepted-product storage, scrap accounting and station reset

## Proposed architectures

| Alternative | Candidate equipment | Control / operator responsibilities |
| --- | --- | --- |
| Manual fixture | Screwdriver/mandrel; Manual wire-handling/cutting tools; Released-coil dimensional inspection; Product/scrap containers | Operator supplies rotation, pitch and tension; Operator inspects and releases every coil |
| Simple motorized winder | Low-speed motor and speed controller; Mandrel/chuck with guarded drive and stop; Manual guide and tension adjustment; Manual cutting and released-coil inspection | Motor supplies rotation only; Operator guides pitch, handles tension and stops at target turns; Operator cuts, releases and inspects |
| CW-02 coordinated winder | Stepper spindle and synchronized traverse; Removable mandrel clamp and wire guide; Passive dancer/spool brake and tension sensor; Camera/backlight and manual cutting/release tools | Proposed controller coordinates spindle and traverse; Proposed sensing supports tension/inspection; Manual loading, cutting, removal and acceptance remain |

## Supplied model inputs

Known numeric inputs below retain their basis; illustrative inputs are hypothetical and unmeasured.

| Alternative | Equipment USD | Other deployment USD | Annual fixed USD | Batch attempts / accepted | Elapsed / attended seconds | Batch Wh |
| --- | --- | --- | --- | --- | --- | --- |
| Manual fixture | unknown | installation: unknown; integration: unknown; training: unknown | unknown | unknown / unknown | unknown / unknown | unknown |
| Simple motorized winder | unknown | installation: unknown; integration: unknown; training: unknown | unknown | unknown / unknown | unknown / unknown | unknown |
| CW-02 coordinated winder | 877.6 (assumed) | installation: unknown; integration: unknown; training: unknown | unknown | unknown / unknown | unknown / unknown | unknown |

## Scenario results

Costs below are conditional arithmetic. All options retain unverified output acceptance/equivalence; none is an approved investment choice.

Variable unit cost excludes upfront and annual fixed allocations, which appear in horizon cost. Resource values use supplied full-batch inputs, not summed preparation ranges.

### current-evidence

| Alternative | Variable USD/coil | Labor s/coil | Wh/coil | Waste g/coil | Accepted/h | Annual capacity | Horizon cost USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Manual fixture | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| Simple motorized winder | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| CW-02 coordinated winder | unknown | unknown | unknown | unknown | unknown | unknown | unknown |

| Comparison | Evidence/capacity status | Decision | Break-even annual volume (direction)* | Payback years* |
| --- | --- | --- | ---: | ---: |
| manual → motorized | insufficient_evidence | undetermined | unknown (unknown) | unknown |
| manual → cw02 | insufficient_evidence | undetermined | unknown (unknown) | unknown |
| motorized → cw02 | insufficient_evidence | undetermined | unknown (unknown) | unknown |

*Threshold and payback are conditional and require checking capacity, output equivalence, and all supplied assumptions.

Blocking issues:

- Manual/apparatus output equivalence is unverified
- baseline output acceptance is unverified
- baseline.accepted_outputs_per_hour: Required inputs are unknown; missing accepted_count, elapsed_s
- baseline.annual_capacity is unknown: baseline.nominal_rate, baseline.scheduled_hours, baseline.utilization, baseline.downtime
- baseline.cost_usd_per_accepted: Required inputs are unknown; missing stock_cost, consumables_cost, allocated_tooling_cost, maintenance_cost, facility_cost, other_utilities_cost, paid_coverage_cost, recovery_credit, labor_s, loaded_labor_rate, electricity_wh, electricity_rate, accepted_count
- baseline.useful_life is unknown
- candidate output acceptance is unverified
- candidate.accepted_outputs_per_hour: Required inputs are unknown; missing accepted_count, elapsed_s
- candidate.annual_capacity is unknown: candidate.nominal_rate, candidate.scheduled_hours, candidate.utilization, candidate.downtime
- candidate.cost_usd_per_accepted: Required inputs are unknown; missing stock_cost, consumables_cost, allocated_tooling_cost, maintenance_cost, facility_cost, other_utilities_cost, paid_coverage_cost, recovery_credit, labor_s, loaded_labor_rate, electricity_wh, electricity_rate, accepted_count
- candidate.useful_life is unknown
- horizon_net_saving is unknown: baseline.horizon_total_cost, candidate.horizon_total_cost

## Measurements needed

- Manual fixture: Full-cycle attended time and elapsed time; Released-coil acceptance and repeatability; Actual tooling cost; Full stock/scrap and utility accounting
- Simple motorized winder: Motor/drive procurement and integration costs; Operator attendance while guiding and stopping; Safe torque/speed and wire tension; Quality, full-cycle energy and scrap
- CW-02 coordinated winder: Pitch/tension calibration and springback; Full-boundary labor, energy and accepted output; Installed cost, software/integration effort and reliability; Actual equivalent coil acceptance and maintenance

## Limits and assumptions

- Source video and annotation are not reviewed; alternative architectures are proposed concepts.
- Every alternative targets the same released-coil geometry/material/function; actual acceptance targets and equivalence remain unresolved.
- No investment recommendation can be made from unverified acceptance or hypothetical inputs.
- Preparation ranges and winding-only estimates are not summed or transferred into these full-boundary options.
- No yield/waste advantage is assumed for automation; shared hypothetical counts and stock are used to isolate labor/capital/energy effects.
