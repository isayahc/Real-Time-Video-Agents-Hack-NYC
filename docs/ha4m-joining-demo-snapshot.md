# Human joining → proposed machine: v000012 presentation snapshot

## Open

Import `snapshots/e2e/v000012` into the workbench and select the final tab.
Local imported run: `http://127.0.0.1:8000/#e6af3d765f664f84894c96107fc81e37`.

- Left: continuous HA4M human-task workspace crop, 8.433 seconds.
- Right: 10-second **assistant-authored concept animation** of the freshly generated
  station, using colored upper/lower proxy parts. It shows approach, acquisition,
  lift, transfer, lowering onto the supported lower proxy, release and retraction.
- The two clocks are independent. Neither is a measured autonomous cycle time.

## Generation and review lineage

1. Cropped-source live extraction recovered two distinct blocks and a joining action.
2. Explicit assistant review corrected upper-transfer/lower-support roles and removed
   guessed lobe count from the design constraints. Raw extraction remains retained.
3. User-approved v000011 generated a new integrated transfer/joining station through
   GMI/OpenCode/native CAD, scene, visual critique and lab. All 220 artifacts verify.
4. The proposed visual correction moved the machine out of matched camera views and
   was rejected (`kept_original`). Baseline critique was 75; rejected candidate 15.
   The summary contains the rejected candidate critique, not a claim that the retained
   scene is empty. The retained machine is visible in the exported video.
5. v000011 had no animation tracks: its MP4 was a static CAD view. v000012 therefore
   adds authored native part tracks and two **assumed-size annular proxies**, preserving
   the original generated station mesh vertices. No further inference calls.

## Evidence boundaries

This is a **reviewed, assisted concept demonstration**, not fully automatic motion
generation or verified robot operation. Proxy dimensions do not reproduce the
original HA4M gear-train CAD. Carriage/gripper travel, grasp offsets, release and
timing were authored to explain the proposed sequence, without collision or fit
validation. Actual gear engagement, safe force control, tolerances and savings are
unverified. Source CAD is not replaced or represented as dimensionally matched.

The lab and model critique artifacts in v000012 are inherited from v000011; they
do not validate the newly authored animation. Historical snapshots remain unchanged.
Source attribution: Cicirelli et al., HA4M, Scientific Data 9, 745 (2022), CC BY 4.0.
Crop/encoding and all review interventions are recorded in retained provenance.

## Verification

- v000012: **227 indexed artifacts** pass snapshot checksum verification.
- Browser imported 225 workbench artifacts; both videos played with readyState 4
  (source width 634, machine width 960).
- Four native video samples at 2.6, 4.2, 6.4 and 9 seconds were visually inspected:
  pickup, transfer, lowered pair and released upper proxy are visible.
- Local evidence: `runs/ha4m-v12-review/sequence.jpg` and
  `.playwright-mcp/ha4m-v12-side-by-side.png`.
- Full offline suite: **278 passed, 4 skipped, 12 subtests passed**.
- New tooling: `scripts/animate_joining_concept.py`; it refuses incompatible body
  names/nest coordinates and appends a separate snapshot instead of altering source.

Next: review this specific side-by-side concept with the user. No further model
generation is needed merely to open or present it.
