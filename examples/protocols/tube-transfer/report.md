# Empty capped tube transfer candidate protocol

**Explicitly supplied plan; acceptance and physical performance remain unverified.**

Functional unit: One identified empty capped tube transferred intact into its intended destination rack position

Boundary: Source/destination rack preparation through placement verification, exception logging and station reset

| Operation | Phase / frequency | Candidate equipment |
| --- | --- | --- |
| prepare_racks: Prepare source and destination racks | preparation / per_batch | Stable rack fixture; Station coordinate reference |
| identify_tube: Identify a selected empty capped tube | processing / per_attempt | Manual ID entry or barcode reader; Position reference |
| grip_tube: Grip the selected tube | processing / per_attempt | Compliant gripper; Grip presence sensor |
| transfer_tube: Move the tube between racks | processing / per_attempt | Clearance envelope; Motion stage or robot arm |
| place_release: Place and release at destination | processing / per_attempt | Controlled gripper release; Rack locating fixture |
| verify_destination: Verify identity, presence and placement | finishing / per_attempt | ID log; Manual inspection or camera |
| reset_station: Reset the station and record exceptions | finishing / per_attempt | Controller; Event log |

## Resource results

| Metric | Value | Basis |
| --- | --- | --- |
| labor_s_per_accepted | unknown | unknown |
| electricity_wh_per_accepted | unknown | unknown |
| stock_g_per_accepted | unknown | unknown |
| recoverable_scrap_g_per_accepted | unknown | unknown |
| unrecovered_waste_g_per_accepted | unknown | unknown |
| accepted_outputs_per_hour | unknown | unknown |
| accepted_fraction | unknown | unknown |
| total_cost_usd_per_batch | unknown | unknown |
| cost_usd_per_accepted | unknown | unknown |

## Acceptance checks

- Correct tube identity at intended destination position, intact tube and cap: Define ID checks, rack occupancy, placement tolerance and damage inspection before testing
- Transfer without drop, collision, cap opening or unacceptable deformation: Measure dimensions, payload and grip-force envelope; review clearances and physical handling performance

## Missing resource inputs

- accepted_count
- allocated_tooling_cost
- attempted_count
- consumables_cost
- consumed_stock_g
- elapsed_s
- electricity_rate
- electricity_wh
- facility_cost
- labor_s
- loaded_labor_rate
- maintenance_cost
- other_utilities_cost
- paid_coverage_cost
- recoverable_scrap_g
- recovery_credit
- stock_cost
- unrecovered_waste_g

## Limitations

- Authored concept example, not an observed laboratory protocol or equipment recommendation
- The same compiler consumes this input and coil.json; capability/equipment choices are supplied, not AI-generated
- Acceptance, useful throughput, resource usage and apparatus feasibility require measurement
- No duration, operator burden, waste or safety envelope is inferred from operation labels

No durations, resource quantities or acceptance outcomes are inferred from operation names or equipment. Preparation ranges are not summed; concurrency and task overlap require review.
