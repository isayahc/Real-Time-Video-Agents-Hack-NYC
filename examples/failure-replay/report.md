# Offline failure replay

**Fabricated scenarios; no physical observations or sensor detection claimed.**

| Case | Explicit skipped required steps | Unknown required steps | Metric deviations outside 10% | Unknown metrics |
| --- | --- | --- | --- | --- |
| missed_preparation | prep_verify_stock | none | none | none |
| delayed_batch | none | none | accepted_outputs_per_hour | none |
| excess_rejects | none | none | cost_usd_per_accepted, labor_s_per_accepted, electricity_wh_per_accepted, stock_g_per_accepted, accepted_outputs_per_hour | unrecovered_waste_g_per_accepted |
| incomplete_observations | none | prep_verify_stock | none | cost_usd_per_accepted, labor_s_per_accepted, electricity_wh_per_accepted, stock_g_per_accepted, unrecovered_waste_g_per_accepted, accepted_outputs_per_hour |

A missing observation does not establish a skipped operation. A delay in batch elapsed time does not prove winding was the cause.
