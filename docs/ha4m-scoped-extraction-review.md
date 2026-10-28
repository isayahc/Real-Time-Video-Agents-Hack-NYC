# Scoped human-task extraction: review before CAD

One user-authorized extraction-only live retry used the existing eight frames from
v000009, Nebius `nvidia/Nemotron-3.5-Super-VL` for observations and GMI
`openai/gpt-6-astra` for protocol compilation. No proposal/CAD calls followed.

Context was explicitly supplied and retained, including publisher action 9
(Block 2 onto Block 1) and reviewer scope excluding the experimenter's card.
The context is SHA-256-bound to the input video; it is not presented as blind visual
discovery. `source-manifest.json` records `annotation_ground_truth_sent_to_model:
true`, context bytes/hash and `extraction_mode: annotation_assisted_video`.
Default context-free extraction retains its existing annotation exclusion.

## Actual review outcome

Local outputs: `runs/ha4m-scoped-extraction-20261028/extracted/`.

| Check | Result |
| --- | --- |
| Card excluded from production actions | Pass; mentioned only as excluded context |
| Two distinct workpiece identities | Fail; only `obj_white_assembly` |
| Upper block positioned onto lower block | Fail; graph still describes lift/hold then place on table |
| Protocol preserves uncertainty | Pass; explicitly refuses to infer joining from the deficient graph |
| Suitable input for joining-machine generation | **No** |

Structural extraction/compilation completed, but semantic review failed. Do not
generate CAD from this result or mark the task understanding as corrected.

## Prepared next input (offline only)

A fixed workspace crop was encoded directly from the same 253 original PNGs,
preserving nominal 30 FPS and every source frame. Original dimensions 2048 × 1536;
crop x=716, y=736, width=634, height=384. No interpolation or synthesized content.
Local clip: `runs/ha4m-joining-closeup-20261028/human-joining-closeup.mp4`.
The adjacent `task-context.json` retains its video hash and source provenance hash.

Assistant inspection of `review.jpg` confirms two separate blocks at source frames
1221/1253, the upper block above the lower at 1284, and overlapping blocks from
1315 onward with hands at rim/center. Internal engagement remains unverified.
The fixed crop removes much irrelevant scene area; whether it improves this vision
model's interpretation is **not tested live**. No additional paid call was made.

## Reproduce extraction (paid; requires approval)

`scripts/extract_scoped_video.py` accepts `--ingested`, `--task-context`, and a new
`--output` directory. It runs observations/protocol only. The cropped clip first
needs normal frame ingestion; do not reuse the wide-view manifest with its new hash.

Tests: **277 passed, 4 skipped, 12 subtests passed**. New regression tests enforce
video/context binding and explicit annotation disclosure, including failure traces.
Next smallest action: one cropped-input extraction retry, reviewed before CAD.
