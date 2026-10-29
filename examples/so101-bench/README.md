# SO-101 physical bench follow-up (#71)

**Status: blocked; no fabrication or physical trial has been executed.** This is
an operator handoff, not completion evidence. Keep #71 open until a physical
report, footage and measured model updates exist.

## Candidate decision before fabrication

The [#63 candidate](../so101-fixture/README.md) is available as a hash-recorded
CAD archive, but its seed-only fit check does not establish gripper clearance.
The [#66 comparison](../so101-comparison/README.md) recorded **0 pickups / 9,
0 accepted placements / 9 and 9 collision attempts / 9 for each tool**.
Its source-mesh diagnosis also found jaw/support interference at commanded
poses, independently of the unresolved Bullet collision-margin behavior.

Do not treat candidate-v1 as selected for successful powered pickup. First
revise the support geometry or grasp approach and repeat the matched comparison,
or explicitly limit a v1 fabrication to an unpowered dimensional/fit study.
Preserve v1 and its failures. A CAD revision must retain parent-bundle lineage;
a policy change must be applied to both candidates in a new matched campaign.
The simulated reference pocket also needs a fabrication-ready, dimensioned
artifact and its own inspection record before a physical comparison.

## Physical setup and release record

Copy [report-template.md](report-template.md) to a new local run directory.
Populate measurements with instrument, units, uncertainty and evidence references;
leave unknowns unknown. Never copy simulation defaults into measured fields.

1. Identify the actual robot, stock gripper, firmware, controller commit and
   calibration. Record hardware/source-model differences. Confirm a functioning
   arm and stop control with the operator; this repository supplies no verified
   hardware driver or calibrated motion program for this experiment.
2. Pin each tool's source, STEP/STL, bundle hash and revision. Record printer,
   material, orientation, slicer settings, actual print dimensions, surface finish
   and seat inspection. The proposed PLA/FDM process is an assumption, not a
   verified fit or material-suitability claim. Inspect the 2.8 mm seat mouth;
   export tolerances are not manufacturing tolerances.
3. Document measured bench fastening and fixture pose relative to the robot,
   tray geometry, home pose, camera calibration and the actual seed cultivar/lot
   and size distribution. Record transforms with direction, units and axes.
   Neither the model TCP nor source joint limits substitute for hardware calibration.
4. Document electrical requirements for the actual arm/controller. The passive
   fixture itself requires no power, air or vacuum; loading and reset are manual.
   Record any added utilities and mounting hardware rather than assuming them.
5. Inspect the complete intended gripper/support path without powered contact.
   Record minimum clearances, measurement uncertainty and photos. Unresolved
   interference or insecure mounting blocks powered trials. The operator must
   establish suitable hardware motion limits and stop behavior; simulation motor
   forces and gripper angles are not approved hardware settings.
6. Freeze the physical acceptance thresholds before running: radial tolerance,
   settling interval, timeout, substrate state and pre/post visible-damage method.
   Use the existing [benchmark](../so101-benchmark/manifest.json) physical rules:
   one whole seed inside the target below its rim, plus pre/post visible crack/
   crush inspection. Geometric placement alone is not accepted placement.
   Visibility that cannot resolve a rule yields unknown acceptance, not a pass.

## Matched execution

Use the existing nominal schedule: seeds `7, 19, 31`, each with targets
`(0,0), (2,5), (5,11)` in that order, nine attempts per candidate. These integers
identify protocol cases; they do not make physical seeds identical. Record actual
seed IDs, dimensions, lot, presentation pose and pairing/reset deviations. Freeze
the candidate order and all non-tool conditions before execution. A non-tool
change invalidates that comparison and requires a separately identified campaign.

Film the setup and every attempt with visible run/trial identity. Retain original
footage, timestamps and hashes; identify the calibration and seed-inspection images.
Start cycle timing at ready-before-pickup; end at acceptance decided and robot home
or failure stop. Time reset separately. Do not retry inside an attempt. Retain
failed attempts, early stops and incomplete schedules; reset failure aborts the
remaining schedule. Planned but unstarted attempts are not executed attempts.
Do not force a nine-attempt campaign through a known interference or unsafe state.

Record pickup, seed count, target placement, visible damage, collision observations,
failure reasons and evidence time ranges per attempt. Physical collisions may be
observed rather than sensor measured: describe the method and its limitations.
Do not transfer simulation's deliberate open-gripper control to hardware without
an operator-reviewed protocol; optional controls/repeats remain outside nominal
denominators. Nine scheduled cases are a smoke test, not a reliability study.

## Analysis and model revision

Report measured accepted / started nominal attempts, unknown-acceptance counts,
pickups, collision attempts and overlapping failure categories for each tool.
Retain all failed/aborted started attempts in denominators. Report cycle and reset
times separately, including failed-cycle times and the exact aggregation rule.
Incomplete or mismatched campaigns cannot establish a winner. Energy, labor,
cost and throughput stay unknown unless separately measured with a stated boundary.

Keep physical results and simulation results in separate columns, each linked to
its exact revision and evidence. Explain differences in shape, placement, friction,
calibration, contacts and seed variability before attributing performance changes
to tooling. Visible inspection cannot establish germination or biological viability.

For each model update, link the bench observation, measured value/uncertainty,
old assumption, new parameter/geometry and new revision. Rerun both simulated
candidates with matched settings, preserve the original results, and document
remaining discrepancies. A fitted model is not an independent validation: identify
which trials informed it and reserve fresh physical trials for any validation claim.

Keep raw recordings and completed local outputs out of git. Publish only evidence
whose permissions are verified. Link permitted footage/report artifacts and their
hashes from #71, and update parent #59 with actual evidence and remaining limits.
No automatic metric ingestion or physical-evidence validation is implemented here.
