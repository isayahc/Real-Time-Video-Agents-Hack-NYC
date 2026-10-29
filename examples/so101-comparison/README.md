# Matched SO-101 presentation-tool comparison (#66)

This compares two **executed simulation configurations** using the same stock
SO-101 gripper. It does not manufacture a successful grasp or a tooling winner.
The #64 run remains archived; it is not mixed into this new comparison.

## Diagnosis and common controller correction

The source collision meshes, sliced at the shared virtual TCP's Z coordinate,
show a 15.8000 mm X gap at gripper angle zero. The virtual TCP's X coordinate
coincides with the fixed jaw's inner face. Thus #64's zero-radian closure and
TCP-centred seed target were insufficient for an ideal 3 mm seed, independently
of the fixture contact. At the source lower limit (-0.174533 rad), the section's
X gap is about 2.4338 mm. These are source-geometry measurements, not calibrated
hardware commands or proof that the complete fingers can grip a seed.

Both new configurations use `config.json`: the grasp point is offset 1.5 mm
from the virtual TCP toward the gap (TCP-local X = -1.5 mm), and closure uses
the source lower joint limit. The imported robot geometry and its declared TCP
remain unchanged. `gripper-audit.json` records the checked source identity,
section bounds, gaps, correction and limits. The old #64 evidence is preserved.
The corrected smoke attempts still miss pickup and encounter contact; the
controller correction alone does not establish reliable grasp clearance.

## The two tools

| Configuration | Geometry under test |
| --- | --- |
| `reference_pocket` | Authored simple flat-bottom presentation pocket: 40 × 30 × 4 mm base, 4 mm radius post, 2 mm nominal circular opening and 0.25 mm shallow rim. Its floor positions the ideal sphere at the common nominal seed centre. |
| `cad_seat` | The hash-verified #63 OpenCAD candidate: the same base/post concept, with its authored conical seed seat and retained source bundle. |

The simple reference pocket is a simulation control, not a claimed commercial
fixture or a physically proven baseline. Both are valid fixed single-seed
presentation pockets under the benchmark. The reference was not tuned to
produce a failure or to make the candidate win. No comparative improvement is
inferred from visual differences, section gaps, or the fixture's design intent.

The presentation fixture belongs to the **tool** identity, alongside the
unchanged stock gripper. Its actual collision/visual OBJ hash changes between
candidates. Robot, controller, evaluator, environment, calibration, cameras,
nominal seed pose, physics parameters, target order and trial seeds remain
identical. `assets/source-cad-fixture-mm.stl` retains the original CAD source
in millimetres; the active tool is `assets/fixture.obj` in metres. Robot source
attribution and its Apache-2.0 license accompany exported meshes. Fixture geometry was under the environment identity in the archived
#64 integration; that older manifest cannot be compared directly with this one.

Both tools start with the same nominal seed pose, then settle under the same
contact rules. Tool-dependent settled positions are recorded rather than
teleported back into agreement. Both must satisfy the same 1 mm reset bound,
verified home pose, empty gripper and camera visibility. Changing the fixture
can change its contact response; it does not authorize changing calibration,
seed distributions, controller gains or the evaluator.

## Reproduce from the repository root

Use the Python 3.11 and pinned OI installation in the
[simulation guide](../so101-simulation/README.md).

```sh
SO101_SOURCE_ROOT="$PWD/runs/so101-source" python -m pytest -q tests/test_seed_comparison.py tests/test_seed_simulation.py
python -m protocol_pipeline.seed_comparison --source-root runs/so101-source --output runs/so101-comparison
node --import ./runs/oi-runtime/node_modules/tsx/dist/loader.mjs protocol_pipeline/seed_oi_bridge.mts runs/oi-runtime runs/so101-comparison/reference_pocket
node --import ./runs/oi-runtime/node_modules/tsx/dist/loader.mjs protocol_pipeline/seed_oi_bridge.mts runs/oi-runtime runs/so101-comparison/cad_seat
python -m protocol_pipeline.seed_simulation --verify-output runs/so101-comparison/reference_pocket
python -m protocol_pipeline.seed_simulation --verify-output runs/so101-comparison/cad_seat
python -m protocol_pipeline.seed_comparison --output runs/so101-comparison --compare-only
```

Choose a fresh output directory. `--smoke --no-video` executes the first pair,
negative control and repeat for each tool, but cannot supply completion evidence.
CI's `seed-simulation` job executes both complete schedules and uploads
`so101-matched-comparison`, including videos and portable OI scenes for every
case. Artifact retention is 30 days; reproduction uses pinned inputs.

## Comparison and existing accounting integration

Each tool executes seeds `[7,19,31]` against targets `(0,0),(2,5),(5,11)` in
that order: **nine nominal attempts per tool**. Each also has an open-gripper
negative control and a fresh-world repeat. Those two controls are reported
separately and excluded from placement denominators. V1 has no perturbations;
these are scheduled smoke cases, not independent reliability samples.

`comparison.json` contains paired seed/target records, accepted/attempted
counts, geometric placements, pickups, collision attempts, all applicable
recorded failure categories, cycle times, reset timings and per-trial evidence
paths/hashes. Failed nominal attempts remain in every denominator.

The comparator checks complete evidence and file hashes, verifies actual tool
and environment mesh identities, and calls the existing #60
`require_matched_trials` guard. Rehashed changes to non-tool components, altered
schedules, identical tool identities, incomplete runs or changed artifacts
are rejected. A successful hash check establishes content identity, not an
independent attestation of physical truth.

Counts feed the existing published `ProcessEvaluationInput` and
`evaluate_process` accounting contracts. `acceptance_verified` stays false:
there is no seed-damage model. Simulated cycle seconds and host wall-clock
reset seconds remain separate. They are never added to fabricate throughput.
Labor, energy, material loss and costs remain unknown. Zero accepted placements
are retained as evaluator decisions; they do not establish seed viability.
No economics engine or worker is reimplemented. The unpublished Serverless
worker referenced by #62 is absent from this checkout; this adapter targets
the accounting contract already published on `nebius-continuation`.

`winner` is null and ranking is not established. In particular, lower collision
counts or shorter failed cycles cannot establish a superior productive tool.
No live model call, Nebius job, learned policy, fabrication, physical trial or
biological success is claimed. The stock moving-link convex hulls, contact
margins, seed rigidity and grasp approach still require investigation before
hardware conclusions. Tooling revisions and cloud execution remain separate
work under the parent epic.
