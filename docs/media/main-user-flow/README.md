# Main user-flow screenshots

Captured October 30, 2026 using Playwright against `http://127.0.0.1:8023/`.
The documentation branch is based on `80a719e`, the merge of PR #79 into
`nebius-continuation`. These are actual rendered UI screenshots, not mockups.

## Capture conditions

- Desktop Chromium, **1440 × 1000 CSS-pixel viewport**, local unauthenticated UI.
- `01-see-the-task.png`: default fastening task, human video paused at 1 second;
  full-page screenshot.
- `02-review-the-change.png`: opened tab 2 without clicking Analyze; all three
  candidate videos loaded and paused at 4 seconds; full-page screenshot.
- `03-compare-costs.png`: reopened historical snapshot
  `7dd7a47e9f2f4f06b6e7bb573d2cdc96`; paired playback started and paused successfully,
  then both videos sought to 4 seconds. Capture is cropped to the upper comparison
  through its headline metrics (1425 × 1548), omitting the long source excerpts.
- Screenshot content width is 1425 pixels; the browser viewport's remaining
  15 pixels are occupied by the scrollbar.
- No DOM content was replaced and no API response was mocked. The third image
  uses an existing earlier analysis, not a new automatic-agent result.
- No credentials, environment contents or private recording assets are shown.

## Browser observations

| Check | Observed outcome |
| --- | --- |
| Task options | Two prepared choices; fastening selected by default. |
| Step 1 human media | 880-pixel decoded width, readyState 4, no media error. |
| Step 2 candidate media | All three decoded at 960-pixel width, readyState 4, no media errors. |
| Step 3 paired playback | Both videos advanced while playing; pause worked. |
| Step 3 media | Human 880-pixel width, machine 960-pixel width; readyState 4, no media errors. |
| Saved costs | $0.133 human / $0.085 custom tooling; earlier lean scenario. |
| Saved sources | Five rendered research links. |
| UI alert | Empty at each captured state. |

This was a documentation capture, not a full browser regression or mobile audit.
No Analyze action, paid request, newly generated analysis or test-suite run was
performed. The new live agent-selection path remains unverified by these images.

## Attribution and reuse

The screenshots include the following attributed material:

- **Human footage:** HA4M, Cicirelli, Marani, Romeo, Garcia Dominguez, Heras, Perri
  and D'Orazio, *Scientific Data* 9, 745 (2022).
  Dataset DOI: [10.57760/sciencedb.01872](https://doi.org/10.57760/sciencedb.01872).
  License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  Shown clip: IDU004V001, action 12, derived encoded excerpt; screenshots reproduce
  a paused frame within the workbench UI.
- **Reference gearbox CAD:** MindBot,
  [DOI 10.5281/zenodo.5675810](https://doi.org/10.5281/zenodo.5675810),
  [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
  Shown within an authored custom-fastening-station visualization. Screenshots
  containing that adapted visualization are shared under **CC BY-NC-SA 4.0**;
  this does not change the underlying code or other source licenses.
- **SO-101 robot meshes:** The Robot Studio / MuJoCo Menagerie,
  [model and Apache-2.0 license](https://github.com/google-deepmind/mujoco_menagerie/tree/main/robotstudio_so101).
  [Retained upstream license](SO101-LICENSE.txt).
  Render package source OID: `8b739c94709abfe11b8e99b07fd74ec0bbad5d97`.
- **Unitree G1 robot meshes:** Unitree / MuJoCo Menagerie,
  [model and BSD-3-Clause license](https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1).
  [Retained upstream copyright/license notice](G1-LICENSE.txt).
  Render package source OID: `ad24af3fa9bc1a99e37291e656fb85e445da6158`.
- Robot previews use locally authored position-only IK, proxy workpieces and
  hypothetical tool coupling. They are not recordings of physical robots or
  validated policy/physics execution. No source author endorsement is implied.
