# Executed SO-101 baseline (issue #64)

This connects the pinned SO-101 model and passive seed seat to **PyBullet 3.2.7**,
then imports the **executed states** into native Open-Industries (OI) replay.
It is an offline rigid-body simulation, not a hardware experiment, learned
policy, live Nebius/GMI call, or successful planting demonstration.

## Capability audit and boundary

OI revision `9b34ec217563e2a6788d5e60d9cc74c0bcd21330` was inspected:

| Existing OI capability | Use in this integration |
| --- | --- |
| `src/lib/form.ts`: CAD mesh import; mm Z-up to metre Y-up conversion; asset recentering | Import actual robot-link, tray, fixture and seed meshes |
| `src/lib/workspace.ts`: portable scene serialization, keyframes, `evaluateWorkspace` | Replay measured simulated link/seed poses; validate every recorded timestamp after native round-trip |
| `server/simulation-service.ts`: domain/job command infrastructure | Not used as contact physics |
| `server/domains/work-cell.ts`: `fixture-v1` jobs consume resources and emit modeled production results | Not evidence of robotic grasp or placement |
| Pinned `package.json`: no rigid-body robotics/contact backend | Add PyBullet as a separate evaluator backend; no new physics engine |

The contact, motor, gravity, collision and rendering APIs come from the
[official PyBullet guide](https://github.com/bulletphysics/bullet3/blob/master/docs/pybullet_quickstartguide.pdf).
The original URDF, its inertial values, joint limits and collision meshes are
loaded directly. No suction, weld, seed-to-tool constraint or seed position
setter is used during a trial. Initial state setters are confined to setup;
reset creates a new isolated physics world. This is a local, file-based bridge,
not an OI server deployment or real-time co-simulation. OI interpolation is for
viewing only and never determines outcomes.

## Reproduce

Use **Python 3.11** (PyBullet 3.2.7 provides its Linux wheel for that version),
Node 22, and a fresh output directory. From the repository root:

```sh
python3.11 -m venv .venv-simulation
. .venv-simulation/bin/activate
python -m pip install -e '.[test,robot,simulation]'
python -m protocol_pipeline.robot_contract --lock examples/so101-robot/source-lock.json --source-root runs/so101-source --fetch
SO101_SOURCE_ROOT="$PWD/runs/so101-source" python -m pytest -q tests/test_seed_simulation.py
python -m protocol_pipeline.seed_simulation --source-root runs/so101-source --output runs/so101-executed

git clone https://github.com/Mapped-Assembly/Open-Industries.git runs/oi-runtime
git -C runs/oi-runtime checkout --detach 9b34ec217563e2a6788d5e60d9cc74c0bcd21330
npm ci --ignore-scripts --prefix runs/oi-runtime
node --import ./runs/oi-runtime/node_modules/tsx/dist/loader.mjs protocol_pipeline/seed_oi_bridge.mts runs/oi-runtime runs/so101-executed
python -m protocol_pipeline.seed_simulation --verify-output runs/so101-executed
```

The `seed-simulation` job in `.github/workflows/offline.yml` performs these checks
and retains the complete `so101-executed-simulation` artifact for 30 days.
Download it for longer retention. `--smoke` runs only the first pair plus repeat
and negative control. `--no-video` is useful for diagnosis. Neither option can
pass the completion-evidence verifier.

## Executed protocol

The frozen #60 benchmark is copied unchanged into a new **simulation** manifest.
All seven runtime components are materialized and hash-bound: robot, stock
gripper, controller, evaluator, environment, calibration and cameras. The
controller source snapshot is retained. The original definition-only manifest
is never upgraded in place. Its historical limitations describe that original
definition; runtime capabilities and limitations are recorded separately.

- Scene: fixed-base SO-101; 72 empty circular cups; the verified #63 CAD seat
  on a support block; one ideal spherical 3 mm seed; table; gravity.
- Layout: tray rotated +90 degrees about world Z, cell (0,0) rim at
  `(0.35, -0.22, 0.06)` m. Seat base at `(0.09, -0.12, 0.07)` m.
- Reset: rebuild the world, place one seed, set the pinned home/open pose,
  settle for 0.5 s, verify seed position within 1 mm, home within 0.001 rad,
  empty gripper, no unintended contact, and visible seed pixels in the close-up
  camera segmentation. The tray is empty by construction.
  A failed reset is retained and aborts remaining attempts. Reset wall time is
  separate from simulated cycle time.
- Policy: bounded numerical IK using the shared URDF FK, then position motors:
  approach, descend, close, lift. A pickup requires bilateral jaw contact,
  seed rise >10 mm and seed–TCP distance <20 mm over the final 24 lift samples.
  A missed pickup stops the attempt after the settling window; there is no
  retry. Only an observed pickup permits transport, release, retract and home.
  That transport branch is implemented but has not demonstrated a successful
  grasp or placement in the baseline.
- Schedule: seeds `[7,19,31]`, each followed by targets `(0,0),(2,5),(5,11)`.
  V1 defines no random perturbations, so these nine attempts are a smoke
  schedule, **not nine independent reliability observations**.
- Deliberate failure: repeat the first pair while suppressing closure (hold
  the gripper open). Inspect actual setpoints and observed failure. Since the
  nominal baseline also fails, this control does not establish that closure
  would otherwise produce a successful pickup.
- Reset repeat: rebuild and rerun the first nominal attempt; compare every
  recorded joint position/setpoint, seed pose/velocity and TCP position, not
  just the final outcome. Same-runtime tolerance is `1e-9`; cross-platform
  bitwise determinism is not claimed.

## Observations, actions, evaluation and frames

`trajectory.jsonl` contains every 240 Hz physics step: simulation time, phase,
commanded and actual joint radians, seed pose/velocity, TCP position, seed
contact link IDs/normal forces and unintended collisions. Commands must cover
all actuated joints and remain finite and within the source limits. IK uses a
separate kinematic model and records residuals; it never writes body states.

The evaluator converts actual seed positions into the tray frame and checks
whole-seed containment, 5 mm radial tolerance and speed <=2 mm/s throughout the
full final 1 s window. A 0.1 mm floor-contact tolerance accommodates solver
penetration. Collision and timeout remain explicit failures. A seed outside
the target cannot pass because a desired target or animation says otherwise.
The rigid-body backend has **no seed damage model**: even geometric placement
would yield `accepted: false`, damage `unknown`, and `invalid_observation`.
Unit tests exercise geometric placement without falsely accepting damage.

Bullet reports link rather than inertial frames through its link-state API;
the base inertial offset is removed explicitly. Reference matrices must match
the pinned contract within `1e-6` (Bullet link quaternions have float32-scale
rounding). OI uses `[x,z,-y]`, metres, XYZ Euler **degrees**. Asset-origin offsets
are rotated and translated with each observed pose. Native OI round-trip checks
all timestamps, original topology and four spread vertices per mesh per frame.
OI/Three.js Euler conversion near gimbal lock introduces micrometre-scale drift;
the adapter rejects world-vertex error above **0.01 mm**. No interpolation is
accepted as physics evidence.

## Retained evidence and limitations

Each attempt has `result.json`, `trajectory.jsonl`, `frames.json`, `trial.mp4`
and portable `replay.oi.json`. The video shows the executed Bullet state in a
wide view plus a seed-following close-up, including occlusion by the gripper.
`summary.json` reports schedule, repeat, failure and timing results;
`oi-report.json` binds each replay to the executed frame hash;
`evidence.json` hashes every retained file and rejects incomplete runs or later
changes. Reopen an OI scene using OI's portable-scene import; its timeline is
replay and contains no independent success claim.

The initial executed baseline misses pickup and detects fixture contact during
descent. This is useful negative evidence: the controller's kinematic TCP
solution does not establish clearance or seed acquisition. The original stock
robot collision meshes use Bullet's convex-hull approximation for dynamic
links; the fixed tray/seat use concave triangle meshes. The seat collision can
therefore reflect collider approximation as well as actual clearance. Resolve
collision geometry and grasp clearance before interpreting this as a hardware
failure or comparing new tools.

Mass (10 mg), friction (0.8), motor force cap (0.6 Nm), velocity (1 rad/s), gains,
layout, cup wall/floor geometry and timestep (1/240 s) are explicit assumptions.
The small rigid sphere jitters/penetrates slightly under the contact solver;
no convergence, compliant tissue, damage, germination, substrate, bulk
singulation, camera-based perception, GR00T training or physical calibration
has been established. The original robot/fixture provenance remains in #61/#63.
No paid inference is used.
