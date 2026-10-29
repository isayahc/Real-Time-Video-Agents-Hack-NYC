# Final-tab comparison layout verification

Implemented on `nebius-continuation`: original source video left, saved generated
machine MP4 right; responsive single-column layout on narrow screens. Native CAD
inspection remains available. A run without a machine video explicitly displays
that gap and its interactive CAD preview. Source and machine clocks are independent;
no measured performance comparison or fabrication recording is implied.

Verified in the local browser:
- Imported v000008: source video decoded (readyState 4), native canvas mounted,
  missing-video caption visible, secondary details collapsed.
- Existing authored stacking run `b2a3871f5aa2481a80fcbc39f2541a5d`: both original
  and generated MP4 decoded and played (readyState 4; widths 1280 and 960).
  This tests the UI, not new inference or permission to publish that older footage.
- Leaving the tab pauses both source and native playback.
- 390px mobile viewport: single column and no horizontal overflow.
- Local screenshots: `.playwright-mcp/comparison-before.png`,
  `comparison-after-desktop.png`, `comparison-after-mobile.png`,
  `comparison-two-videos.png` in that same directory.
- Existing inline-style CSP console errors also occurred before the change;
  they are unrelated to video loading. No new playback error observed.
- Full offline suite: 273 passed, 4 skipped, 12 subtests passed.

No model calls or new footage downloads. The robot-based source remains unsuitable
for the intended human-to-machine demo; no source was swapped beneath existing
generated results. Next: acquire a bounded continuous HA4M human-work clip, then
generate a corresponding machine demonstration with explicit paid-run approval.
