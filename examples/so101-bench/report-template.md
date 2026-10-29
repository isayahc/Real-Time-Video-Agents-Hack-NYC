# SO-101 physical report — UNEXECUTED TEMPLATE

Status: not executed. All blank fields are unknown, not zero or passed.
This document alone cannot close #71.

## Run identity and release

- Run ID, date/time/timezone, operator and location:
- Scope: unpowered fit inspection / powered matched trial (select before execution):
- Robot serial/revision, gripper, firmware, controller commit:
- Robot model source-lock hash and hardware differences:
- Baseline tool revision, CAD/bundle hashes, fabrication record:
- Candidate tool revision, parent-bundle hash, CAD/bundle hashes, fabrication record:
- Simulation comparison commit, configuration hash, artifact/hash:
- Seed cultivar/lot, seed IDs and measured dimensions:
- Printer/material/settings; measured print dimensions and inspection evidence:
- Fastening, utility requirements and measured fixture/tray transforms:
- Calibration file/hash, home pose, camera IDs/calibration and uncertainty:
- Clearance observations/evidence; unresolved interference:
- Operator motion/stop checks and decision to proceed or block:
- Frozen physical acceptance thresholds and inspection method:
- Frozen candidate order, initial conditions and permissible reset deviations:
- Recording permissions and publication scope:

## Trial ledger

Add one row for every started attempt, including failures and aborts. Keep controls
separate. Link an immutable evidence path/hash plus timestamps, not just a filename.
Use `unknown` when observations cannot resolve an outcome.

| Trial / tool revision | Seed schedule ID / physical seed ID / target | Nominal or control | Initial/reset conditions | Cycle start/end / seconds | Reset seconds | Pickup | Seed count / placement | Visible damage | Accepted | Collision / failures / abort | Footage and images / hashes / time ranges |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Campaign result

| Evidence domain / revision | Tool | Planned / started / unstarted | Accepted / started | Unknown acceptance | Pickups / started | Collision attempts / started | Cycle time aggregation | Reset time aggregation | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

- Schedule completeness, exclusions and reasons:
- Failed attempts and overlapping failure counts:
- Non-tool differences and comparison validity:
- Observed fit, operation, limitations and unresolved acceptance:
- Measured resources (method/boundaries) or explicitly unknown:
- No-winner / supported conclusion with scope:

## Simulation discrepancies and revision ledger

| Bench observation and evidence | Simulation assumption / revision | Measured value, units, uncertainty | Model change and new revision | Matched rerun evidence | Remaining discrepancy / independent validation needed |
| --- | --- | --- | --- | --- | --- |

## Completion evidence

- Fabricated parts and exact robot/tool revisions evidenced:
- Physical report and permitted footage with hashes:
- Implementation commits and actual automated checks, if applicable:
- Bench-informed model changes and rerun artifacts:
- Remaining limitations and parent #59 update:
- #71 acceptance met: unknown until evidence reviewed.
