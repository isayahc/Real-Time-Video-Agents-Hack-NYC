# FJ-01: original CAD and offline envelope audit

## Decision

Reject the tested full collar. Retain open arcs as a **geometry hypothesis**, with
rotation clearance an explicit unresolved requirement. No fabrication-ready fixture,
physical validation, accepted-output result or intervention savings is established.

## Source and coverage

HA4M paper reference 44 identifies **MindBot Planetary Gearbox**, by Davide Felice
Redaelli, Fabio Alexander Storm and Giulia Fioretta:
[Zenodo DOI 10.5281/zenodo.5675810](https://doi.org/10.5281/zenodo.5675810).
Its **CC BY-NC-SA 4.0** license is separate from HA4M's CC BY 4.0 dataset license.
Source geometry and rendered derivatives remain in ignored local run directories.

Downloaded `STEP_Gearbox_nominali.zip`: 1,820,298 bytes; publisher MD5 verified as
`3cad8e4dc058535a8f06a0718299407f`. SHA-256:
`943379d835bbf893829113c30754ae805132f608b7f1cdeb4421d5fe2c91180f`.
The audit rechecks every file against `source-manifest.json` before importing it.
All 13 STEP files declare millimeters and import as valid native shapes. The full
assembly contains 13 solids; it does not supply separate screw solids.

Relevant source dimensions (nominal CAD, not measured recorded hardware):

| Component | Envelope / features in standalone coordinates |
| --- | --- |
| Ring | 176 × 145 × 37.5 mm; circular outer radius 72.5 mm; tabs extend to x ±88 mm |
| Carrier | 97.5 × 107.942 × 25.5 mm; three raised posts |
| Support 14 | 60 × 80 × 18 mm; publisher identifies sun-shaft positioning purpose |
| Support pin 15 | 5 × 10 × 30 mm |

`Assem_SunShaft-Support.STEP` has two solids, corresponding by volume to support 14
and the sun shaft. It is not a verified model of the lower carrier support visible
in action 9. Exact source-CAD/recorded-part identity remains unverified.

## Method and assumptions

Native CadQuery/OCCT intersections and minimum distances, not image measurements.
Assembly coordinates are normalized by `xL=88-zG`, `yL=xG-20`, `zL=22.5-yG`.
The normalized assembly ring overlaps the entire standalone ring volume; its
volume exceeds the standalone ring by **1.00494 mm³**. Thus registration is close,
but the two exports are not geometrically identical. Source placements are retained
unchanged; the transform is only applied in the review worker.

Both hypothetical guides occupy radii **73.5–78.5 mm**, z **0–12.5 mm**:
- Full collar: 360°.
- Open arcs: 45–135° and 225–315°, leaving two 90° angular windows near the tabs.

These are exploratory envelope dimensions, not sourced tolerances. There is no
lead-in, base, attachment, compliance or support adapter. A 1 mm radial gap would
allow lateral play; effectiveness at limiting tilt has not been tested.

Each guide was tested against the assembly's ring at rotations −45, −30, −15, 0,
+15, +30, +45 degrees and axial offsets −20, 0, +20 mm: **42 discrete checks**.
Positive intersection volume above 0.00001 mm³ is classified as a collision.
Additionally, each guide was checked separately against all 13 assembly solids at
the publisher's nominal assembled pose: **26 component checks**.
Rotating the whole ring is an envelope probe, not simulated geared-assembly motion.

## Results

| Guide | Ring checks | Nominal assembly |
| --- | --- | --- |
| Full collar | Collision at all 21 poses | Ring overlap 4,940.342 mm³; other solids no positive overlap |
| Open arcs | Clear at −15°, 0°, +15° for all three axial offsets (9 poses); collision at ±30° and ±45° (12 poses) | No positive overlap with any of the 13 solids |

For clear open-arc poses, minimum distance is **1.000 mm** at axial offsets −20/0
and **7.566 mm** at +20 mm. At nominal axial position, overlap is **16.454 mm³**
at ±30° and **2,470.171 mm³** at ±45°. These discrete results do **not** certify
a continuous ±15° motion range, full withdrawal, tolerance robustness, lateral
offset/tilt clearance or a valid assembly sequence.

The rendered source assembly and orange envelopes were visually inspected.
Open arcs preserve an unobstructed central region and two angular windows in the
guide itself. Those windows contain part features and are **not** proof of human
finger/hand clearance, grip comfort, sight lines or tool approach. No hand envelope
or tool model was supplied. Publisher final-assembly orientation has not been
registered to the action-9 video, so local z is not an established insertion or
gravity direction. Cover/screw installation paths remain unchecked.

## Revised requirements and next smallest action

1. Confirm which part/support and orientation correspond to the recorded lower
   block before designing a locating adapter.
2. Establish the required adjustment: rotating a shaft, ring or entire block are
   distinct motions. Do not treat unrestricted ring rotation as demonstrated need.
3. If substantial ring rotation is needed, revise arc extent/retraction and test
   the resulting motion path, tolerances and guidance tradeoff.
4. Check explicit hand/grip and downstream tool envelopes after registration.

The next smallest action is a frame-to-component/support correspondence review
using the existing ten trials and publisher reference, retaining any ambiguity.
No further participant sample or paid inference is required for that review.

## Reproduction and evidence

```powershell
python scripts/audit_ha4m_geometry.py --input runs/ha4m-geometry-20261028 --output runs/ha4m-geometry-audit-new
```

Requires CadQuery/OCP and matplotlib. Use a new output directory and allow several
minutes for exact intersections. Source package is local; no download or inference
occurs. Outputs include `audit.json`, two STEP envelopes and `guide-review.png`,
with artifact hashes in the report. Successful evidence:
`runs/ha4m-geometry-audit-20261028-v3/`.

The initial run failed on generic-matrix conversion; the worker now constructs an
explicit rigid OCCT transform. The second run timed out before completion. Both
partial directories are retained and are not successful evidence. The third run
completed successfully. No original source or earlier evidence was overwritten.
