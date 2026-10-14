# Extraction benchmark

**review_complete; reference: assistant_authored_reference_requires_user_review; evidence: recorded_fixture_review.**

| Dimension | Score | Pending judgments |
| --- | --- | --- |
| Step recall | 100.0% | 0 |
| Step precision | 100.0% | 0 |
| Step grounding support | 100.0% | 0 |
| Ordering preserved | 100.0% | 0 |
| Preparation/evidence classification | 100.0% | 0 |
| Acceptance recall | 100.0% | 0 |

## Explicit review differences

- steps missed: none
- steps unsupported: none
- steps grounding_failed: none
- steps pending_reference: none
- steps pending_candidate: none
- acceptance missed: none
- acceptance unsupported: none
- acceptance grounding_failed: none
- acceptance pending_reference: none
- acceptance pending_candidate: none

Ordering checks:

- r1 before r2: preserved
- r2 before r3: preserved
- r3 before r4: preserved
- r4 before r5: preserved
- r5 before r6: preserved
- r6 before r7: preserved

## Limits

- Reference is assistant-authored and needs user review; it is not an independently certified gold standard
- The source and replayed candidate are authored concept fixtures, not a live-model evaluation set
- Initial one-to-one operation matching excludes split/merged steps; do not silently penalize them as semantic errors
- Expected ordering follows the authored procedure sequence and is not measured physical execution
- Scores depend on reviewer semantic alignments and citation judgments, not automatic semantic verification.
- One-to-one initial matching; split or merged operations require a richer review contract.
- One authored text fixture is not evidence of general live-model extraction quality.
