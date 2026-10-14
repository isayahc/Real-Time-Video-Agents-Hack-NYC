# Apparatus alternatives: manual fixture, motorized winder, CW-02

**Evidence: illustrative_assumptions. Physical validation: false. Recommendation: undetermined.**

Exploratory arithmetic with invented full-batch performance and budget assumptions. These numbers are not estimates of real manual/motorized performance and do not validate CW-02. Acceptance and equivalence stay unverified.

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
| Manual fixture | 100 (assumed) | installation: 0 (assumed); integration: 0 (assumed); training: 0 (assumed) | 50 (assumed) | 100 (assumed) / 95 (assumed) | 10000 (assumed) / 9000 (assumed) | 10 (assumed) |
| Simple motorized winder | 300 (assumed) | installation: 0 (assumed); integration: 0 (assumed); training: 0 (assumed) | 75 (assumed) | 100 (assumed) / 95 (assumed) | 8000 (assumed) / 7000 (assumed) | 30 (assumed) |
| CW-02 coordinated winder | 877.6 (assumed) | installation: 0 (assumed); integration: 0 (assumed); training: 0 (assumed) | 125 (assumed) | 100 (assumed) / 95 (assumed) | 6000 (assumed) / 5000 (assumed) | 50 (assumed) |

## Scenario results

Costs below are conditional arithmetic. All options retain unverified output acceptance/equivalence; none is an approved investment choice.

Variable unit cost excludes upfront and annual fixed allocations, which appear in horizon cost. Resource values use supplied full-batch inputs, not summed preparation ranges.

### 1000-coils-per-year

| Alternative | Variable USD/coil | Labor s/coil | Wh/coil | Waste g/coil | Accepted/h | Annual capacity | Horizon cost USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Manual fixture | 37.0253 | 94.7368 | 0.1053 | 0.0021 | 34.2 | 24,624 | 111,325.7947 |
| Simple motorized winder | 36.92 | 73.6842 | 0.3158 | 0.0021 | 42.75 | 30,780 | 111,285.1316 |
| CW-02 coordinated winder | 36.8148 | 52.6316 | 0.5263 | 0.0021 | 57 | 41,040 | 111,697.0684 |

| Comparison | Evidence/capacity status | Decision | Break-even annual volume (direction)* | Payback years* |
| --- | --- | --- | ---: | ---: |
| manual → motorized | insufficient_evidence | undetermined | 871.1818 (above) | 2.4931 |
| manual → cw02 | insufficient_evidence | undetermined | 1,588.0852 (above) | 5.7412 |
| motorized → cw02 | insufficient_evidence | undetermined | 2,304.9887 (above) | 10.4598 |

*Threshold and payback are conditional and require checking capacity, output equivalence, and all supplied assumptions.

Blocking issues:

- Manual/apparatus output equivalence is unverified
- baseline output acceptance is unverified
- candidate output acceptance is unverified

### 10000-coils-per-year

| Alternative | Variable USD/coil | Labor s/coil | Wh/coil | Waste g/coil | Accepted/h | Annual capacity | Horizon cost USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Manual fixture | 37.0253 | 94.7368 | 0.1053 | 0.0021 | 34.2 | 24,624 | 1,111,007.9474 |
| Simple motorized winder | 36.92 | 73.6842 | 0.3158 | 0.0021 | 42.75 | 30,780 | 1,108,126.3158 |
| CW-02 coordinated winder | 36.8148 | 52.6316 | 0.5263 | 0.0021 | 57 | 41,040 | 1,105,697.2842 |

| Comparison | Evidence/capacity status | Decision | Break-even annual volume (direction)* | Payback years* |
| --- | --- | --- | ---: | ---: |
| manual → motorized | insufficient_evidence | undetermined | 871.1818 (above) | 0.1947 |
| manual → cw02 | insufficient_evidence | undetermined | 1,588.0852 (above) | 0.3832 |
| motorized → cw02 | insufficient_evidence | undetermined | 2,304.9887 (above) | 0.5763 |

*Threshold and payback are conditional and require checking capacity, output equivalence, and all supplied assumptions.

Blocking issues:

- Manual/apparatus output equivalence is unverified
- baseline output acceptance is unverified
- candidate output acceptance is unverified

### 30000-coils-per-year

| Alternative | Variable USD/coil | Labor s/coil | Wh/coil | Waste g/coil | Accepted/h | Annual capacity | Horizon cost USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Manual fixture | 37.0253 | 94.7368 | 0.1053 | 0.0021 | 34.2 | 24,624 | 3,332,523.8422 |
| Simple motorized winder | 36.92 | 73.6842 | 0.3158 | 0.0021 | 42.75 | 30,780 | 3,323,328.9475 |
| CW-02 coordinated winder | 36.8148 | 52.6316 | 0.5263 | 0.0021 | 57 | 41,040 | 3,314,586.6527 |

| Comparison | Evidence/capacity status | Decision | Break-even annual volume (direction)* | Payback years* |
| --- | --- | --- | ---: | ---: |
| manual → motorized | infeasible_capacity | undetermined | 871.1818 (above) | 0.0639 |
| manual → cw02 | infeasible_capacity | undetermined | 1,588.0852 (above) | 0.1247 |
| motorized → cw02 | insufficient_evidence | undetermined | 2,304.9887 (above) | 0.1859 |

*Threshold and payback are conditional and require checking capacity, output equivalence, and all supplied assumptions.

Blocking issues:

- Manual/apparatus output equivalence is unverified
- baseline capacity cannot meet annual demand
- baseline output acceptance is unverified
- candidate output acceptance is unverified

### 10000-coils-unpriced-labor

| Alternative | Variable USD/coil | Labor s/coil | Wh/coil | Waste g/coil | Accepted/h | Annual capacity | Horizon cost USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Manual fixture | 36.5516 | 94.7368 | 0.1053 | 0.0021 | 34.2 | 24,624 | 1,096,797.4211 |
| Simple motorized winder | 36.5516 | 73.6842 | 0.3158 | 0.0021 | 42.75 | 30,780 | 1,097,073.6842 |
| CW-02 coordinated winder | 36.5517 | 52.6316 | 0.5263 | 0.0021 | 57 | 41,040 | 1,097,802.5474 |

| Comparison | Evidence/capacity status | Decision | Break-even annual volume (direction)* | Payback years* |
| --- | --- | --- | ---: | ---: |
| manual → motorized | insufficient_evidence | undetermined | undefined (no_volumes) | undefined |
| manual → cw02 | insufficient_evidence | undetermined | undefined (no_volumes) | undefined |
| motorized → cw02 | insufficient_evidence | undetermined | undefined (no_volumes) | undefined |

*Threshold and payback are conditional and require checking capacity, output equivalence, and all supplied assumptions.

Blocking issues:

- Manual/apparatus output equivalence is unverified
- baseline output acceptance is unverified
- candidate output acceptance is unverified

### 10000-coils-higher-labor-rate

| Alternative | Variable USD/coil | Labor s/coil | Wh/coil | Waste g/coil | Accepted/h | Annual capacity | Horizon cost USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Manual fixture | 37.3411 | 94.7368 | 0.1053 | 0.0021 | 34.2 | 24,624 | 1,120,481.6316 |
| Simple motorized winder | 37.1657 | 73.6842 | 0.3158 | 0.0021 | 42.75 | 30,780 | 1,115,494.7369 |
| CW-02 coordinated winder | 36.9903 | 52.6316 | 0.5263 | 0.0021 | 57 | 41,040 | 1,110,960.4421 |

| Comparison | Evidence/capacity status | Decision | Break-even annual volume (direction)* | Payback years* |
| --- | --- | --- | ---: | ---: |
| manual → motorized | insufficient_evidence | undetermined | 522.6254 (above) | 0.1157 |
| manual → cw02 | insufficient_evidence | undetermined | 952.6986 (above) | 0.2265 |
| motorized → cw02 | insufficient_evidence | undetermined | 1,382.7719 (above) | 0.339 |

*Threshold and payback are conditional and require checking capacity, output equivalence, and all supplied assumptions.

Blocking issues:

- Manual/apparatus output equivalence is unverified
- baseline output acceptance is unverified
- candidate output acceptance is unverified

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
- Hypothetical full-batch totals per 100 attempts: manual 10000 elapsed s / 9000 attended s / 10 Wh; motorized 8000 / 7000 / 30; CW-02 6000 / 5000 / 50. These are scenario inputs, not derived observations or automatic task sums.
- Manual $100 and motorized $300 equipment budgets are arbitrary exploration values, not market prices. CW-02 $877.60 is the existing conceptual equipment midpoint only.
- Installation/integration/training and selected batch cost components are explicitly assumed zero for this scenario. Actual evidence lane keeps them unknown; zero-priced engineering is not proof of zero effort.
- Annual fixed costs of $50/$75/$125, 1000 scheduled h/year, utilization 0.8, additional downtime 0.1 and 5-year useful life are unmeasured scenario assumptions.
- Base labor $18/operator-hour and electricity $0.20/kWh are hypothetical shared rates; sensitivity explores labor $0 and $30. Unpriced labor does not remove operator time.
- 95 accepted / 100 attempted is a shared hypothetical 95% accepted fraction, not evidence of yield. All accepted-output metrics remain conditional.
- Stock cost dominates this example and is held identical; recoverable scrap about 1.008 g from the shared hypothetical material balance, unrecovered waste 0.2 g and recovery credit $0 are arbitrary shared assumptions. No waste reduction is claimed.
- Linear economics hold the 100-attempt batch assumptions constant across annual demand. No batch-size scale advantage, financing, tax, resale or replacement is modeled.
