# Infrastructure investment comparison

Compares two process configurations at the same accepted output and declared boundary. Implements the investment-comparison portion of [epic #17](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/17); it does not complete the observed-outcome feedback controller.

```bash
python -m protocol_pipeline compare \
  --input examples/investment-comparison/synthetic-comparison.json \
  --output /tmp/investment-report.json
```

The command runs locally, makes no model/API calls and refuses an existing output file. Python entry point: `compare_investment(InvestmentComparisonInput)`. Both input/report contracts have exported JSON schemas in `schemas/`.

## Cost model

Each option embeds an existing `ProcessEvaluationInput` containing a representative **variable-cost** batch. Unit cost comes from the deterministic process evaluator. Unknown unit-cost components remain unknown.

Keep three accounting buckets disjoint:

| Bucket | Input | Contents |
| --- | --- | --- |
| Upfront investment | `upfront.equipment`, `.installation`, `.integration`, `.training` in USD | One-time deployment costs; every category needs a sourced number or explicit unknown |
| Annual fixed expenses | `annual_fixed_cost` in USD/year | Fixed maintenance, facility, additional paid coverage and other fixed operating expenses |
| Variable production | Embedded process batch costs | Consumed stock, attended labor, energy, consumables, other variable utilities, recovery credits |

The batch fields `allocated_tooling_cost`, `facility_cost`, `paid_coverage_cost` and `maintenance_cost` must be explicitly sourced zero for this comparison. Nonzero values are rejected to prevent capital/fixed costs being charged again through unit cost. Allocate them into upfront or annual fixed expenses. Variable maintenance must be decomposed into consumable replacement and attended labor when applicable. The general process evaluator still supports its broader cost categories separately.

An existing manual setup can have zero incremental upfront cost only when justified as a sunk-cost baseline. Do not include historical equipment cost as new spending and also ignore the candidate's new spending. Capture whether the comparison is replacing existing infrastructure or choosing between two new deployments in the cost model source.

All values retain their basis (`unknown`, `measured`, `supplier_specification`, `assumed`) and source. Planning assumptions are allowed and remain visible. `cost_model_source` explains the variable/fixed split; `capacity_model_source` explains the nominal throughput and additional utilization/downtime factors.

## Demand and capacity

Supply annual accepted-output demand, analysis horizon, and for each option:

- `scheduled_hours`: h/year.
- `utilization`: fraction of scheduled time allocated to this process.
- `downtime`: fraction of allocated time unavailable.
- `useful_life`: years before replacement becomes necessary.

Annual accepted capacity = nominal accepted outputs/hour × scheduled hours × utilization × (1 − downtime). Nominal rate comes from the embedded batch's accepted count and elapsed duration. Apply only losses not already included in that rate. Demand is constant during the horizon; this first model does not auto-buy additional machines or model ramp-up, queues, overtime or nonlinear batch economies.

The decision is blocked when either option cannot meet demand. A horizon longer than either useful life is unsupported because replacement costs are not yet modeled. Unknown lifetime or capacity inputs block a complete conclusion.

## Comparison metrics

Let V be annual demand, H analysis years, C variable unit cost, F annual fixed cost, and K upfront investment.

| Metric | Formula |
| --- | --- |
| Annual operating cost, each option | C × V + F |
| Horizon total cost, each option | K + H × annual operating cost |
| Incremental upfront | K_candidate − K_baseline |
| Annual operating saving | Annual baseline cost − annual candidate cost |
| Horizon net saving | Baseline horizon cost − candidate horizon cost |
| Simple payback | Incremental upfront / positive annual operating saving |
| Horizon capital-recovery annual volume | (Incremental upfront / H + fixed-cost difference) / unit variable saving |

Payback is zero when there is no incremental capital and operating savings are positive; undefined when recurring savings are nonpositive, except a no-capital/no-operating-difference case. Lower upfront cost with higher operating cost is assessed through horizon cost instead of a negative payback number.

Break-even volume is a continuous **annual** threshold that recovers incremental capital over H years, not a total lifetime unit count. `horizon_break_even_direction` indicates whether the candidate is favorable above or below that threshold, or at all/no volumes. Equality at the threshold is a tie. For integer demand, round appropriately and verify both capacities. A threshold beyond capacity is not an attainable investment justification.

When unit costs are equal, the capital/fixed burden determines all/no volumes and there is no unique break-even threshold. Unknown inputs never become zero. There is no financing, discounting, tax, revenue, resale value or replacement model; results are an undiscounted cost comparison at equivalent output.

## Evidence and decisions

Functional unit and boundary strings must match. Both process acceptance flags and the separate output-equivalence flag must be verified with sources before a cost decision is returned. Matching strings alone are insufficient.

Status can be `calculated`, `insufficient_evidence`, `infeasible_capacity`, or `unsupported_horizon`. Decision is `candidate_lower_cost`, `baseline_lower_cost`, `equal_cost`, or `undetermined`. Numeric metrics may be available conditionally while a decision is blocked. A calculated result containing assumptions remains a planning scenario, not observed economic performance.

Reports preserve dependencies, missing values, issues, assumptions and the entire input snapshot. Cost completeness and equivalence flags are declarations backed by supplied sources, not independent audits performed by the software.

## Sensitivity scenarios

Each named scenario has sourced overrides and is evaluated independently without changing the base case. Supported paths:

- `annual_demand`, `horizon_years`.
- `baseline.*` / `candidate.*`: `annual_fixed_cost`, `scheduled_hours`, `utilization`, `downtime`, `useful_life`.
- `baseline.process.inputs.*` / `candidate.process.inputs.*`: `loaded_labor_rate`, `electricity_rate`, `stock_cost`.

All units/ranges and comparison gates are revalidated. Vary stock cost consistently with the representative batch quantity. Unsupported override paths and duplicate scenario names are rejected.

## Examples

`synthetic-comparison.json` is a clearly labeled arithmetic demonstration, not coil performance. At 10,000 outputs/year it compares USD 5 versus USD 2 variable unit cost, USD 1,000 versus USD 3,000 annual fixed cost, and USD 0 versus USD 10,000 incremental deployment cost. It yields USD 28,000 annual savings, about 0.357 years simple payback, and USD 130,000 undiscounted savings over five years. Lower demand makes the baseline cheaper; reduced utilization/downtime scenarios can make the candidate infeasible. A labor-rate scenario exercises changes to the underlying evaluator.

`coil-investment-unknown.json` uses the full manual workflow boundary for both options. It includes only the previously assumed USD 877.60 CW-02 equipment midpoint; installation, integration, training, operating inputs, demand, lifetime and equivalence remain unresolved. The expected decision is `undetermined`. This template does not convert the winding-only v2 example into a full production baseline.

## Verification

```bash
python -m unittest discover -s tests -v
```

Investment tests cover independent cost/payback arithmetic, absent capital costs, capacity/equivalence gates, lifetime, nonpositive savings, reversed/equal-unit-cost break-even cases, sensitivity isolation, mismatched boundaries, invalid ranges/units and fixed-cost double counting.
