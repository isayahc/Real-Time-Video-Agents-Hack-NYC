# Offline failure replay and CI

```bash
python -m protocol_pipeline failure-replay --output runs/failure-replay-001
```

Uses the hypothetical CW-02 full-batch input from the apparatus comparison and selected candidate operation requirements. Every observation is fabricated and explicitly illustrative; actual source-video acceptance is unresolved.

| Case | Expected behavior |
| --- | --- |
| Explicitly skipped stock verification | Flag the skipped required preparation step |
| Batch elapsed time rises from 6,000 to 9,000 seconds | Flag throughput deviation; do not attribute the cause to winding |
| Accepted count drops from 95 to 50 of 100 attempts | Flag increased resources/cost per accepted output; leave unmeasured scrap disposition unknown |
| Preparation evidence and accepted/labor/energy values absent | Mark the step and metrics unknown; do not infer a skip or a numerical failure |

These are checks of software behavior, not sensor-based diagnoses, measured physical outcomes, or automated corrective actions. See the executed [report](report.md) and [summary](summary.json).

## Continuous verification

`.github/workflows/offline.yml` runs on pull requests, pushes to main and manual dispatch, with Python 3.11/3.12. It installs the Python package plus ffmpeg, runs the test suite, and executes all five offline workflows with Python socket connections blocked. Dependency installation and artifact upload still use network access; the application stages require no provider credits or keys.

Run the same workflow stages locally:

```bash
python -m unittest discover -s tests -v
python -m scripts.verify_offline --output runs/ci-offline-001
```

Outputs include accounting/coil reports, evidence/illustrative alternatives, the failure replay and a hash manifest. CI retains downloadable artifacts for 14 days. Use a new output directory to preserve prior evidence. The accounting loop's record timestamps and dependent lineage hashes naturally vary between executions.
