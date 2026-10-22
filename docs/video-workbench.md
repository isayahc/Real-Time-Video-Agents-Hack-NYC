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

After extraction completes, select **Design autonomous version** or **05 / Design**. This makes a separate, explicit model request using the saved protocol. The source procedure remains unchanged. The new proposal maps every source operation to concrete hardware or an explicit automation gap, and lists remaining human tasks and verification needs. A schema/coverage failure can make at most one additional correction request.

Prices and performance figures are rough **model planning estimates**, each with a rationale; they are not supplier quotations or measurements. Edit equipment unit prices, manual/autonomous labor and cycle times, energy, materials, recurring overhead, demand and deployment assumptions, then select **Save & recalculate costs**. The existing process/investment evaluator calculates conditional unit costs, annual savings, capacity and simple payback. Unknown inputs remain null, and output-equivalence/capacity gates still apply. The scenario assumes an existing, sunk-cost manual setup and separates capital from annual fixed costs.

Generated candidates, provider traces and source-protocol hashes live under the run's `autonomy/` directory. Cost edits are saved separately with revision records, survive restarts, and never modify the original extraction. **Download design + cost scenario** exports the proposal, current assumptions and comparison. Reopening a completed design does not make another inference request.

## Step 6: required machines and Forma generation

The default authoring runtime is **OpenCode → Nebius**. One retained OpenCode session authors the mechanical CAD parts for a machine. Forma validates the object schema and exports real geometry; schema/kernel/export errors go back to that same conversation for correction, with at most three CAD candidates. Session IDs, raw model envelopes, candidates and native failures are retained. This route uses schema-validated JSON text because the live Nebius request rejected OpenCode's tool-based structured-output mode. Native CAD commands are executed by the worker, with their actual errors returned to OpenCode; unrelated agent tools are disabled for these authoring messages. There is no silent fallback to a different provider.

**GMI Cloud is an optional provider**, selected explicitly in Step 6 or in the visual-review CAD-correction controls. Existing Nebius/provider/model defaults are preserved. Selecting GMI offers `openai/gpt-6.1-sol`, verified in the authenticated GMI catalog and in a live OpenCode/schema smoke test. The project `opencode.json` adds only the GMI provider and references `{env:GMI_API_KEY}`; it does not change OpenCode's default model or embed credentials. Provider/model are recorded per job and session. Restart OpenCode after configuration edits; the workbench's managed server must also reload its configuration before using a newly added provider.

Machine cards show lazy **still posters and click-to-play turntable GIFs** of their actual generated CAD. A single shared temporary OpenIndustries renderer generates uncached 320 × 320, two-second, 20-frame previews sequentially for visible cards. GIFs/posters are cached privately by CAD content and preview version, so later visits use images only, without loading a 3D component or regenerating previews. Regeneration or vision-assisted CAD changes select a new cache key automatically. Leaving Machines pauses image playback and aborts pending render work. Turntables orbit the review camera; they are not physical operating-cycle animations and make no model calls.

OpenCode uses its existing configured Nebius connection and starts a local server on port 4097 when needed. Set `MACHINE_OPENCODE_URL` to reuse another server; the CLI must be installed on PATH. Mechanical CAD authoring does not imply an electrical BOM, wiring validation or physical verification. Reports explicitly distinguish OpenCode mechanical authoring from the optional **Forma native pipeline → Nebius** runtime, which runs the longer hardware/electronics workflow.

The workbench follows **human video → evidence-grounded procedure → machine proposal and costs → generated Forma machines → native OpenIndustries scene**. Step 5 is a proposal; Step 6 turns each equipment line into a separately generated hardware project and CAD asset.

Select **06 / Machines** and generate an individual machine or all missing machines. The actual Forma default hardware workflow runs with mandatory native CAD and strict fallback controls. It uses its OpenAI-compatible provider adapter routed to Nebius with server-side credentials; model selection is explicit. A separate machine-specific CAD stage authors named structural/mechanical parts and exports the assembly through Forma's OpenCAD adapter as STEP/STL and inline meshes. This avoids treating Forma's generic enclosure/base-plate CAD as a complete machine. The model returns bounded declarative part data, not executable Python; the adapter runs a fixed CAD template. Each machine has its own status, native pipeline progress, retained candidates/checkpoints, validation findings and downloadable Forma project. Failed or envelope-only output is not scene-ready. A batch stops after its first failure, retaining completed assets. Retry resumes completed Forma checkpoints or reuses a completed hardware project when the proposal/model match.

Forma Core, OpenCAD, CadQuery and Forma's `cad.py` adapter are required. A sibling `forma-oss` checkout supplies the adapter and component seed catalog; `FORMA_ROOT` and `FORMA_CAD_ADAPTER_PATH` can override these locations. Each generation initializes a private SQLite catalog using Forma's own seed data. Long-running batches execute independently of the web process so hot reloads do not block HTTP or erase progress. Generation incurs the configured provider's usage; restarting the web server never silently repeats it. Named CAD parts are exported separately through the native adapter and assembled as a CAD compound, preserving disconnected moving components instead of trying to Boolean-fuse an entire machine.

## Step 7: the native OpenIndustries viewer

Select **07 / Scene** once all required machine CAD assets are ready. Only those generated meshes are imported; no generic equipment cubes or fabricated workbench are substituted. Each installed machine unit becomes a scene instance. Stocked consumables use one labeled sample by default, retaining full quantities in the proposal, inventory report and cost inputs. Enable **Show every stocked consumable unit separately** to expand those copies explicitly. The original OpenIndustries React `WorkspaceViewer` is bundled directly from the configured checkout, including its Three.js WebGL renderer, OrbitControls, part selection and native animation evaluator. The former custom 2D schematic renderer is removed.

Drag to orbit, scroll to zoom, select a part, play/pause, restart, or scrub the timeline. **Download native OpenIndustries scene** exports bundled Forma geometry and editable native animation tracks. Scene assembly/rendering makes no model calls.

Set `OPENINDUSTRIES_ROOT` (or `OI_ROOT`) to a compatible checkout with its npm dependencies installed. A sibling `OpenIndustries` / `Open-Industries` checkout is detected automatically. Node.js and `node_modules/tsx` are required. Missing runtimes and failed native builds are reported explicitly.

Room dimensions and seconds per operation are editable planning inputs. Positions, clearance gaps and motion cues remain planning assumptions; this is not collision checking, robot kinematics, physical simulation or measured cycle time. Geometry uses the dimensions in the actual generated CAD. Scene timing does not change Step 5 cost assumptions. Sources, options, machine hashes, native output and provenance remain under the run's `machines/` and `scene/` directories. Changed proposals or regenerated machine files invalidate old scenes until rebuilt.

Layout uses each CAD asset's own footprint, with assumed clearance and animation margins. It does not allocate a largest-machine-sized grid cell to every object. Planning rooms expand to fit by default; actual room dimensions and any adjustment are recorded and displayed. Uncheck **Expand the planning room** to enforce the entered dimensions. An insufficient strict room produces a structured suggestion and a **Use suggested room & render** action. Room fitting never rescales the machine geometry or changes cost/inventory quantities.

### Vision-assisted self-correction

In Step 7, **Review & improve once** captures three labeled canonical views with OpenIndustries' actual native world/renderer and adds two source-video frame references. The vision model returns image-cited issues, proposed placements/mounting relationships and targeted CAD feedback. The worker can revise one machine through its retained OpenCode session, export real Forma CAD, and build a candidate native scene. The browser then captures matching after-views using the original camera metadata, and the vision model reassesses the same criteria.

This is a single bounded pass, not an endless regeneration loop. The default scope is layout plus at most one machine revision; **Layout only** skips CAD authoring. It uses up to two vision assessments plus the selected CAD correction session. Review requests use provider JSON-object mode and local full-contract/evidence validation; malformed or ungrounded output is retained and rejected. An image-grounded, native-valid candidate is automatically applied only when its model-assessed score increases by at least five points and existing high-severity issues decrease (or remain zero). Identical renders, worse/invalid/insufficient-evidence candidates, or concurrent source changes leave the original active scene unchanged. Unchanged machine poses and mounting anchors are preserved when CAD dimensions change. Prices, source procedure and inventory quantities are not changed by the visual pass.

Critiques, provider traces, labeled before/after PNGs, source hashes, candidates and original job versions are retained in `visual-reviews/`. The UI shows the critique, remaining/resolved issues and matched images, and can **Restore original scene & CAD** while that correction remains current. Scores are model judgments about visual plausibility, not engineering/physical validation. Keep a browser page open for after-capture; if it closes, generation pauses at that stage and resumes when Step 7 is reopened. Model/CAD work runs in detached workers so the HTTP server remains responsive.

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

# Request scheduling and recovery

Analysis uses one queued worker by default. Vision extraction, evidence correction,
and protocol compilation run sequentially within each run. To change analysis/design
queue concurrency, set `WORKBENCH_ANALYSIS_WORKERS=1` (serial) or `2`–`4` (concurrent)
in the server environment and restart the workbench. This does not control independent
machine or visual-review subprocesses; machine batches generate their members sequentially.

Provider requests retry transient HTTP 429/502/503/504 failures. Configure
`MODEL_REQUEST_ATTEMPTS` (1–6, default 3) and `MODEL_RETRY_BASE_SECONDS`
(1–60, default 10). Retries honor numeric or HTTP-date `Retry-After` headers,
with each wait capped at 120 seconds; otherwise exponential backoff is used.
Provider quotas may still reject serialized requests.

Invalid observation evidence receives at most one correction request to the same
vision model using the original frames. Both unvalidated candidates are retained
as `observation-candidate-1.json` / `observation-candidate-2.json` for diagnosis.
Validation is not bypassed if the correction fails.
# Step 8: semantic lab layout

After building an up-to-date Step 7 scene, open **08 / Lab layout** and choose
**Map subsystems into lab**. The fixed `compact-lab-v1` template is 8 × 6 × 3 m,
with a process bench, floor automation cell, controls/utilities zone, staging bench
and reserved 1.2 m access aisle. Step 7 remains a separate original scene.

Placement uses equipment categories/roles, shared operation IDs and actual CAD
bounding boxes. Related equipment is placed close together within permitted zones.
Bench elevations, ceiling height and footprint clearance are checked. Oversized
assets are reported unplaced instead of scaled or moved into the aisle. Consumable
instance counts follow the source scene. Missing mounts and camera/tool interfaces
remain explicit unresolved requirements; this is a subsystem location plan, not
an automatically validated mechanical assembly or robot reach simulation.

The UI provides a labeled floor plan, the original OpenIndustries viewer with
unchanged machine CAD and explicitly labeled furniture envelopes, placement
rationales, and downloadable scene/report artifacts. Plans are retained under
`runs/workbench/<run>/lab/<attempt>/`; source scene/proposal hashes invalidate stale
plans. `POST /api/runs/<run>/lab` builds a plan; `GET` reads its status. This planner
is deterministic and does not require an LLM/API call.
