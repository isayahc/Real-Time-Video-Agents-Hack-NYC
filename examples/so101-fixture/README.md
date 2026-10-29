# SO-101 seed-presentation fixture

Issue #63's first CAD candidate is a passive, manually loaded seed seat. It
implements the fixed presentation pocket assumed by the [benchmark](../so101-benchmark/README.md)
while keeping the [SO-101 robot and stock gripper](../so101-robot/README.md) unchanged.
It is deterministic parametric OpenCAD authoring, not a live model-provider result.

## Geometry and declared target

All dimensions are authored assumptions in **millimetres**, right-handed **Z-up**.
The origin is the centre of the base's bottom face. The 40 × 30 × 4 mm base carries
an 8 mm diameter, 8 mm high pedestal. Its top is at z=12 mm. A 45° conical seat has
a 1.4 mm mouth radius and a 0.14 mm flat floor radius (the truncated apex avoids
degenerate STL triangles). The sole target is the benchmark's **ideal 3 mm sphere**.
The seed centre is at z=12.72132034356 mm; the equator is 0.72132034356 mm above the rim.

For radius `r`, rim height `h`, and mouth radius `a`, the seed-centre height is
`h - a + r*sqrt(2)`. This locates tangency to the conical wall. The builder checks
that contact is inside the seat and the equator is exposed. Geometry checks reopen
actual STEP and STL exports; bounding-box proximity alone does not establish fit.

The generated `machine.py` is self-contained parametric OpenCAD source with named
dimensions and a documented builder. `machine.tree.json` retains its feature history.
`machine-bodies.json` uses the existing apparatus adapter's component identity and
native mesh format for downstream Forma consumers. Only the fixture is exported;
cutters and reference seeds are excluded.

## Reproduce

Use Python 3.12 and the pinned OpenCAD source revision used in CI:

```sh
python -m pip install -e '.[test,robot,fixture]'
git clone https://github.com/caid-technologies/OpenCAD.git runs/opencad-runtime
git -C runs/opencad-runtime checkout 5cf1a47dda7b80fc6b5ac47a9f60f8d6030dba0f
python -m pip install --no-deps -e runs/opencad-runtime/packages/opencad
python -m protocol_pipeline.robot_contract \
  --lock examples/so101-robot/source-lock.json --source-root runs/so101-source --fetch
python -m protocol_pipeline.seed_fixture \
  --spec examples/so101-fixture/spec.json \
  --benchmark examples/so101-benchmark/manifest.json \
  --robot-contract examples/so101-robot/robot-contract.json \
  --lock examples/so101-robot/source-lock.json \
  --source-root runs/so101-source --output runs/so101-fixture
SO101_FIXTURE_NATIVE_TESTS=1 SO101_SOURCE_ROOT="$PWD/runs/so101-source" \
  python -m pytest -q tests/test_seed_fixture.py tests/test_opencad_program.py
```

The output directory must be new. The native worker uses the existing bounded
`CadProgram` exporter, with mandatory OCCT (no analytic fallback), a 180-second
subprocess limit, native STEP round-trip checks and provider credentials omitted.
The default Forma adapter remains available for its existing callers.

The committed [candidate-v1.zip](candidate-v1.zip) preserves the exact local bundle.
Extract it into a directory and run `verify_bundle` below to repeat the fit checks.
[assembly.py](assembly.py) is its readable parametric source.

The `so101-native-fixture` CI artifact contains the executable source, STEP, STL,
feature tree, native body mesh, interfaces, pinned robot contract, fit report and
`bundle.json` hashes. Artifacts expire after 14 days; the source and pinned inputs
remain in git. `executed-fit-report.json` and `executed-bundle.json` retain the
local executed evidence and exact artifact hashes. STEP writer timestamps and
feature IDs can change bytes between builds; each run records its own exact hashes.
Do not substitute a previous run's hashes for new output.

To verify an intact downloaded bundle and repeat its geometry checks:

```python
from pathlib import Path
from protocol_pipeline.seed_fixture import verify_bundle
report = verify_bundle(Path('runs/so101-fixture'))
```

## Interfaces and revision lineage

`interfaces.json` supplies the fixture-to-bench and fixture-to-seed matrices in
OpenCAD Z-up/mm and OI Y-up/metres using #61's shared conversion. Matrices map child
coordinates into their named parent frame. The bench datum is the planar underside.
The robot-base-to-fixture transform is **null** until calibration. A seed target is
not a robot TCP: `attachment_tcp` and `robot_mount` are null, and the unmodified
upstream robot TCP is retained separately. No bolt pattern or physical wrist
interface is invented. Robot source hashes are verified before and after generation.

`spec.json` pins the benchmark and robot contract by SHA-256. The root candidate
is `so101-seed-seat`, revision 1. A subsequent revision must increment the revision,
reference its predecessor's exact `bundle.json` SHA-256, and supply that file via
`--parent-bundle`. The predecessor is copied into the new bundle. Tests build a
44 mm base revision to exercise that lineage rather than merely checking a schema.

Use the same presentation fixture for the stock-gripper baseline and future pickup
candidates. Freeze its pose and revision in the environment artifact of both trial
manifests. A fixture or placement change requires a new matched comparison; this
CAD result does not make #60's definition-only manifests executable.

## Executed checks and evidence boundaries

The local run loaded the pinned SO-101 model and built a valid 5,199.253 mm³ OCCT
solid. Reopened STEP bounds are `[-20,-15,0]` to `[20,15,12]` mm. The STL is watertight
with consistent winding and positive volume. The fit report records:

- Zero seed/fixture interference and surface tangency at the declared seed centre.
- Positive intersection after a 0.05 mm downward probe, establishing geometric support.
- Zero interference over the complete 10 mm upward sphere sweep.
- Agreement of the STL contact ring with the analytic seat within 0.02 mm, plus
  STEP/STL bounds and volume checks. This threshold is export fidelity, not a print tolerance.
- CAD-derived interface transforms and unchanged pinned robot geometry.

Regression tests reject a missing seat, a filled STL seat despite almost identical
whole-part volume, shifted STEP, metre-scaled STL, incorrect target transforms,
changed inputs, modified artifacts and missing revision parents.

**Unverified:** stock-gripper finger clearance, grip force, damage, seed variability,
friction, reachability, workcell collision, stable bench attachment and pickup success.
The lift envelope belongs to the seed alone; it is not a swept robot/gripper envelope.
No dynamics simulation, live provider, GR00T, Nebius job, robot motion, fabrication
or physical seed trial was performed. The geometric pass applies only to the declared
idealized seed target.

## Fabrication and utilities

Candidate process: FDM in assumed PLA, flat base down. Actual printer, layer height,
shrinkage, surface finish, dimensional tolerance and seed-contact material suitability
are unknown. The small seat must be inspected and measured before any physical claim.
Secure the external base with a measured clamp or adhesive setup and calibrate its pose;
neither bench fastening nor load capacity has been validated.

The fixture needs no electricity, vacuum or pneumatics. Loading and reset are manual.
A pickup attachment is deferred because #61 has no verified wrist fasteners, payload
or vacuum/control interface, and this work has no evidence that a new attachment is
needed. Tray locators are likewise deferred until external tray dimensions are measured;
the benchmark defines cell geometry, not a tray outer rim.
