# HA4M fastening concept

Human source: `runs/ha4m-fastening-clip-20261028/`, IDU004V001 action 12,
331 consecutive frames (11.033 seconds at nominal 30 FPS). Both the wide view and
close-up preserve the real workpiece. Source attribution: Cicirelli et al., HA4M,
Scientific Data 9, 745 (2022), CC BY 4.0.

## Geometry and evidence

The publisher MindBot Planetary Gearbox STEP, DOI `10.5281/zenodo.5675810`, is
separately licensed **CC BY-NC-SA 4.0**. `scripts/prepare_gearbox_asset.py` verifies
the retained source checksums and tessellates all 13 solids. Only a rigid pose,
millimeter-to-meter conversion and display colors are applied. It retains the
original STEP and license provenance with the scene asset. Identity with the
recorded hardware remains unverified; the CAD contains no screw solids.

The proposed machine holds the gearbox while a driver feeds, rotates, retracts,
traverses while raised, and repeats at a second proposed target. Two targets and
their tool-access coordinates are design assumptions informed by reference CAD,
not an observed screw count. `scripts/animate_fastening_concept.py` checks the
generated bit pose before adding explicitly authored motion. It does not replace
existing animation or source snapshots. Source gearbox vertices remain unchanged.
The 14-second presentation is not a measured machine cycle or validated fastening.

## Live run and recovery

- Twelve-frame Nebius extraction was rejected with HTTP 400. The cause was not
  established; the failed extraction is retained.
- A separately retained eight-frame request succeeded through Nebius observations
  and GMI protocol extraction. It identified support and perimeter tool manipulation,
  retaining uncertainty about tool engagement, torque and seating.
- v000013 generated a proposal, but its CAD build failed after native Boolean-union
  errors. Review also found that the model's proposal summary omitted the exact
  reference envelope and moving-body names from the CAD handoff.
- The reviewed continuation now appends protocol constraints verbatim to the CAD
  requirements, retaining the raw model proposal and hash-bound review metadata.
  `scripts/retry_reviewed_cad.py` appends a recovery snapshot reusing extraction and
  proposal, with fresh CAD authoring. It does not change the failed snapshot.
- Offline suite after this handoff correction: **281 passed, 4 skipped,
  12 subtests passed**. Regression checks cover unchanged source mesh, raised-only
  traverse, bounded rotation interpolation, incompatible tool-pose rejection and
  preservation of exact reviewed requirements through the handoff.

## Completed local presentation

- v000014 successfully built native station CAD, scene and lab after the handoff fix.
- v000015 retained an export failure caused by an incorrect native animation track ID.
  The ID contract was corrected; v000016 exported the first full motion sequence.
- **v000017** adds display contrast and two separately authored socket-head fasteners.
  These are illustrative hardware additions, not source STEP solids. Head dimensions,
  socket size, target locations and rotation are assumed; no thread advance or torque
  physics is modeled. The publisher gearbox's thirteen mesh parts remain unchanged.
- The 14-second video shows feed, rotation, retract, raised traverse, second feed,
  rotation and final retract. Native frames were inspected at both targets and during
  traverse. Both videos played in the final workbench tab. **182 indexed artifacts**
  passed checksum verification; browser import restored 180 workbench artifacts.
- No new live visual critique was run on the recovered presentation. Its inherited
  lab was generated before reference geometry and authored motion were added.

Open `http://127.0.0.1:8000/#5570c4117f2c4027aeccf149bebd67d7` → final tab.
Portable local snapshot: `snapshots/e2e/v000017`.
Convenient video copies and attribution: `runs/ha4m-fastening-demo-20261028/`.
Output video: `automated-fastening.mp4`; input: `human-fastening-closeup.mp4`.
Screenshot: `.playwright-mcp/ha4m-fastening-v17-side-by-side.png`.

No physical execution, fit certification, torque acceptance or ROI is established.
Next: user review of this geometry-preserving fastening concept.
