# CW-02 coil winding candidate protocol

**Explicitly supplied plan; acceptance and physical performance remain unverified.**

Functional unit: One accepted released coil; actual acceptance criteria unresolved

Boundary: Stock verification and station preparation through accepted-coil storage, scrap accounting and station reset, including allocated maintenance

| Operation | Phase / frequency | Candidate equipment |
| --- | --- | --- |
| prep_verify_stock: Select and verify wire stock/specification | preparation / per_batch | dimensional measuring tools; stock specification/label; wire stock |
| prep_prepare_mandrel: Inspect and prepare mandrel/fixture; clean if required | preparation / per_batch | cleaning materials if required; inspection tools; mandrel/fixture |
| prep_prepare_containers: Prepare labels, accepted-part trays and scrap container | preparation / per_batch | accepted-part tray; labels; scrap container |
| prep_thread_and_tension: Load/thread stock and establish initial tension | preparation / per_batch | spool brake/dancer; tension sensor; wire guide |
| prep_home_and_calibrate: Home axes and calibrate inspection, where applicable | preparation / per_batch | axis controller; home sensors; inspection calibration reference |
| prep_trial_coil: Produce/inspect a trial coil and adjust settings | preparation / per_batch | released-coil inspection tools; winding apparatus |
| prep_measure_cut: Measure and cut/pre-position wire | preparation / per_attempt | length measure; manual wire cutter |
| prep_prepare_ends: Straighten/prepare ends if required | preparation / per_attempt | manual wire preparation tools if required |
| prep_orient_secure: Orient and secure wire for winding | preparation / per_attempt | removable mandrel clamp |
| constrain: load wire end: wire held without slipping | processing / per_attempt | removable mandrel clamp |
| establish_contact: thread the guide: wire contacts cylindrical forming surface | processing / per_attempt | guide and mandrel |
| relative_rotation: start cycle: target turns and pitch formed | processing / per_attempt | stepper spindle and synchronized traverse |
| maintain_tension: set tension during setup: stable tension below tested damage limit | processing / per_attempt | passive dancer/spool brake and tension sensor |
| verify_and_release: cut and remove coil: inspect final diameter, pitch, turns and lead geometry after release | processing / per_attempt | camera/backlight, removable mandrel and manual cutting tools |
| rework: Rework a rejected coil where feasible | finishing / per_rework | Hands; forming fixture; inspection tools |
| label_store: Label and store accepted coil | finishing / per_accepted | Product tray; labels |
| scrap_recover: Segregate and account for recoverable scrap | finishing / per_batch | Scrap container; scale |
| cleanup: Clean and reset station | finishing / per_batch | Cleaning tools if needed |
| maintenance: Maintain/replace tools | finishing / per_maintenance_event | Replacement tooling |

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

- Released coil meets material, geometry and downstream function requirements: Resolve target tolerances and test method; verify springback and actual functional equivalence

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

- Fixed planning protocol; original video and annotation have not been ingested or reviewed.
- Equipment and graph links are proposed candidates, not a verified BOM or executable schedule.
- Preparation applicability and repetitions need review; trial coils may repeat forming/inspection.
- Threading, clamping, cutting and inspection may overlap existing allowances; ranges are not summed.
- Full-process measurements and released-coil acceptance criteria remain unresolved.

No durations, resource quantities or acceptance outcomes are inferred from operation names or equipment. Preparation ranges are not summed; concurrency and task overlap require review.
