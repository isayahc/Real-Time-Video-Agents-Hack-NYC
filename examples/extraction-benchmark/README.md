# Extraction benchmark and review workflow

This initial benchmark scores the existing authored empty-tube text example. It separates the source, reference expectations, candidate extraction and reviewer judgments.

**The reference is assistant-authored from the seven source lines and needs user review. The candidate is a hand-authored replay response. Neither is an independent held-out live-model evaluation.** Scores here establish scoring behavior, not Nebius accuracy or physical validity.

## Start a review

```bash
python -m protocol_pipeline benchmark-extraction \
  --candidate runs/text-extraction-001/extracted-protocol.json \
  --reference examples/extraction-benchmark/reference.json \
  --source examples/extraction/procedure.txt \
  --output runs/review-pending-001
```

Without `--review`, output metrics stay pending; matching IDs or line spans do not create a perfect score. `review-template.json` contains candidate/reference hashes and empty semantic alignments/classifications. Fill it by comparing each candidate operation against source and reference:

- Align semantically equivalent steps using reference and candidate IDs. Add a rationale and separately judge whether citations support the operation.
- Explicitly classify genuinely missed reference steps and unsupported candidate steps. An unclassified item stays pending.
- Align expected acceptance checks to candidate criteria and judge citation support.
- Keep `complete: false` until every item is classified and all matched citations judged. A complete review with pending items fails validation.

Initial matching is one-to-one. Split/merged operations need a richer review contract; do not silently mark them wrong to fit this scorer. If candidate or reference bytes change, recreate and redo the content-bound review. Source bytes must match the reference's source hash.

## Score a completed review

```bash
python -m protocol_pipeline benchmark-extraction \
  --candidate runs/text-extraction-001/extracted-protocol.json \
  --reference examples/extraction-benchmark/reference.json \
  --source examples/extraction/procedure.txt \
  --review /path/to/completed-review.json \
  --output runs/review-scored-001
```

| Dimension | What is checked |
| --- | --- |
| Step recall / precision | Explicitly reviewed matches versus expected/candidate operations; missed and unsupported IDs listed |
| Grounding support | Reviewer judgment that cited evidence supports an operation, distinct from valid reference syntax |
| Ordering | Expected precedence checked through candidate dependency paths; concurrency requires the explicit directed `during` relation |
| Preparation/evidence classification | Phase and source-supported/hypothesis distinction on reviewed matched steps; missed reference steps remain in the denominator |
| Acceptance recall / precision / grounding | Expected checks matched, missing or unsupported; citation support judged separately |

There is no aggregate grade hiding tradeoffs. Pending review yields null metrics, not zeros or success. Ordering relationships through explicitly missed steps are marked unscorable and count against preservation; unreviewed alignment remains pending. An empty denominator yields no score.

## Bundled verification

The [reference](reference.json) uses its own `r1`–`r7` identifiers and source-based descriptions. The [fixture review](fixture-review.json) explicitly aligns the existing replay candidate; its reviewer/reference metadata disclose assistant authorship and pending user review.

Executed [pending report](pending/report.md) and [fixture report](fixture/report.md) are included. The perfect authored fixture is an arithmetic smoke check, not a live extraction result. Regression tests deliberately remove a step, add unsupported output, reverse ordering, misclassify preparation and reject a valid-looking citation's semantic support. Hash and overwrite tests prevent reuse of stale reviews.

89 tests passed without skips. CI now executes ten connection-blocked offline workflows, including pending and fixture-reviewed benchmark runs. [Checks](checks.json) record local evidence. The actual CREOLab coil-video reference remains outstanding; it must come from source review rather than the existing proposed apparatus graph.
