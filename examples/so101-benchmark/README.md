# SO-101 seed-placement benchmark v1

Issue #60 defines the inputs for #61–#71. This fixture freezes an **authored,
assumption-only benchmark**, not a robot result. It selects uncoated radish seeds,
an idealized 72-cell tray and one isolated seed per pickup. Cultivar, physical lot,
actual seed dimensions and tray measurements remain unknown. This selection is
an engineering starting point, not a claim about a farmer's seed or tray inventory.

## Run and consume

```bash
python -m pip install -e '.[test]'
python -m protocol_pipeline.seed_benchmark \
  --manifest examples/so101-benchmark/manifest.json \
  --output runs/so101-contract-validation.json
python -m pytest tests/test_seed_benchmark.py -q
```

Outputs are created exclusively; choose a new output path for another run.
`validation-report.json` is the executed local contract validation report. It
records input/artifact hashes and blockers, with execution, provider evidence
and physical-performance flags all false. No trial outcomes are fabricated.
CI runs the same tests and archives a fresh validation report on Python 3.11/3.12.

`TrialManifest` in `protocol_pipeline.seed_benchmark` is the authoritative typed
contract. `manifest.schema.json` is its generated JSON Schema for editors and
other consumers. Python validation is mandatory: JSON Schema alone cannot enforce
cross-field checks, artifact hashes, or matched-trial comparisons.

Use `validate_manifest(path)` at ingestion to verify all seven dependency files.
Use `require_matched_trials(baseline, candidate)` before any tooling comparison;
it permits changes only to the experiment ID and tool identity. It rejects changes
to policy, evaluator, robot, environment, calibration, cameras, task, evidence kind,
targets, random seeds, initial conditions or timing. Runtime integrations must
validate both bundles before comparison. Changing the fixture or acceptance rules
requires a new benchmark version and regeneration of its report/schema as needed.

## Numerical protocol decisions

The source of every number below is **this authored protocol decision**, made for
issue #60. These are not manufacturer specifications, measurements or sourced
performance estimates. `basis=definition` means a chosen task requirement;
`basis=assumption` means an unmeasured simulator input.

| Input | Frozen value | Basis |
| --- | --- | --- |
| Tray topology | 6 rows × 12 columns | Definition; 72 selected cells |
| Grid pitch, X and Y | 40 mm | Simulation assumption |
| Circular cell opening / depth | 30 / 40 mm | Simulation assumption |
| Spherical seed diameter | 3 mm | Simulation assumption; no biological size claim |
| Accepted seeds per target | Exactly 1 | Definition |
| Maximum radial center error | 5 mm | Simulation assumption |
| Settling interval / cycle timeout | 1 / 30 seconds | Simulation assumptions |
| Trial random seeds | 7, 19, 31 | Authored repeatability schedule |
| Target cells (row, column) | (0, 0), (2, 5), (5, 11) | Authored coverage sample |

All indices are zero-based; X increases with columns, Y with rows, Z points up.
The origin is the center of cell (0, 0) at its rim. Each seed/target pair is one
attempt, in seed-major listed order: nine attempts per candidate. This is a smoke
test, not a powered reliability study. The evaluator must record its RNG algorithm
and version in its artifact. V1 has no randomized perturbations; seed assignment
is frozen for later deterministic stochastic dynamics. Introducing perturbation
distributions requires a new benchmark and identical sampled initial conditions
across candidates.

## Acceptance and timing

Simulation acceptance requires exactly one seed, wholly within the target cell
and below its rim after the settling interval, radial center error within the
declared tolerance, and no evaluator damage flag. Missing observations or an
unimplemented damage model are `invalid_observation`, never successful placement.
Rigid-body simulation does not establish seed viability. Collisions, timeouts and
execution errors invalidate an attempt even if its final seed position looks good.
Success requires completion of the whole cycle, including return home.

Physical acceptance uses calibrated pre/post images to verify count, containment,
radial placement and absence of visible cracking/crushing. Occlusion, ambiguous
count, missing calibration or missing damage inspection invalidate the observation.
Visible inspection cannot establish germination or internal damage. Physical
acceptance is blocked until its unknown dimensions and thresholds are supplied.

The cycle starts from verified home/empty gripper, immediately before pickup; it
ends after acceptance and return home, or at a recorded failure stop. Timeout
includes pickup, transit, release, settling, inspection and return. No retry is
hidden inside an attempt. Reset is separately timed from cycle end to verified
initial conditions. Report both cycle and reset durations; throughput must include
both. Never discard failed attempts from the denominator. A reset failure is
retained and aborts the remaining schedule, whose entries remain unattempted.

Reset removes all tray seeds, replenishes the single-seed presentation pocket,
restores tray/robot poses and resets evaluator/RNG state. Verify home, empty gripper,
empty tray, one presented seed, transforms and camera visibility before each attempt.
Simulation starts with empty cells and no substrate; physical substrate and all
poses must be frozen in materialized environment/calibration artifacts before use.

| Failure | Meaning |
| --- | --- |
| `pickup_miss` | No seed acquired |
| `multiple_seeds` | More than one seed acquired or delivered |
| `dropped_seed` | Seed lost before intended release |
| `wrong_cell` | Seed delivered outside the target cell |
| `outside_tolerance` | Target reached but containment or position rule fails |
| `damaged_seed` | Applicable damage check fails |
| `collision` | Unallowed robot/tool/environment contact |
| `timeout` | Full cycle exceeds the declared limit |
| `reset_failed` | Repeatable initial conditions could not be restored |
| `invalid_observation` | Evidence insufficient to decide acceptance |
| `execution_error` | Controller, simulator or device execution fails |

Downstream trial records must retain all applicable failure categories; they may
co-occur. The manifest defines inputs only. Result storage/evaluation is #64/#66;
provider job IDs and live-provider verification are separate evidence under #67/#68.
Cloud execution does not convert simulation into physical evidence.

## Physical measurements required

Unknown values are explicit nulls with `basis=unknown` and this source reference.
Do not fill them with the simulation assumptions. Required work includes cultivar
and seed-lot identification, seed-size distribution and damage inspection method,
tray opening/depth/pitch, physical tolerances, settling/time limits, substrate,
camera calibration/uncertainty, robot/home/tool transforms and initial seed pose.

Each component currently points to a hashed, versioned **definition-only** file.
These are real contract artifacts, not fake URDFs, policy weights or evaluator
executables. Replace them with attributable, pinned runtime artifacts in the
dependent tasks. The validator verifies bytes, not that a supplied executable
implements physics correctly; domain validation remains required in #61/#64/#71.
`execution_requested=true` rejects assumptions, definition-only components, unknown
required quantities, and physical quantities labeled as assumptions. A successful
contract check does not itself authorize hardware motion or prove runtime readiness.
