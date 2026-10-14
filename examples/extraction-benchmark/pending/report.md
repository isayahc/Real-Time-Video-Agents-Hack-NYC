# Extraction benchmark

**review_pending; reference: assistant_authored_reference_requires_user_review; evidence: recorded_fixture_review.**

| Dimension | Score | Pending judgments |
| --- | --- | --- |
| Step recall | pending | 7 |
| Step precision | pending | 7 |
| Step grounding support | pending | 0 |
| Ordering preserved | pending | 6 |
| Preparation/evidence classification | pending | 7 |
| Acceptance recall | pending | 2 |

## Explicit review differences

- steps missed: none
- steps unsupported: none
- steps grounding_failed: none
- steps pending_reference: r1, r2, r3, r4, r5, r6, r7
- steps pending_candidate: grip_tube, identify_tube, place_release, prepare_racks, reset_station, transfer_tube, verify_destination
- acceptance missed: none
- acceptance unsupported: none
- acceptance grounding_failed: none
- acceptance pending_reference: a1, a2
- acceptance pending_candidate: handling_and_clearance, identity_and_placement

Ordering checks:

- r1 before r2: pending_alignment
- r2 before r3: pending_alignment
- r3 before r4: pending_alignment
- r4 before r5: pending_alignment
- r5 before r6: pending_alignment
- r6 before r7: pending_alignment

## Limits

- Reference is assistant-authored and needs user review; it is not an independently certified gold standard
- The source and replayed candidate are authored concept fixtures, not a live-model evaluation set
- Initial one-to-one operation matching excludes split/merged steps; do not silently penalize them as semantic errors
- Expected ordering follows the authored procedure sequence and is not measured physical execution
- Scores depend on reviewer semantic alignments and citation judgments, not automatic semantic verification.
- One-to-one initial matching; split or merged operations require a richer review contract.
- One authored text fixture is not evidence of general live-model extraction quality.
