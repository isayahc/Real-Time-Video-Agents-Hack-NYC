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

## Approved close-up retry: task identity recovered

The next user-authorized extraction-only retry used the fixed crop and the same
eight timestamps (0, 1.2, 2.4, 3.6, 4.8, 6, 7.2, 8.4 seconds). Outputs:
`runs/ha4m-joining-closeup-20261028/extracted/`. Both providers completed with finish
reason `stop`; served vision ID matched `nvidia/Nemotron-3.5-Super-VL`. GMI returned
`gpt-6-astra` for the requested `openai/gpt-6-astra`.

- Graph now distinguishes `obj_circular_block` and `obj_clover_block` and includes
  `act_join_blocks` with both objects. Protocol keeps both identities and a joining
  operation. Card handling and the unrelated small piece are excluded.
- Internal engagement, self-retention and successful assembly remain explicitly
  unverified. Annotation assistance remains disclosed.
- **Task identity: passes assistant review. Direct design handoff: needs two
  explicit role/shape corrections.** The graph describes four lobes and both
  blocks being lifted. Inspection of cropped frame 0000, frame 0002, and the
  retained source contact sheet instead supports moving the ring-shaped upper
  block from the left onto the lower subassembly on the right. Do not convert
  the guessed lobe count into fabrication geometry or assume a two-part lift.

An immutable-input review sidecar, `semantic-review.json`, hashes the raw outputs
and records these corrections separately. The original provider responses are
unchanged. The intended next design is **upper-block transfer/alignment onto a
located lower block**, with actual contact geometry checked against source CAD.
That does not establish insertion force, acceptable fit or required gear-phase motion.

No new CAD/proposal calls or corrected machine snapshot were produced by this
extraction-only approval. Next: use the explicitly reviewed task scope for a new
design/CAD/animation pass, with paid-call approval. No code changed after the last
277-pass offline suite; this review adds documentation and ignored local evidence.

## Approved reviewed-design continuation

The user subsequently approved one design/CAD/animation run. Its input is
`runs/ha4m-joining-closeup-20261028/reviewed-design-input/`: `protocol.json` contains
the explicit role corrections and a proposed integrated-station/named-body design
brief; `review.json` binds that derivative to raw protocol and observation hashes.
No guessed lobe count is used as an engineering dimension. No raw inference is edited.

`scripts/design_reviewed_task.py` verifies those hashes and the clip/context binding,
then appends a snapshot with mode `reviewed-extraction-live-design-continuation`.
It retains raw extraction, reviewed input, cropped source and fresh downstream
outputs separately. It does not claim a new blind or uninterrupted extraction run.
The final result and presentation quality require inspection after completion.

Offline tests after adding the continuation command: **278 passed, 4 skipped,
12 subtests passed**, including rejection of changed review input before paid work.
