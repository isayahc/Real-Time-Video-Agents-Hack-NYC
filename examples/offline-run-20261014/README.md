# Offline run — 14 October 2026

Executed the existing accounting and iteration demo at commit `7f7be35f43d8aaadfb7fc1142cd2a9d71103490b`, without Nebius credits or live inference.

```bash
python -m protocol_pipeline demo --output runs/offline-20261014 --accounting-only
python -m unittest discover -s tests -v
```

Use a new output directory when reproducing; existing records cannot be overwritten.

## Results

- Prediction → illustrative outcome → deviations → revision → reevaluation completed.
- Flagged cost, labor, and throughput deviations in the fabricated accounting fixture.
- Revised cost per accepted output: $1.976 versus illustrative outcome $2.05; attended labor: 4.5 versus 18 operator-seconds; throughput: 100 versus 80 accepted outputs/hour.
- Electricity rises from 0 to 5 Wh per accepted output: a predicted tradeoff, not an unqualified improvement.
- CW-02 actual unit cost stays unknown; investment decision stays undetermined.
- All 59 tests passed, with no skips.
- A second run with socket connections blocked completed and produced identical evaluator summaries. Record timestamps and dependent lineage hashes differ between runs as expected.

## Scope

The outcome data is synthetic, and the revision is a supplied fixture rather than an automatically generated redesign. This run does not perform protocol extraction, video inference, scene/MCP execution, or physical validation. It verifies local accounting, deviation detection, revision evaluation, and evidence lineage. The broader protocol-to-apparatus workflow remains a separate integration step.

## Evidence

[Readable report](report.md), [HTML report](report.html), [structured summary](demo-summary.json), and [verification checks](checks.json). The four original records are preserved under `records/`.
