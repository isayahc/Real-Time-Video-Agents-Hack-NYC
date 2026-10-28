# HA4M: ten-trial recorded assembly baseline

## Why this dataset

IndustReal's official annotation host remains inaccessible. HA4M's **official CNR
public share is accessible** and supplies complete per-frame action annotations
and timestamped RGB frame indexes. This establishes a recorded manual baseline
without asking the user to collect hardware measurements.

- Authors: Grazia Cicirelli, Roberto Marani, Laura Romeo, Manuel García Domínguez,
  Jónathan Heras, Anna G. Perri and Tiziana D'Orazio.
- Paper: [Scientific Data 9, 745 (2022)](https://doi.org/10.1038/s41597-022-01843-z).
- Dataset DOI: [10.57760/sciencedb.01872](https://doi.org/10.57760/sciencedb.01872).
- [Authors' repository and terms](https://baltig.cnr.it/ISP/ha4m): **CC BY 4.0**.
- [Official growing dataset share](https://cloud.cnr.it/owncloud/index.php/s/j5BZvG1sXPzh6x1),
  linked directly by the authors. This is the source used, not a third-party mirror.

The task is manual assembly of an epicyclic gear train (EGT), with 12 action
classes, repeated bearing/gear/screw placements, and class 0 for transitions or
unexpected events. Researchers manually annotated the RGB frames and cross-checked
the labels. The labels **do not provide defect/acceptance ground truth** comparable
to IndustReal's assembly-state annotations.

## Selection and retained evidence

Exactly **ten trials**, `IDU001V001` through `IDU010V001`: the first trial of each
of the first ten participant IDs. This is a convenience sample with possible
first-trial/participant-order effects, not a representative or held-out benchmark.
No official split is asserted. If training/evaluation is added, keep participant
groups separate and avoid presenting this exploratory sample as independent test data.

Retain complete original `Labels.txt` files, complete RGB directory indexes with
frame IDs/device timestamps, source hashes, interval summaries and sparse original
PNG previews. Only **12 uniformly spaced RGB frames per trial** are requested,
including the endpoints. Full RGB recordings are not downloaded. Sparse MP4s are
explicitly **one-sample-per-second slideshows**, not original-time videos; downstream
reasoning must use the original frame IDs/timestamps in the manifest. Do not use
slideshow duration as an action-duration measurement.

Local outputs: `runs/ha4m-ten-20261028/` (ignored). Publisher README and license
snapshots are retained under `source-context/`; source media remain local.

Retrieval completed: **10 full annotation timelines, 120 original RGB PNGs
(402,530,901 bytes) and 10 sparse previews**. All PNG/video hashes were independently
rechecked; all ten videos decoded and contained the expected 12 frames. The initial
preview attempt encountered a missing optional OpenCV dependency; the downloader
now uses PNG header checks plus the existing FFmpeg decoder and resumed from the
verified metadata without redownloading annotations.

The independent offline rebuild is at `runs/ha4m-baseline-audit-20261028/report.md`.
Regression/full-suite checks: **259 passed, 4 skipped, 12 subtests passed**. Tests
cover repeated actions, background accounting, terminal-time uncertainty, timestamp
regressions, missing/invalid frame labels, source tampering, offline reconstruction
and preservation of unknown accepted-output resource metrics.

## Recorded baseline

All **42,378** label rows align one-to-one with contiguous RGB frame IDs. All
expected action/repetition pairs are present in all ten trials, without fragmented
pairs. This is annotation coverage, **not proof of ten accepted products**.

Nominal duration uses the paper's **30 FPS**, preserving all frames including
class 0: **1,412.60 s total**, **141.26 s/trial mean**, range **80.90–204.20 s**.

| Labeled action | Mean nominal seconds/trial | Share of all recorded frames |
| --- | ---: | ---: |
| Join block 2 onto block 1 | 28.12 | 19.90% |
| Pick up Allen key, tighten, return key and EGT | 22.95 | 16.25% |
| Place the two screws, combined | 22.61 | 16.01% |
| Place cover | 10.88 | 7.70% |
| Place three gear bearings, combined | 9.99 | 7.07% |
| Place three planet gears, combined | 9.39 | 6.65% |

The first three account for **52.16%** of recorded frames. These are candidates
for closer inspection, not measured avoidable time or demonstrated savings.

### Timing validation

Every trial contains **6–7 duplicate adjacent device timestamps**; no timestamp
decreases or gaps above 50 ms were found. Nominal frame-count durations and device
first-to-last spans are therefore kept separate. Device timing for a segment ends
at the next segment's first timestamp; the final segment's terminal timestamp is
unknown and is not extrapolated. The raw timestamps and duplicate counts are retained.

Labels are independent publisher annotations; our offline audit verifies their
structure and frame-index alignment, not their visual correctness. Sparse previews
cannot independently validate every action boundary.

## Reproduce

Requires Python project dependencies and `ffmpeg` on PATH. No model keys required.

```powershell
python scripts/sample_ha4m.py --output runs/ha4m-ten-new
python scripts/evaluate_ha4m.py --input runs/ha4m-ten-new --output runs/ha4m-audit-new
```

The downloader caps selection at ten trials and twelve previews per trial, PNGs
at 10 MiB each and planned preview payload at 800 MiB. It fetches no whole archive,
depth, skeleton or point-cloud data. Original bytes are hashed. New output folders
are required; `--resume` verifies complete source-metadata hashes before completing
previews and refuses existing preview files without recorded matching hashes.

The offline evaluator reconstructs intervals from the raw labels/indexes after
hash verification, rather than trusting cached summaries. It exports `baseline.json`,
`report.md`, and results from the **existing resource evaluator**. Only the measured
recorded device-time span is supplied to resource accounting; accepted-output,
labor, energy, cost and throughput metrics remain unknown. No second optimizer is
introduced and the earlier coil/BridgeData paths remain separate.

## Next smallest experiment

Inspect block-joining intervals in these trials to determine whether alignment,
grasping, insertion or recovery dominates. Compare a proposed locating/alignment
fixture against a proposed screw-presentation aid using explicit predictions.
Use full-resolution frames around the relevant intervals from these same ten
trials if sparse previews are insufficient; additional downloads must remain bounded.

Keep fixture cycle savings, installation/setup costs, output equivalence and
quality effects as hypotheses until tested. This pass supplies a dataset-backed
time allocation baseline, not physical intervention validation, measured ROI,
complete operator labor or continuous tracking. No paid inference is required for
the baseline and none was performed.
