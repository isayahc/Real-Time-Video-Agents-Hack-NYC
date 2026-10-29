# SO-101 contact-margin correction — draft follow-up to #71

**Scope: an opt-in PyBullet runtime correction, diagnostic grasp investigation,
and a placement tracking gate. #71 remains open pending physical evidence.**
The default dependency, robot geometry, motor limit and CAD v1 remain unchanged.

## Defect and correction

PyBullet 3.2.7's `b3ChangeDynamicsInfoSetCollisionMargin` sets `m_linkIndex = -1`.
Thus Python `changeDynamics(robot, jaw_index, collisionMargin=...)` targets the
base, even when other link-specific properties are passed in the same call.
Separately, the server's link branch changes only the outer collision shape;
URDF mesh hulls can be children of compound shapes.

[`pybullet-3.2.7-link-margin.patch`](../scripts/patches/pybullet-3.2.7-link-margin.patch):

- Adds a link-aware setter and uses it from Python; preserves the old C entry point.
- Propagates requested link margins through compound children and recalculates
  compound AABBs. Source vertices, joint limits and inertias stay unchanged.
- Labels the custom build `3.2.7+issue71margin1` and bounds compilation to four jobs.

This is a local diagnostic patch, not an upstream release. The base-body margin
implementation is not generalized by this patch. Numerical margin values remain
simulation assumptions, not hardware tolerances.

## Reproduce in an isolated Linux Python 3.11 environment

Requires a C++ compiler (`build-essential` on Ubuntu), Git and network access for
dependencies. Preserve the stock runtime. From the repository root:

```bash
REPO="$PWD"
python3.11 -m venv /path/to/new-margin-venv
source /path/to/new-margin-venv/bin/activate
python -m pip install setuptools wheel 'numpy==2.3.5' -e '.[test,robot,simulation]'
mkdir -p runs/margin-build
curl -fL https://files.pythonhosted.org/packages/de/95/b9a98cd4ed948d4f25a7d0b13cb0c1f87e58dc6d113be9e18940641eb25f/pybullet-3.2.7.tar.gz -o runs/margin-build/pybullet-3.2.7.tar.gz
echo '042879db8d101ac7590dee475fc6aded508b85fe1273fdbbfde1d88bd200e14f  runs/margin-build/pybullet-3.2.7.tar.gz' | sha256sum -c -
tar -xzf runs/margin-build/pybullet-3.2.7.tar.gz -C runs/margin-build
cd runs/margin-build/pybullet-3.2.7
git apply --check "$REPO/scripts/patches/pybullet-3.2.7-link-margin.patch"
git apply "$REPO/scripts/patches/pybullet-3.2.7-link-margin.patch"
python setup.py bdist_wheel
python -m pip install dist/pybullet-3.2.7+issue71margin1-*.whl
cd "$REPO"
SO101_MARGIN_RUNTIME_TESTS=1 python -m pytest -q tests/test_pybullet_link_margin.py
SO101_SOURCE_ROOT=runs/so101-source python -m pytest -q -rs tests/test_robot_contract.py tests/test_seed_simulation.py tests/test_seed_comparison.py
```

Fetch pinned robot sources using the existing robot-contract guide before the
second test command. The new margin tests use generated geometry and need no
robot download. They are opt-in because they intentionally fail on stock 3.2.7.
Default simulation execution does not request the corrected jaw margin; adopting
it in a production run requires explicit configuration and runtime provenance.

## Actual verification (2026-10-29)

- New regression tests on stock 3.2.7: **2 failed**, reproducing base mutation and
  unchanged child contact distance. Same tests on custom runtime: **2 passed**.
- Existing robot/simulation/comparison tests on custom runtime: **66 passed**,
  no skips (219.42 s); yourdfpy deprecation warnings remain.
- Eight frozen failed-pose contact queries changed by exactly **+0.99 mm** when
  the requested jaw margin decreased from 1 mm to 0.01 mm. Only the intended link
  changed. At one failed lift pose, source/FCL clearance was 0.829129 mm;
  stock Bullet reported -0.176321 mm, corrected Bullet +0.813679 mm.
- Not all Bullet distances equal source/FCL distances: one commanded-pose query
  remained 0.360981 mm versus 0.083006 mm. Convex approximation and numerical
  distance behavior are still distinct from source-surface and hardware evidence.

The original WSL offline suite had **419 passed, 17 skipped, 12 subtests passed**;
native fixture verification later had **39 passed, 2 skipped**. Those earlier
counts predate the two new opt-in tests. Unchanged baseline trajectories and
frames reproduced the original #66 artifact byte-for-byte for both tools.

## Motion results and explicit limitations

The completed stock-runtime +6 mm-offset comparison had **0 pickups / 9 and
0 accepted / 9 for both tools**; reference had 0 collision attempts, CAD had 9.
Both complete bundles passed the existing evidence verifier and native OI replay
checks; these are evidence-integrity checks, not task success.

With corrected margins, paired +6 mm smoke trials still failed pickup. Neither
nominal attempt contacted the seed during descent/closure; the moving jaw touched
it only briefly during lift. A separate 1.2 mm supporting-web mesh prototype also
failed pickup/collision in all six attempted cases, and the comparator rejected
its controlled inputs as mismatched. It is **not** a valid matched campaign,
fabrication-ready CAD revision, or adopted fix. Its failed results remain local.

At that stage no sustained bilateral pickup or successful transport had been
demonstrated. No physical fabrication, hardware calibration, authorized physical
trial or live provider call is claimed.
The rigid-body evaluator has no seed-damage channel. The next motion step is to
diagnose the failed relief/controller path and its input mismatch before adopting
any revised geometry or launching another full comparison.

## Follow-up diagnostics: collision representation and motion

Further local diagnostics separated three additional failure sources:

- The rejected prototype comparison included its backup
  `assets/unrelieved-fixture.obj` in the candidate environment hash. Moving the
  backup outside `assets` restores matching without weakening the comparator.
- Whole-mesh convex hulls fill jaw concavities. Splitting each jaw collider at
  the source TCP plane preserves separate distal/proximal hulls. At a checked
  fixed-jaw target, source clearance is 0.863851 mm and split-tip Bullet clearance
  is 0.847929 mm, versus approximately -0.970332 mm with the whole-mesh hull.
  These remain approximate colliders, not certified source-surface equivalence.
- Single joint-setpoint moves cause transient support intersections. A shared
  48-waypoint descend/lift diagnostic was executed with a 2 mm distal grasp
  offset and two-second closure. A 0.6 mm support web failed initial seed
  settling; the 1.2 mm web passed reset.

The completed **simulation-only** smoke at
`runs/issue71-continuous-offset2-web12-complete/` produced CAD nominal and repeat
pickups, each retaining bilateral contact throughout the two-second lift. The
nominal seed rose approximately 29 mm. The open-gripper CAD control missed;
all three reference-pocket attempts failed pickup with collisions. The paired
comparator completed without an input-mismatch exception. Neither candidate
achieved successful placement or full acceptance.

Crucially, absence of recorded unwanted contacts during CAD grasp/lift is **not
proof of zero intersection**: the evaluator filters contacts at 0.1 mm penetration
and 0.001 N force. At nominal closure the source moving jaw intersects the support,
and split-tip Bullet reports about 0.060 mm penetration at the executed pose.
The commanded pose reports about 0.199 mm penetration. This requires geometric
clearance correction before adopting the prototype.

Transport remains a single joint-setpoint move. In the nominal CAD attempt it
collides with the tray starting at 9.5125 s; its final TCP is near Z=0.062 m rather
than the requested grasp point near Z=0.110 m, with shoulder/wrist errors around
0.1 rad. After release the seed passes through the environment. The contact,
tracking and tunneling failures remain unresolved. An earlier execution at
`runs/issue71-continuous-offset2-web12-smoke/` timed out after the CAD nominal
result; it is preserved separately from the completed run.

No production controller/CAD changes, native CAD revision, video campaign, live
provider execution or physical validation resulted from these local probes.
Next: remove the small source-support overlap and validate source clearance,
then diagnose Cartesian transport reachability/tracking and tray collision.

## Deeper isolation: transport load and discrete mesh tunneling

The next investigation isolated causes instead of changing several campaign
parameters together. All results below are **offline simulation/model evidence**.

### Transport exceeds the configured shoulder torque

Source FK puts the commanded transport grasp point at
`[0.349227, -0.219443, 0.109582]` m, close to the requested
`[0.35, -0.22, 0.11]` m. The executed grasp point instead ends at
`[0.336242, -0.210703, 0.061136]` m. This is predominantly a dynamics/tracking
failure, not a 49 mm IK error.

An isolated replay starts at the recorded lift joint positions, removes the seed,
all obstacles and self-collisions, and commands the same transport setpoint:

| Gravity | Motor limit | Result |
| --- | --- | --- |
| -9.81 m/s² | 0.6 N·m | Shoulder saturates at -0.6 N·m; error remains 0.832 rad after 6 s |
| 0 | 0.6 N·m | All joint errors below 0.00004 rad after 2 s |
| -9.81 m/s² | 2 N·m, diagnostic only | All joint errors below 0.0014 rad after 2 s; shoulder uses about -0.769 N·m |

Independent static inverse-dynamics queries require **0.76914 N·m at transport**
and **0.78915 N·m at placement**, exceeding the configured 0.6 N·m even without a
seed or acceleration. The lift pose requires only 0.11225 N·m at the shoulder.
This explains why pickup can work while extended transport sags. Tray contact
then supports/obstructs the sagging arm; it cannot be treated as the sole cause.
Waiting longer or only smoothing the Cartesian path cannot make these final
poses statically feasible under the current model and torque limit.

The 2 N·m case is an ablation, **not a measured motor rating or adopted fix**.
Resolve model mass/inertia assumptions and actuator limits, or move the target
into a torque-feasible workspace, before choosing production settings.

### Table tunneling is reproducible without the robot

A simple drop from rest lands correctly, so that alone would miss the defect.
Replaying the recorded seed pose/velocity at 12.1 s against only the actual table
mesh reproduces fall-through. The table is a triangle surface representation;
its 30 mm envelope does not provide volumetric collision response between faces.
Near its top surface the seed travels about 4.54 mm per recorded physics step,
larger than its 3 mm diameter.

The 48-case matrix varies initial state (rest/recorded), mesh/identical box
primitive, reduced/maximal coordinates, 0/4/16 internal substeps, and CCD off/on.
Both **stock and patched runtimes produce identical drop results**:

- Recorded-state mesh cases with no internal substeps fall through, with CCD
  either enabled or disabled and with either coordinate formulation.
- Four and sixteen internal substeps stop the recorded-state fall-through.
- An identical box primitive also stops it without internal substeps.
- The existing CCD setting alone does not resolve this reproduction.
- Sphere AABBs retain the intended 3 mm diameter; the margin request did not
  shrink the seed to a 20 µm collider.

This is a discrete collision representation/integration failure independent of
the link-margin patch. Four substeps passing this example is not a convergence
proof for grasp forces or tray placement. Any adopted integration change must
apply to both candidates and rerun the matched controls and timestep checks.

### Remaining controller and evidence gaps

`execute_trial` records IK residuals but advances without enforcing a tracking
gate; placement releases after a fixed duration even when the grasp point is
about 19 mm below the requested placement height. A checked motion policy needs
explicit infeasible/failed-tracking outcomes before release. The diagnostics
also still have the small source-support overlap reported above.

Monkey-patched diagnostic wrappers are described by sidecar files; the standard
manifest's policy/source-robot labels do not fully describe those overrides.
Comparator completion establishes its existing input-matching checks, not full
provenance validation for these experimental overrides. Do not promote these
runs to production evidence without materializing the actual controller,
derived collision meshes, parameters and source hashes in the normal contract.

New retained local probes:

- `runs/issue71-contact-model/deep_audit.py` and
  `deep-audit-replay-{stock,custom}.json`: 48 isolated drop cases per runtime and FK audit.
- `runs/issue71-contact-model/transport_isolation.py` and
  `transport-isolation.json`: three dynamics ablations.
- `runs/issue71-contact-model/static-load.json`: static gravity torques.

## Tracking gate and model audit implementation

The diagnostic implementation exposed 0–64 internal Bullet substeps. Final PR
packaging restricts `SimulationConfig.physics_substeps` to **zero only**, because
the experiments identified an inflated motor impulse budget at nonzero values.
Refine `timestep_s` instead. Historical nonzero-substep runs retain their executed
implementation snapshots; they are not valid fixed-torque convergence evidence.

Before opening at placement, `execute_trial` now checks the last 0.1 s of
**measured** grasp positions against the requested Cartesian destination and
measured joints against their commands. Defaults are 0.002 m and 0.02 rad,
respectively; these are explicit simulation policy tolerances, not calibration.
Missing/nonfinite measurements and insufficient window coverage fail closed.
The grasp point includes the configured offset transformed by measured TCP
orientation, rather than comparing the bare TCP or an IK target with itself.

A failed gate ends the attempt without release, home motion or retry, retains
the trajectory, and records `release_inhibited`, `motion_failure`, and measured
errors in `release_tracking`. The frozen benchmark failure vocabulary is
preserved: collision/timeout retain precedence, otherwise the failure is
`invalid_observation` with the specific tracking detail. This gate is not a
hardware emergency-stop or a guarantee of a stable held object.

The source-URDF mass audit totals **0.632006001 kg including the fixed base**;
link masses and inertial tensors are retained in
`runs/issue71-contact-model/workspace-load-audit-closer.json`. Finite differences
of gravitational potential energy agree with inverse dynamics within
3.2e-11 N·m across 14 checked poses. No unit conversion or patched-collider mass
change is needed to explain the baseline overload. These checks establish
internal model consistency, not measured correctness of its masses or motors.

Keeping the original 0.6 N·m limit, a candidate XY target `[0.18, -0.14]` m needs
0.394665 N·m at transport height 0.11 m and 0.465287 N·m at placement height
0.08 m. Both have at least 20% static headroom; IK position residuals are
0.196 mm and effectively zero. This is a **candidate first-cell pose only**,
not a validated tray relocation: full tray/fixture/robot clearance, path loads,
and all other cells remain unchecked. Production layout and motor limits remain
unchanged pending those checks or measured actuator data.

The immediate static layout check **rejects simply translating the existing
tray** to either `[0.18, -0.14]` or `[0.16, -0.14]`: its mesh intersects the
fixture's support pedestal. The first-cell torque calculation does not justify
adopting either layout. Preserve those rejected candidates in
`runs/issue71-contact-model/closer-tray-static-clearance.json`; a revised layout
must satisfy both full-geometry clearance and load constraints.

Eight focused release tests pass, including actual trial orchestration with a
synthetic missed-placement case proving no release command is issued and a
tracking case proving release remains possible. Synthetic tests are not
simulation task-success evidence.

The relevant source-enabled robot/simulation/comparison/margin suite passed
**75 tests** before adding the passing-release orchestration variant; all eight
release tests subsequently passed. The isolated custom runtime cannot collect
the full application suite because its environment lacks FastAPI (six collection
errors). Full-suite verification uses the preserved application/stock runtime.
That full-suite run completed with **406 passed, 40 skipped and 12 subtests
passed**; the source-enabled targeted suite above covers the relevant optional
robot/simulation tests separately.

### Narrow diagnostic IK correction

The initial integration sweep completed the zero-substep pair and demonstrated
the real release gate stopping the CAD nominal/repeat at placement. The nominal
window had maximum grasp error 0.025126 m and joint error 0.119853 rad.
The four-substep CAD attempt then aborted before descent: the measured wrist
angle was 1.6580600077823555 rad against a 1.65806 rad limit, causing SciPy to
reject its initial guess. This is a numerical optimizer-domain error, not proof
that finer integration cannot grasp.

The local `bounded_probe.py` wrapper projects only the IK warm start into the
existing joint bounds and records each projection. It does not reset/clamp the
executed robot state, relax joint limits, or change source geometry. A frozen
reproduction confirms the original solver raises, the bounded solver returns
within-limit arm commands, the input observation stays unchanged, and nonfinite
warm starts are rejected. The observed projection is 7.78236e-9 rad.

A fresh bounded 0/4/8/16 sweep is retained under
`runs/issue71-integration-convergence-bounded/`; original partial/failed runs
remain preserved. This is a bounded diagnostic to determine whether pickup is
integration-sensitive, not a new controller feature or successful-grasp claim.
After assessing these settings, prioritize source-support clearance and a
load/clearance-feasible task layout over more controller features or demo runs.

## Clearance and load-feasible transfer follow-up

A sampled source-triangle closure search varied only grasp Z offset over
2–4.25 mm, retaining the 1.2 mm support web and source robot geometry. Across
33 closure poses per offset, 2.75 mm first cleared the support (0.067 mm minimum),
3 mm gave 0.218 mm minimum, and 3.5 mm gave 0.584 mm minimum. These are sampled
commanded clearances, not a certified swept-volume bound or executed clearance.

At tray XY `[0.18, -0.14]`, changing yaw from 90° to 0° removes the tray/support
intersection, with 54.159 mm static separation. The first-cell target retains
the lower static load established above. The full tray schedule, home motion,
self-collision and all executed path clearances still require verification.

`runs/issue71-clearance-transport-smoke/` completed a paired six-attempt test with
3.5 mm offset, this closer zero-yaw tray, and the existing Cartesian waypoint
method extended to transport/place/retract. CAD nominal/control/repeat all
reported pickup misses without recorded unwanted contacts; reference attempts
failed collision. The CAD nominal had bilateral contact during closure but lost
it about 0.21 s into lift. Removing overlap did **not** establish reliable pickup.

### Internal-substep motor budget confound

The internal-substep campaign is **not a fixed-torque convergence experiment**.
The Bullet position-motor command converts force to maximum impulse using the
outer `m_physicsDeltaTime` (server source around line 7352), while the motor is
solved on each internal step. With unchanged API force=0.6, four/eight substeps
allow the previously infeasible extended pose to be held. Reported shoulder
motor torque becomes approximately 0.769/4 and 0.769/8 N·m, respectively.
Thus those API readings must not be interpreted as physical torque savings.

An isolated normalization check with API force `0.6 / substeps` restores the
original approximately 0.832 rad shoulder sag at four and eight substeps.
Evidence: `substep-motor-audit.json` and `substep-motor-normalized-audit.json`
under `runs/issue71-contact-model/`. The original unnormalized campaign remains
diagnostic evidence, not a convergence or improved-transport claim. The final
PR rejects nonzero `physics_substeps` until this mapping is corrected and tested.

The original unbounded campaign has now finished: zero substeps completed with
CAD nominal/repeat pickup followed by collision and inhibited release; four and
eight substeps aborted on the previously reproduced out-of-bounds IK warm start;
sixteen substeps completed with CAD nominal/repeat pickup but `wrong_cell`
placement failures. All reference attempts failed collision/pickup, and all CAD
open-gripper controls missed. The sixteen-substep results do not supersede the
torque diagnosis because their motor budget is confounded as described above.

The next paired probe uses **explicit 1/960 s timesteps with no internal
substeps**, preserving the declared 0.6 N·m API torque budget, and the sampled
source-clear 3 mm offset. It is retained at
`runs/issue71-clearance-transport-fine-smoke/`. That paired smoke has now
completed: CAD nominal and repeat both picked up and transported the seed with
**zero recorded unwanted collisions**, then failed placement (`wrong_cell`).
The open-gripper CAD control missed pickup. All reference attempts still failed
collision/pickup. Both tools' nominal/repeat state difference is exactly zero,
and their deliberate-failure checks passed. This remains a first-cell smoke,
not a complete benchmark schedule or full evidence-verifier claim.

The CAD nominal retained bilateral contact in all 1,920 lift samples and all
1,920 transport samples. Placement tracking passed over 97 samples spanning
0.1 s: maximum requested-grasp position error 1.191413 mm and maximum joint
error 0.004174 rad. The repeated run produced identical tracking metrics.
These results use explicit 960 Hz steps with no internal substeps and the
unchanged 0.6 N·m limit; they do not rely on the inflated substep motor budget.

Frozen checks of the **executed closure pose** against original source surfaces
give 0.908347 mm fixed-jaw/support clearance and 0.218750 mm moving-jaw/support
clearance. Split-tip Bullet distances are 0.899582 mm and 0.199442 mm,
respectively. The earlier moving-jaw overlap is absent at this checked pose.
The source check is retained as `clearance-fine-source-poses.json`.

After release, the seed reaches the target cup floor but drifts toward the wall;
final radial error is 13.555146 mm, and the complete settling-window checks fail.
No successful placement, full acceptance or physical readiness is claimed.
The immediate remaining task is release/settling accuracy, rather than another
increase in motor torque. Native fixture authoring and complete executed source
clearance validation remain prerequisites to promoting this local prototype.

A separate full-source-link
environment clearance/load audit samples lift, transfer, place, release and
retract. Its first execution exceeded the 200 s tool limit; a longer execution
is running. No result from that pending audit is claimed here.

### Original retained evidence

- `runs/issue71-baseline-20261029/verification-report.md`: prior commands/results.
- `runs/issue71-offset6-full-20261029/`: complete stock-runtime failed comparison,
  22 videos, trajectories, source hashes, OI replays and verifier manifests.
- `runs/issue71-contact-model/`: source archive, build logs, patch/wheel hashes,
  frozen-pose probes, tilted-pose failures and diagnostic wrapper source.
- `runs/issue71-margin10um-offset6-smoke/`: corrected-margin failed smoke.
- `runs/issue71-relief-prototype-smoke/`: failed, comparator-rejected prototype.

Local custom wheel SHA-256:
`7ff113a80d76755e2902017eace696c9be6b39aadec342fd25af6f0f055cbcc8`.
Build outputs may have different hashes; record each build's own identity.
Prior public textual findings: [#71 verification comment](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/71#issuecomment-6502575704).
Recordings, binary outputs and private runtime data are excluded from this change.
