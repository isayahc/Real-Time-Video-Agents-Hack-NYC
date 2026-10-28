# HA4M block joining: evidence and fixture hypothesis FJ-01

**Decision:** investigate an **open, rotation-permitting mating guide** around the
existing lower-block support. It would aim to limit lateral offset/tilt while
preserving access to the center and allowing the operator to adjust gear phase.
This is a proposed experiment, not a validated fixture, simulated result or savings claim.

**Geometry follow-up:** [original-CAD audit](ha4m-geometry-audit.md) rejects the
tested full collar and finds limited discrete clearance for open arcs. It does
not establish continuous rotational freedom, support fit or human-hand access.

## What was inspected

Same ten trials as the [recorded baseline](ha4m-small-sample.md). Rebuilt action-9
intervals from checksum-verified publisher labels and RGB indexes. Downloaded
**110 original PNGs**: nine evenly spaced in-action frames plus the immediately
preceding/following frame for each trial. No additional participants or recordings.
All ten cropped contact sheets were visually inspected by the assistant in this
session; the original full-resolution frame `IDU005V001/002884.png` was also
inspected. Full-scene sheets and original PNGs are retained for further review.

Local evidence: `runs/ha4m-joining-inspection-20261028/manifest.json` and
`<recording_id>/joining-crop.jpg`, `joining-full.jpg`, `<frame_id>.png`.
The manifest retains exact source paths, frame IDs, device timestamps and hashes.
Contact-sheet time is **relative to action-9 start**, not recording start. The
first/last context images are outside the action's half-open interval even though
the sheet heading says `action9`; the manifest's interval is authoritative.

The authors' exploded component figure was also reviewed as **design context**:
`https://baltig.cnr.it/ISP/ha4m/-/raw/master/Figs/Fig1.png`, retained with a hash in
`runs/ha4m-joining-reference-20261028/`. It identifies the ring, sun/planet gears,
shafts, carrier, cover and fasteners. It does not establish observed contact forces,
tolerances, dimensions or an error mechanism in these recordings.

## Interval evidence ledger

Times below are publisher label-frame counts / 30 FPS; source device durations
agree within about 12 microseconds for these action-9 intervals. `fN` references
the original RGB frame ID. Notes describe selected snapshots, not continuous motion.

| Trial | Action-9 frames `[start, end)` | Duration | Visible evidence in inspected samples |
| --- | --- | ---: | --- |
| IDU001V001 | [1221, 1474) | 8.43 s | Upper block held above lower at f1284; overlapping at f1315; hand locations differ between rim and center at f1347/f1410/f1441. |
| IDU002V001 | [1740, 2224) | 16.13 s | Upper block lifted at f1800; blocks overlap at f1861; fingers at openings and outer edge at f1921/f1982/f2042; edge grip at f2163. |
| IDU003V001 | [1682, 2461) | 25.97 s | Blocks overlap at f1779; two-handed rim holding at f1876/f1974/f2168; fingers at central region at f2266/f2363. |
| IDU004V001 | [1203, 2021) | 27.27 s | Blocks overlap at f1305; fingers at central region at f1407; rim grips at f1509/f1611/f1714; hand on center and outer edge at f1918. |
| IDU005V001 | [2066, 3157) | 36.37 s | Blocks overlap at f2202; hand positions at center/rim vary at f2338/f2475/f2611; hands withdrawn from assembly at f2884, back on it at f3020. No recovery event is established from this gap. |
| IDU006V001 | [1527, 3482) | 65.17 s | Blocks overlap at f1771 (+8.13 s); one hand at central opening and another at rim in f2015/f2260/f2504/f2748/f2993/f3237 (+16.27 to +57.00 s). Final edge grip at f3481. |
| IDU007V001 | [1461, 1799) | 11.27 s | Transfer visible at f1503; overlapping blocks at f1545; center/edge hand contact at f1587/f1629; hands clear at f1756, edge grip again at f1798. |
| IDU008V001 | [1881, 3305) | 47.47 s | Blocks overlap at f2059 (+5.93 s); central/edge hand positions at f2237/f2415/f2593; rim holding at f2770/f2948, central hand at f3126 (+41.50 s). |
| IDU009V001 | [1663, 2262) | 19.97 s | Blocks overlap at f1738; central/edge hand positions at f1813/f1887/f1962; rim grip at f2037/f2186; head close to assembly at f2261. |
| IDU010V001 | [1937, 2631) | 23.13 s | Upper block held above lower at f2024; overlapping at f2110; fingers in central region at f2197/f2283; rim contact at f2370/f2543. Head/hair obscure part of mating area. |

Across these ten action intervals: **mean 28.12 s, median 24.55 s, range
8.43–65.17 s**. This variability is descriptive. The fastest participant is not
a demonstrated achievable fixture target or a counterfactual for slower trials.

### Observed vs inferred

- **Observed in sampled images:** initially separate subassemblies; upper-block
  transfer; later overlapping blocks with hands on outer and central regions;
  changing hand positions and intermittent occlusion. The recordings already use
  assembly supports; compare against that baseline, not an invented unsupported task.
- **Suggested mechanism:** maintaining alignment while manipulating the center
  may occupy both hands. The exploded geometry makes gear engagement/phase a
  plausible contributor. Neither misalignment nor tooth interference is verified.
- **Not established:** exact first contact, seating depth, retry count, force,
  uninterrupted adjustment duration, correctly meshed teeth, accepted fit or defect
  rate. The images cannot partition the whole action into measured grasp/align/
  insert/recover durations. A long labeled interval is not automatically rework.

## Fixture hypothesis FJ-01

**H1:** a guide that reduces unwanted lateral/tilt motion while preserving needed
rotation and center access reduces mating/repositioning work enough to offset its
own handling overhead, with equivalent accepted output.

### Proposed arrangement

1. **Locate the existing lower support**, preferably with an adapter to its known
   nonfunctional surfaces. Keep the existing upstream assembly sequence as the
   baseline. Establish whether the support already provides adequate restraint.
2. Add a **split/open-sided external lead-in guide** for a verified outer datum of
   block 2. Limit lateral displacement and tilt during approach without using gear
   teeth, bearings or shafts as clamping surfaces.
3. Preserve **axial lift-off and controlled rotational adjustment** of the mating
   assembly and/or accessible shaft, as the actual gear kinematics require.
   Do not rigidly key both subassemblies until the required rotation is understood.
4. Leave the **central openings, rim grip areas and sight line accessible**. Avoid
   a bridge directly over the area where fingers appear in the inspected frames.
   A guide that blocks those contacts could increase time rather than reduce it.
5. Permit withdrawal and straightforward unloading. Check interference with cover
   placement and screw access in actions 10–12, not merely with action 9.

This specifies functions, not fabrication geometry. **Dimensions, clearances,
lead-in angle, allowed rotation, compliance, material and force limits are unresolved.**
The next CAD step needs original part/support geometry or independently sourced
dimensions; perspective RGB images do not supply trustworthy millimeter tolerances.

### Competing explanations and controls

| Candidate/control | What it tests | What could defeat it |
| --- | --- | --- |
| Existing supports, unchanged | Actual baseline | Participant/learning variation makes unmatched comparisons misleading |
| Lower-support locator only | Whether base stability is the main problem | Baseline support is already stable; extra locating adds overhead |
| Locator + open mating guide (FJ-01) | Whether coaxial/tilt guidance helps | Gear phase dominates, guide overconstrains rotation, or obscures the working area |
| Handling/orientation instruction only | Whether sequence or grip explains long intervals | Instructions do not resolve mechanical interference |

A screw presenter targets a different labeled action. Keep it as a separate
candidate rather than crediting its possible benefits to this joining guide.

## Falsifiable evaluation contract

**First, an offline geometry/access check:** obtain the actual mating/support
geometry; identify valid contact datums, required rotation and existing support
constraints; evaluate guide clearance and hand/tool access. A CAD clearance pass
would establish only geometric plausibility, not reduced cycle time or quality.

**Then, if an intervention is tested:** compare the controls above under the same
start/end boundary, parts and acceptance specification. Counterbalance condition
order within participants and retain individual trials; do not compare only the
slowest baseline person with the fastest fixture person. Freeze the hypothesis
and thresholds before a new evaluation set. These ten trials are exploratory.

Record:
- Time from reach for the ready block through confirmed seating/release; separately
  record fixture loading/unloading, support changes, recovery and downstream delays.
- First approach and each withdrawal/re-approach under a precise event definition;
  use sufficiently dense observations, not counts guessed from these contact sheets.
- Observable lateral/tilt deviations, access obstruction and added handling actions.
- Independently checked seating, assembly completeness, gear motion/binding and
  damage, with numerical tolerances from a verified specification. Current limits
  and acceptance results are **unknown**.

**Pass logic:** equivalent accepted output plus positive net whole-boundary time
benefit including setup allocation, loading/unloading and downstream effects.
Reject or revise FJ-01 if it obstructs adjustment, increases errors, or any apparent
action-9 gain is consumed elsewhere. Acceptance or timing gaps mean **undetermined**.

No predicted cycle time, percent reduction, unit cost, payback or ROI is supplied.
When sourced outcomes exist, feed them to the existing resource/alternatives and
prediction/outcome evaluators; retain their acceptance/equivalence gates.

## Reproduce and verification

```powershell
python scripts/inspect_ha4m_joining.py --input runs/ha4m-ten-20261028 --output runs/ha4m-joining-new
```

Requires Pillow and the existing Python dependencies. New output directory required.
The script checks source hashes before fetching, limits requests to eleven images
per each of the same ten trials, caps each PNG at 10 MiB and total planned PNG data
at 500 MiB, decodes every original PNG, and records hashes for original and derivative
images. The original baseline package is unchanged. Source media remain local.

Independent verification rechecked and decoded **110 original PNGs (367,008,238
bytes) and 20 contact sheets**. The source manifest hash is unchanged. Results are
retained in the inspection directory's `verification.json`.

Full offline suite: **266 passed, 4 skipped, 12 subtests passed**. No paid provider
calls, fixture simulation, native CAD generation or physical intervention test was
performed. **Quality acceptance and intervention savings remain unverified.**
