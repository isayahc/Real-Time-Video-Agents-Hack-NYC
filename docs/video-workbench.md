# Video workbench: verification and demo guide

Tracks #26. This implementation does not close the live-inference or semantic-review requirements.

## Start and use

1. Install `ffmpeg`/`ffprobe` and `python -m pip install -e ".[web,test]"`.
2. Set `NEBIUS_API_KEY` or `NEBIUS_TOKEN_FACTORY_KEY` in the server environment. Optionally set `NEBIUS_VISION_MODEL` and `NEBIUS_COMPILER_MODEL`. The example environment file is guidance and is not automatically loaded.
3. Run `python -m protocol_pipeline.web` and open http://127.0.0.1:8000.
4. Select a short procedure video whose use is permitted. Confirm it plays. Enter explicit available model IDs and choose 2–24 sampled frames.
5. Start analysis. The video remains playable while stages advance. No guessed percentages or fabricated incremental operations are shown.
6. Inspect completed operations, capability/equipment mappings, resource quantities and report. Click a timestamp to pause/seek the video and display the corresponding sampled frame. Hypotheses without observed evidence have no invented timestamps.
7. Download artifacts or the evidence ZIP. Reopen the run using its URL hash or the saved-runs selector.

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

## Evidence bundle

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
