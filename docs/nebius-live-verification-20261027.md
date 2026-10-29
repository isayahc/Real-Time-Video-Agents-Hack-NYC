# Live NVIDIA text verification — October 27, 2026

User-authorized paid verification on `nebius-continuation`, based on commit
`4afa5a3aeac714a6f18db0d0b82aa243bfe2b726` with the probe-prompt fix uncommitted
at execution time. The local verifier records dirty state, implementation hashes
and its own checksum, so this is not represented as a clean-tree run.

## Result

**Successful live NVIDIA participation through Nebius Token Factory:** source text
was extracted into seven operations and consumed by the real protocol compiler.
Requested and served model IDs both matched `nvidia/Nemotron-3_5-Lightning`.
Strict output validation passed; no provider substitution or replay was used.

```powershell
python -m scripts.verify_nebius --model nvidia/Nemotron-3_5-Lightning --output runs/nebius-live-20261027-02
```

Input: repository-owned example `examples/extraction/procedure.txt`.
Source SHA-256: `578884be7f0af6b6bf29a25e3e4aaa3e3fdeeadaebabca4e9ae008b43cb0f51f`.

| Call | Outcome | Latency | Prompt tokens | Completion tokens | Finish |
| --- | --- | --- | --- | --- | --- |
| Initial probe, run `01` | Returned bare `true`; rejected by object schema | 0.616 s | 131 | 2 | stop |
| Explicit-object probe, run `02` | Passed | 0.442 s | 146 | 6 | stop |
| Text extraction, run `02` | Passed and compiled | 7.599 s | 2234 | 2150 | stop |

Each call took one transport attempt. No citation correction was needed. Total
reported usage across these three calls was **4,669 tokens**; billing cost was not
returned and is not inferred. Latencies describe these calls, not a benchmark.

The first prompt said `Return ready=true as JSON`; the response was a valid JSON
boolean but invalid `CompletionProbe`. The fix requests exactly `{"ready": true}`
and explicitly excludes a bare boolean. Validation remains strict. A regression
test reproduces the rejected boolean and verifies retained diagnostics and no
downstream extraction after failure.

## Retained local evidence

- `runs/nebius-live-20261027-01/verification.json`: failed probe with served model,
  finish reason, response, usage, latency and validation error.
- `runs/nebius-live-20261027-02/verification.json`: successful verification,
  source/implementation hashes and downstream artifact checksums.
- `probe.json`, `catalog.json`, and `extraction/` under successful run `02`.
- `extraction/compiled/`: protocol input, apparatus requirements, process graph,
  process input, summary and Markdown report.

All **13 indexed artifact checksums** were independently recomputed and matched.
Artifacts remain local/Git-ignored; this summary is not a published raw evidence
bundle and does not close the reviewed public-evidence requirement in #36.

## Limitations and next gate

This establishes live text extraction and downstream consumption for #35, not
video accuracy, semantic correctness, generated CAD, scene rendering, physical
execution or measured economics. The compiled report keeps resource quantities
unknown. Candidate equipment includes speculative choices such as obstacle
detection lidar and multispectral identity verification; these require review,
not promotion to source-observed requirements.

The focused suite passed **16 tests**. Full baseline results and remaining
OpenCode/native-process blockers are in the
[continuation audit](nebius-continuation-baseline.md). Next: resolve E2E preflight,
select permitted footage and obtain separate authorization for full paid
video-to-CAD-to-scene execution. No new video inference was authorized by this
text verification.
