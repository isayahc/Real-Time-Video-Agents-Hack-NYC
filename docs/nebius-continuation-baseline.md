# Nebius continuation baseline — October 27, 2026

Follow-up: [live NVIDIA text verification](nebius-live-verification-20261027.md)
passed, and the [OpenCode V2 startup fix](opencode-v2-startup-verification.md)
now passes the no-inference E2E preflight. Results below retain the original audit
state; full paid video-to-CAD-to-scene verification remains outstanding.

Audited starting commit `b6f6b8c138ef6e4191567561d59a4c4dde3699d0` on
`nebius-continuation`, after fetching origin. The only pre-existing untracked
content was `.playwright-mcp/`; it was preserved. This is a local-environment
audit, not a clean-checkout or submission acceptance certificate.

## Capability and evidence matrix

| Capability | Evidence and remaining boundary |
| --- | --- |
| Sampled video → observations → procedure/requirements | Implemented with validated frame references, timestamps and hashes; offline contract tests pass. Not continuous tracking or an accuracy benchmark. |
| Design/economics → machine/CAD → scene/lab | Implemented using existing workbench services, native CAD exports, visual review and versioned snapshots. Native tests use deterministic provider responses. |
| Workbench and snapshot import/export | HTTP integration, saved artifacts and checksum contracts exercised by the test suite. No new manual browser acceptance performed in this audit. |
| Nebius Token Factory | Authenticated catalog access succeeded in this audit. Historical Qwen text/proposal successes are documented in README and issues; they are not new NVIDIA evidence. |
| NVIDIA contribution | Lightning catalog membership verified; successful live inference and downstream consumption remain pending paid-call authorization. |
| Scripted provider routing | Nebius `nvidia/Nemotron-3.5-Super-VL` for vision/critique; GMI `openai/gpt-6-astra` for reasoning/CAD. Preflight reached OpenCode startup after its native-runtime and both model-catalog checks. |
| Existing demo | README labels stacking output as live-model-authored CAD with local refinements and authored animation. Not an unedited fresh E2E run or physical execution. |

Direct workbench/CLI presets remain MiniMax M3 vision and NVIDIA Lightning
compilation. Existing environment overrides remain authoritative. The local
compiler override selected a non-NVIDIA model; the verifier correctly rejected
that default. An explicit `--model nvidia/Nemotron-3_5-Lightning` was used for the
catalog check without modifying configuration.

## Commands and observed results

- Initial `python -m pytest -q`: **199 passed, 4 skipped, 12 subtests passed**.
- After catalog-only implementation: **201 passed, 4 skipped, 12 subtests passed**.
- `python -m scripts.verify_offline --output runs/continuation-baseline-20261027-01`:
  **10 workflows passed**, network connections blocked; hashed local outputs retained.
- `python -m pip check`: failed on shared-environment `huggingface-hub 1.29.0`
  conflicting with `tokenizers 0.21.0` and `transformers 4.48.2` requirements.
  These packages are not declared project dependencies; no shared packages were changed.
- `python scripts/run_e2e.py --check`: failed with
  `TimeoutError: OpenCode server startup exceeded 20 seconds`.
  Browser preflight completion is not claimed. Inspect startup/connection compatibility
  before authorizing a full paid E2E run; local logs are not publication-ready evidence.
- With `WORKBENCH_NATIVE_E2E_TESTS=1` and `WORKBENCH_NATIVE_CAD_TESTS=1`,
  `python -m pytest -q tests/test_e2e.py tests/test_opencad_program.py tests/test_scenes.py`:
  pytest reported **30 passed, 1 skipped**, but the shell reported **exit code 1**.
  The result is not a clean process-level pass; investigate teardown/exit status.
- `python -m scripts.verify_nebius --catalog-only --model nvidia/Nemotron-3_5-Lightning --output runs/nebius-catalog-20261027-01`:
  **catalog_verified**, `live_inference=false`, `nvidia_model_verified=false`.
  Local `verification.json` records revision, dirty state, implementation hashes and
  catalog checksum. No source upload or inference request occurs in this mode.

No paid inference was performed. Local outputs remain ignored; existing snapshots
and provenance contracts were preserved.

## Submission audit

GitHub issue bodies/statuses #34–#44 were inspected. #37 is closed and MPL-2.0
is present in the repository and package metadata. #34–#36 and #38–#44 remain open:
live NVIDIA evidence, reviewed Token Factory evidence, reproducible acceptance run,
demo recording, narrative, integration feedback, new/reused-work explanation,
judge access and asset permissions remain acceptance gates.

The issues cite October 30, 2026 at 17:00 UTC for submission and December 15 for
the end of judging. Fetching the official rules at
<https://nebiusglobalaihackathon.devpost.com/rules> returned HTTP 403 during this
audit, so these dates were **not independently reconfirmed**. The private Devpost
draft and publication permissions were not inspected. Existing CREOLab attribution
does not by itself close the selected submission clip's permission review.

## Smallest next actions

1. Obtain authorization for the existing paid text verification command using an
   explicit Lightning model. It runs a 512-token JSON probe and a 12,000-token
   extraction budget, potentially one citation correction and bounded transport
   retries. Retain requested/served identity, validation, latency, usage and actual
   downstream compiler artifacts; catalog access alone does not close #35.
2. Diagnose OpenCode startup and native-test exit status without changing provider
   assignments. Resolve dependencies in a project-specific environment if needed.
3. Select a permitted video and authorize a separately bounded full E2E run.
   Preserve a fresh version, review source citations and before/after captures,
   and only then package claim-to-evidence and judge instructions.
4. After the baseline is verified, evaluate additive physical-event records,
   temporal transitions, robustness metrics, optional streaming and agent exports.
   These remain future work, separate from current submission requirements.
