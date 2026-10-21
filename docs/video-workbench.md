# Video workbench: verification and demo guide

Tracks #26. This implementation does not close the live-inference or semantic-review requirements.

## Start and use

1. Install `ffmpeg`/`ffprobe` and `python -m pip install -e ".[web,test]"`.
2. From the repository directory, copy `example.env` to `.env` and set `NEBIUS_API_KEY` or `NEBIUS_TOKEN_FACTORY_KEY`, or export either key in your shell. The web app and `python -m protocol_pipeline` automatically load `.env` from the current working directory using `python-dotenv`; existing environment variables take precedence. Optionally set `NEBIUS_VISION_MODEL` and `NEBIUS_COMPILER_MODEL`. Run `python -m pip install -e ".[web,test]"` after updating and restart the server after editing `.env`. The example file itself is not loaded.
3. On Windows, double-click `run-workbench.cmd` (or run it from a terminal). Elsewhere, run `python -m protocol_pipeline.web --reload`. Open http://127.0.0.1:8000. Backend code changes reload automatically; frontend changes need only a browser refresh. The launcher uses the repository directory so `.env` loads consistently. Keep the terminal open; Ctrl+C stops the server.
4. Select a short procedure video whose use is permitted. Confirm it plays. Nebius is already selected by the web flow, with `MiniMaxAI/MiniMax-M3` preset for vision and `nvidia/Nemotron-3_5-Lightning` for compilation and new designs. Override either model ID if needed and choose 2–24 sampled frames.
5. Start analysis. The video remains playable while stages advance. No guessed percentages or fabricated incremental operations are shown.
6. Inspect completed operations, capability/equipment mappings, resource quantities and report. Click a timestamp to pause/seek the video and display the corresponding sampled frame. Hypotheses without observed evidence have no invented timestamps.
7. Download artifacts or the evidence ZIP. Reopen the run using its URL hash or the saved-runs selector.

Both presets are returned by `/api/config` and sent as `vision_model` in the upload request. Nonblank `NEBIUS_VISION_MODEL` and `NEBIUS_COMPILER_MODEL` settings override their server defaults; blank values use the presets. Browser model edits persist across video changes and reloads when local storage is available, taking precedence over server defaults. Only model IDs are stored, never credentials. **Use recommended models** explicitly replaces saved choices with the built-in presets. Saved NVIDIA selections are never silently migrated to Qwen. See [preset verification](nebius-model-presets.md) for the live smoke command and remaining account verification gate. Model-request rejections identify the affected field and prompt you to select a compatible model accessible to your account. Availability still depends on the live Nebius catalog and account permissions; no live availability claim is made by the preset.

The raw upload API is `POST /api/runs?filename=...&model=...&vision_model=...&frame_count=8`, with video bytes as the body and `X-Workbench-Request: 1`. The backend serves both UI and API. Provider access stays on the server. Poll `GET /api/runs/{id}` and request `/results` after completion. `/video` supports byte ranges; `/frames/{id}` resolves real manifest frames. Cross-origin writes and unrecognized Host headers are rejected.

This local application is intentionally single-process. Do not expose it to a network as an authenticated service. A production queue, authentication, quotas, retention policy and hardened media sandbox are separate deployment work. Shut down normally to let active work finish; after a hard restart, queued/running jobs are marked failed and never automatically resubmitted.

## Reproduce the text baseline

```bash
python -m protocol_pipeline extract-protocol \
  --text examples/extraction/procedure.txt \
  --provider nebius --model Qwen/Qwen3-235B-A22B-Instruct-2507 \
  --output runs/live-text-review-001
```

Use a fresh output directory. This is a paid live request using your account; the model ID must be available. Preserve the output, command, commit, dependency versions and source hashes. #25's historical report is not a newly reproduced result.

## Step 5: autonomous design and planning costs

After extraction completes, select **Design autonomous version** or **05 / Autonomous**. This makes a separate, explicit model request using the saved protocol. The source procedure remains unchanged. The new proposal maps every source operation to concrete hardware or an explicit automation gap, and lists remaining human tasks and verification needs. A schema/coverage failure can make at most one additional correction request.

Prices and performance figures are rough **model planning estimates**, each with a rationale; they are not supplier quotations or measurements. Edit equipment unit prices, manual/autonomous labor and cycle times, energy, materials, recurring overhead, demand and deployment assumptions, then select **Save & recalculate costs**. The existing process/investment evaluator calculates conditional unit costs, annual savings, capacity and simple payback. Unknown inputs remain null, and output-equivalence/capacity gates still apply. The scenario assumes an existing, sunk-cost manual setup and separates capital from annual fixed costs.

Generated candidates, provider traces and source-protocol hashes live under the run's `autonomy/` directory. Cost edits are saved separately with revision records, survive restarts, and never modify the original extraction. **Download design + cost scenario** exports the proposal, current assumptions and comparison. Reopening a completed design does not make another inference request.

## Evidence bundle contents

The workbench ZIP contains the source video, sampled frames, ingestion manifest, extracted observations/protocol, compiler artifacts, run metadata and exact-byte SHA-256 checksums. Run metadata includes models, sampled-frame count, stage timings, Python/dependency versions and Git revision/dirty state when available. Provider traces include usage/latency when supplied. No billing estimate is fabricated.

No environment dump or authentication headers are exported. The ZIP does contain uploaded source content and model output; review these and their sharing permissions before publishing. Keep live evidence in a reviewed release/CI artifact rather than committing private source videos. Runtime directories remain ignored by Git.

To reproduce video extraction after unpacking a bundle, use its recorded vision/compiler models:

```bash
python -m protocol_pipeline extract-protocol \
  --run /path/to/unpacked/ingested \
  --provider nebius --model YOUR_RECORDED_COMPILER_MODEL \
  --vision-model YOUR_RECORDED_VISION_MODEL \
  --output runs/live-video-repeat-001
```

The frame manifest and hashes are verified before inference. Repeat calls may produce different model output; reproducing the workflow does not imply byte-identical inference.

## Manual browser and live acceptance checklist

- [ ] Play/pause/seek the selected source video in desktop and narrow layouts.
- [ ] Submit a live run and watch actual progress with the player still usable.
- [ ] Open all result views, click evidence, verify the frame/timestamp against the source and download the report/ZIP.
- [ ] Select another run while polling; ensure old requests do not replace the new run's results.
- [ ] Refresh a completed run URL and restart the server; verify results reopen.
- [ ] Try an invalid video/model and verify an explicit failure with no success claim.
- [ ] Capture a short end-to-end demonstration and publish reviewed evidence.

## Semantic review

Select a permitted, representative procedure clip. A reviewer must prepare the visible-operation reference and timestamps by watching that source, independently of the generated candidate. Record correct, missing, unsupported, misordered and incorrectly grounded operations, with concrete examples and raw counts. Review capability mappings/equipment separately. Keep off-camera preparation and unsourced quantities explicitly uncertain.

Use the existing `benchmark-extraction` workflow and its source-bound reference/review contracts where applicable; see `examples/extraction-benchmark/README.md`. Do not reuse the authored text fixture as a video ground truth, and do not report precision/recall before an explicit matching rule and completed review exist. A single clip cannot establish general accuracy.

## OpenCode diagnosis and remaining work

The direct provider remains the workbench's video path. OpenCode's text adapter now performs up to three local correction attempts for schema-valid but cross-field-invalid candidates, records actual served-model metadata when returned, checks explicit server errors, and cleans up its session. The SDK debug example remains useful for inspecting a retained session. Structured-output retries and local validation retries are separate.

Live missing-output behavior is still unresolved: collect CLI/server and SDK versions, model/provider IDs and a sanitized response envelope, then isolate a minimal structured-output request. Qwen worked in the historical direct-Nebius text run; that is not proof it works through OpenCode. No live success is claimed here.

After a reviewed video run, define a separate scene-generation verification using the resulting apparatus requirements. Generated geometry alone does not validate engineering feasibility or physical performance.

## Automated verification

```bash
python -m pip install -e ".[web,test]" -r examples/debug-extraction/requirements.txt
python -m pytest -q
python -m scripts.verify_offline --output runs/issue-26-offline
node --check protocol_pipeline/web_static/app.js
```

The web tests use actual FFmpeg decoding, extraction/compiler code and HTTP handlers with explicitly synthetic replay responses. They cover completed output, source/frame mapping, media ranges, ZIP checksums, invalid video, upload limits, cross-origin protection, missing credentials and restart recovery. They do not establish browser rendering, model accuracy or live provider compatibility.

