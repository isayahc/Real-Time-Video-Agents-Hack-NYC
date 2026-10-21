# Nebius model presets and NVIDIA verification

Tracks #35. The workbench and direct Nebius CLI now preset both model roles:

| Role | Built-in model | Direct-output setting |
| --- | --- | --- |
| Vision | `MiniMaxAI/MiniMax-M3` | `chat_template_kwargs.thinking_mode="disabled"` |
| Protocol compilation and default new design | `nvidia/Nemotron-3_5-Lightning` | `chat_template_kwargs.enable_thinking=false` |

These are documented provider presets, **not a claim of verified access or
successful inference in your account**. An explicit unavailable model fails;
there is no automatic replacement with Qwen or a replay result.

## Start with presets

Set `NEBIUS_API_KEY` or `NEBIUS_TOKEN_FACTORY_KEY` in the environment or the
repository's ignored `.env`, then run:

```bash
python -m protocol_pipeline.web
```

Both fields are populated. Step 5 initially uses the selected compiler model.
Previously saved choices remain authoritative. Select **Use recommended models**
to explicitly restore both built-in presets; this also seeds the next design
selection. Existing saved results keep their original model provenance.

Nonblank `NEBIUS_VISION_MODEL` and `NEBIUS_COMPILER_MODEL` override server/CLI
defaults. Empty values use the built-ins. If an older `.env` explicitly selects
Qwen, remove/change that override to use NVIDIA for CLI compilation. In-browser
edits remain supported and persist across reloads. The restore button chooses
the built-ins even when the server has an override.

Direct text extraction needs no model flags:

```bash
python -m protocol_pipeline extract-protocol \
  --text examples/extraction/procedure.txt --provider nebius \
  --output runs/preset-extraction-001
```

`analyze` and direct-Nebius sampled-video extraction also use the presets when
their model flags are omitted. Explicit CLI flags win over environment defaults.
OpenCode and replay still require an explicit `--model`; OpenCode's request
settings are managed by that provider, not this direct HTTP adapter.

## Reasoning-budget diagnosis

The project's historical Nemotron attempt was incomplete. The former adapter
supplied a bounded output budget without Lightning's thinking control.
[Nebius's migration verification](https://github.com/nebius/nebius-physical-ai/blob/main/docs/workbench/token-factory-deprecation-verification.md)
reports the same failure mechanism: reasoning consumed nearly all of a small
output allowance; the model-specific control produced complete visible output.
This supports the fix but does **not** prove the cause of our historical run
without its retained trace or a reproduction.

The shared adapter applies the controls only to the exact presets. Other models
retain their provider settings. Both stages request JSON in the prompt and
strictly validate it; MiniMax is not sent the constrained `response_format`
that the provider's report found problematic. Truncated responses remain errors.

Successful traces now retain finish reason, output budget, effective generation
settings, requested/served model IDs, usage, latency and retry count. For NVIDIA
requests, a missing or different served model is rejected instead of being
credited as NVIDIA success. Rejected completion traces survive extraction and
design failure reporting. Requests remain bounded to three transport attempts
for transient HTTP failures; no automatic model fallback is introduced.

The vision preset follows that same provider report's replacement for the
retired Qwen vision default. Explicit legacy choices are preserved because
account availability can differ; restoring presets is a user action.

## Live NVIDIA verification

With a configured key, run from a source checkout:

```bash
python -m scripts.verify_nebius --output runs/nebius-verification-001
```

This makes paid live calls: account catalog → 512-token JSON probe → source text
extraction → real protocol compiler → apparatus/resource artifacts and report.
The extraction request has a 12,000-token budget. A source-citation failure may
cause one bounded correction call; transient transport retries can also incur
usage. Use a new output directory for each run. An explicitly selected NVIDIA
model may be supplied with `--model`; availability is checked against the account
catalog, then separately tested through inference.

`verification.json` records status, run ID, commit/dirty state, implementation
hashes, source hash, successful traces and output hashes. The probe and extraction
artifacts remain alongside it. Missing credentials, a missing catalog model,
incomplete JSON, a served-model mismatch, or failed compilation cause a nonzero
exit. No test is skipped into success and no fixture is substituted.

Review these local outputs before sharing: they contain source text and model
responses. Authentication headers and keys are not written by the verifier.
Passing this text smoke does not establish video accuracy, physical performance
or cost savings. A live vision run and source review remain separate gates.

## Verification status for this change

- Automated tests exercise actual HTTP payload construction, model presets,
  browser preference handling, identity checks and downstream compilation using
  explicitly synthetic transport responses. They are not live provider proof.
- The local live-verification attempt failed at credentials because neither
  supported Nebius key was configured. No inference request was made.
- NVIDIA account availability and successful live extraction remain outstanding;
  keep #35 open until a successful reviewed run is linked.
- The historical Qwen smoke documented in `examples/extraction/README.md` remains
  historical Qwen evidence and is not relabeled as NVIDIA output.

## Provider references

- [Nebius integration guide](https://github.com/nebius/nebius-physical-ai/blob/main/docs/workbench/token-factory.md)
- [Provider migration and thinking-control evidence](https://github.com/nebius/nebius-physical-ai/blob/main/docs/workbench/token-factory-deprecation-verification.md)
- [NVIDIA Lightning model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16)

Consulted October 21, 2026. Catalog membership alone is not an inference test.
