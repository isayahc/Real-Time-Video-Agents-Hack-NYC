# Deterministic process evaluator

Implements resource and recurring cost accounting for [epic #17](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/17). Runs locally without an API key or model call. It calculates values from explicit inputs; it does not predict missing physical behavior.

```bash
python -m protocol_pipeline evaluate \
  --input examples/process-evaluation/coil-v2-partial.json \
  --output /tmp/coil-process-report.json
```

The output must not already exist. For a complete unknown manual baseline, use `manual-baseline-unknown.json`. `coil-v2-partial-report.json` is the reproducible example report committed here.

## Contract and inputs

`ProcessEvaluationInput` and `ProcessEvaluationReport` are Python/Pydantic contracts; JSON schemas are in `schemas/process-evaluation-*.json`. Every input has a numeric `value` or null, exact `unit`, `basis` and `source`. Supported basis values are `unknown`, `measured`, `supplier_specification` and `assumed`. Non-unknown numbers, including zero, require a source. Inputs cannot be negative or nonfinite. Counts must be integers, and accepted count cannot exceed attempted count.

State the configuration, functional unit, consistent batch boundary and whether output acceptance has been verified. Verification requires an acceptance source. Numerical results may be calculated when acceptance is unverified, but the report stays partial and warns that equivalence has not been established. A complete report can still include assumptions, which remain labeled.

| Input | Unit | Meaning |
| --- | --- | --- |
| accepted_count, attempted_count | count | Final accepted count and attempts; rework keeps the original attempt |
| elapsed_s | s | Whole boundary wall time, not the sum of overlapping stages |
| labor_s | operator-s | Aggregate attended labor after merging overlaps per operator |
| electricity_wh | Wh | Energy consumed within the same boundary |
| consumed_stock_g | g | Consumed stock, excluding unused stock returned to inventory |
| recoverable_scrap_g, unrecovered_waste_g | g | Separate material dispositions; recovery does not imply a cash credit |
| loaded_labor_rate | USD/operator-hour | Loaded price of attended labor |
| electricity_rate | USD/kWh | Electricity price |
| stock_cost | USD/batch | Cost of stock actually consumed, including rejected/trial material within boundary |
| consumables_cost, other_utilities_cost | USD/batch | Cleaning/replacement consumables and utilities other than electricity |
| allocated_tooling_cost | USD/batch | Explicitly allocated tool/equipment consumption; caller supplies life/allocation assumptions |
| maintenance_cost, facility_cost | USD/batch | Allocated recurring maintenance and facility cost |
| paid_coverage_cost | USD/batch | Additional paid coverage not already charged as attended labor |
| recovery_credit | USD/batch | Realized or explicitly assumed net credit, subtracted once |

Omitted inputs are unknown; they are never converted to zero. Initial infrastructure investment and development labor are outside this recurring-cost calculation. If equipment amortization is desired, supply its justified batch allocation in `allocated_tooling_cost`; do not also count that allocation in maintenance or facility costs. This evaluator does not implement investment comparison, payback or automatic allocation.

## Labor events

Instead of aggregate `labor_s`, supply `attendance` plus `attendance_source` confirming the list covers the full boundary. Each interval records `operator_id`, `start_s`, `end_s`, `basis` (`measured` or `assumed`) and `source`. Intervals must lie within the known elapsed boundary. Overlaps are merged for each operator, then time is summed across operators. An explicit empty list with a source means zero attended labor; an omitted list means no interval-derived total. Aggregate labor and intervals cannot both be supplied.

Paid coverage is additional cost only. Do not charge attended time and the same paid shift again. Distinguish machine occupancy, elapsed time and operator attendance.

## Outputs and missing data

Metrics include labor seconds, electricity Wh, consumed stock grams, recoverable scrap grams, unrecovered waste grams and USD per accepted output, accepted fraction, accepted outputs/hour and total batch cost.

Each metric records dependencies, missing inputs, status and whether assumptions were used. No accepted outputs means per-accepted metrics are undefined. Zero elapsed time prevents a throughput calculation. Known batch costs remain available even when output is zero.

The report includes component costs and a **known cost subtotal**. If any required cost component is unknown, total cost and unit cost remain null. The partial subtotal is neither a total nor necessarily a lower bound, because missing recovery credit can reduce the eventual total. A zero energy input still needs a sourced price to make its cost complete under this conservative rule. Explicit zero/inapplicability decisions are required for every excluded cost component.

The complete validated input snapshot is embedded in the report. Completeness means every defined metric is calculable and acceptance is declared verified; it does not independently verify supplied measurements or prove the declared boundary covers the whole lifecycle. No model, simulation or price lookup is performed.

## Coil example

The v2 example scales existing illustrative assumptions to 100 attempts and 95 accepted coils. Its winding-only values reproduce approximately 15.79 operator seconds and 0.1667 Wh per nominal accepted coil. Labor price, full setup/cleanup, tooling allocation, recovery and other cost/resource values remain unknown, so total unit cost remains null. The example is not a complete process baseline or evidence that the apparatus beats manual winding. Use the manual workflow in `benchmarks/coil-winding/` to collect full-boundary inputs.

## Verification

```bash
python -m unittest discover -s tests -v
```

Accounting tests cover independently calculated full costs, recovery credits, missing costs/rates, zero output, interval overlap, invalid units/counts/nonfinite values, source requirements and preserving existing report files.
