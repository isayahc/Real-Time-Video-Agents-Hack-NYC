# SO-101 follower: source model and shared tool interface

Implements issue #61, consuming the benchmark from #60. The robot is the actual
TheRobotStudio **SO-101 follower, new calibration**, not a generated approximation
or the SO-100. This milestone verifies model loading, joints, forward kinematics,
coordinate conversions and a reference attachment's frame alignment. It does not
execute a seed-placement task or establish physical attachment compatibility.

## Attribution and immutable inputs

- Upstream: [TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100)
- Revision: [`a758567c3978dfeefe282ede0500085a48fe8f78`](https://github.com/TheRobotStudio/SO-ARM100/tree/a758567c3978dfeefe282ede0500085a48fe8f78)
- Model: [`Simulation/SO101/so101_new_calib.urdf`](https://github.com/TheRobotStudio/SO-ARM100/blob/a758567c3978dfeefe282ede0500085a48fe8f78/Simulation/SO101/so101_new_calib.urdf)
- [Upstream model documentation](https://github.com/TheRobotStudio/SO-ARM100/blob/a758567c3978dfeefe282ede0500085a48fe8f78/Simulation/SO101/README.md)
- License: Apache-2.0, retained in [UPSTREAM-LICENSE](UPSTREAM-LICENSE).

The source model credits TheRobotStudio and its Onshape/onshape-to-robot design
lineage. No upstream robot geometry is modified. `source-lock.json` pins the exact
URDF, all 13 referenced STL files, upstream README and LICENSE with SHA-256 and byte
counts. Source files are fetched explicitly or read from an existing checkout;
the build itself is offline. Exported bundles include the complete pinned source
subset and upstream license. This project's importer is MPL-2.0; that license does
not replace the upstream assets' Apache-2.0 terms.

## Reproduce

```bash
python -m pip install -e '.[robot,test]'
python -m protocol_pipeline.robot_contract \
  --lock examples/so101-robot/source-lock.json \
  --source-root runs/so101-source --fetch

SO101_SOURCE_ROOT="$PWD/runs/so101-source" python -m pytest tests/test_robot_contract.py -q

python -m protocol_pipeline.robot_contract \
  --lock examples/so101-robot/source-lock.json \
  --source-root runs/so101-source \
  --contract examples/so101-robot/robot-contract.json \
  --benchmark examples/so101-benchmark/manifest.json \
  --output runs/so101-import
```

An existing source checkout can replace `runs/so101-source` if all locked bytes
match. `--fetch` only requests immutable public URLs from the named upstream.
Modified cache files are rejected, never overwritten. Outputs must be new paths.
No hardware, provider credentials, paid inference or server is used.
The robot extra pins yourdfpy, trimesh and NumPy to the exercised versions;
yourdfpy 0.0.58's array-to-scalar conversion is incompatible with newer NumPy.

The bundle contains:

| Artifact | Purpose |
| --- | --- |
| `robot-contract.json` | Shared typed SI contract: identities, joints/limits/origins, reference poses, TCP/mount, unknown constraints |
| `source-lock.json`, `upstream/` | Exact reproducible model dependency closure and license |
| `model-report.json` | Executed load/FK, geometry bounds, model mass and frame-alignment evidence |
| `robot-with-reference.glb` | Actual robot meshes and magenta reference attachment at the declared pose |
| `robot.forma.json` | The same transformed meshes in Forma/OpenCAD millimetres, suitable for native OI import |
| `benchmark-manifest.json` | A new #60-compatible bundle binding the materialized robot contract |
| `benchmark-validation.json` | Benchmark validation; missing policy/evaluator/calibration still block execution |

The original frozen benchmark fixture is unchanged. Only its robot identity is
materialized in the exported copy. Source-model q=0 is not measured physical home
calibration, so its calibration and other unresolved identities remain definition-only.

## Joint and frame semantics

The contract uses metres, radians, kilograms, right-handed frames and Z-up.
Matrices are row-major arrays applied to column vectors:
`p_parent = T_parent_frame @ p_frame`. The reference pose is **q=0 radians** for
all six joints under upstream new calibration. This is a chosen model test pose,
not a claim about physical homing, collision clearance or servo encoder zero.

| Actuated joint | Lower / upper (radians, source model) |
| --- | --- |
| `shoulder_pan` | -1.91986 / 1.91986 |
| `shoulder_lift` | -1.74533 / 1.74533 |
| `elbow_flex` | -1.69 / 1.69 |
| `wrist_flex` | -1.65806 / 1.65806 |
| `wrist_roll` | -2.74385 / 2.84121 |
| `gripper` | -0.174533 / 1.74533 |

These numbers come directly from the pinned URDF's `<limit>` elements. The model
also declares effort/velocity values; these remain explicitly model-only and are
not used to infer payload, safe working loads or physical motor ratings.

`gripper_frame_joint` is fixed from `gripper_link` to `gripper_frame_link`.
Its source translation is `[-0.0079, -0.000218121, -0.0981274]` metres and its
source RPY is `[0, 3.14159, 0]` radians. Preserve the actual source rotation, rather
than replacing its rounded pi with an exact pi. The loader compares every joint,
limit, origin and declared reference-link transform against yourdfpy's loaded model.
Tests additionally compose the exported chain at multiple poses, including limits.

The `gripper` is revolute in the URDF. Upstream documents that LeRobot's `0..100`
gripper convention is not represented by this URDF. No implicit linear mapping,
degrees-to-radians guess or hardware action adapter is supplied.

## Mounting geometry and reference attachment

The complete stock `gripper_link` visual geometry and moving jaw are loaded from
their source meshes. The executed report includes fixed-body bounds in
`gripper_link` coordinates; these are computed model bounds, not measured bolt
locations or fabrication tolerances.

V1's **virtual mount** coincides with the upstream TCP frame. A magenta rectangular
marker, 4 × 6 × 20 mm, is the reference attachment. Its local mating frame has a
90-degree Z rotation and a -10 mm Z translation. These dimensions and offsets are
authored test geometry; they are not a proposed pickup tool. Placement solves:

`T_base_attachment = T_base_mount @ inverse(T_attachment_mating)`

The test requires coincident mating/mount frames under multiple robot poses. This
proves frame composition and import alignment, not physical fastening, collision
clearance, reachability or seed handling. Fabricatable tooling remains #63.

## OpenCAD/Forma and OI consumers

Both use the same contract and hash. `consumer_frames()` supplies the exact frame
in CAD Z-up millimetres and OI Y-up metres. CAD translations are multiplied by
1000; rotations are unchanged. OI coordinates map `(x,y,z)` to `(x,z,-y)` and frame
rotations use a change of basis on both sides of the matrix. Mesh vertices are
transformed from URDF link-local coordinates before export; no generic boxes
substitute for robot geometry.

OI's `importForm` recenters assets. The bridge restores `asset.originOffset` as the
scene item position, preserving the original robot base/TCP coordinates. It then
round-trips the portable scene and compares **every vertex and face** against the
source export, including the reference attachment.

With a compatible Open-Industries checkout and its npm dependencies installed:

```bash
node --import "$OPENINDUSTRIES_ROOT/node_modules/tsx/dist/loader.mjs" \
  protocol_pipeline/robot_oi_bridge.mts "$OPENINDUSTRIES_ROOT" runs/so101-import
```

This adds `robot.oi.json` and `oi-report.json`. The executed reference uses
Open-Industries commit `9b34ec217563e2a6788d5e60d9cc74c0bcd21330`; CI pins that
same importer. OI is used for static scene import here; #64 selects and integrates
the task/contact evaluation backend. OpenCAD tool authoring consumes the contract
in #63; this milestone does not claim a fabricated CAD attachment.

## Unverified physical constraints

Mounting hole diameter/spacing, payload, allowable tool mass, installed supply
voltage/current and vacuum pressure are null with `basis=unknown`. An unmeasured
specification cannot contain a number, and a model value cannot be labeled as a
physical measurement. No vacuum pump, flow capacity, valve or control interface
is provided by the model. The installed hardware variant must be checked before
choosing electrical constraints. `require_physical_attachment()` always rejects
this virtual-mount contract; adding a guessed payload cannot bypass that boundary.

The upstream README mentions removed base collision meshes, while the pinned
URDF contains base collision elements. The report records what was actually
loaded: 17 source collision elements grouped into seven link-level collision
geometries by yourdfpy. Their presence does not establish collision fidelity.
No dynamics/contact, payload, fabrication fit, provider execution or physical
performance is validated by this import.

## Executed evidence

`executed-model-report.json` and `executed-oi-report.json` were generated by the
commands above. CI reruns the Python 3.11/3.12 suites, generates a fresh complete
bundle, verifies native OI import on Python 3.12's job, and archives the model,
portable scene and reports. Pure contract tests can run without source assets;
real model checks require `SO101_SOURCE_ROOT`. CI always sets it, so missing or
changed assets fail rather than skip.
