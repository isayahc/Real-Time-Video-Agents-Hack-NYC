# GPU execution → static Vercel playback

Run GR00T inference and SONIC humanoid simulation on a suitable GPU host, retain
their outputs, then export a static site. Vercel serves HTML, JSON, images and video;
it needs no GPU, model credentials, inference endpoint or running Python backend.

## Current state

- **Implemented:** typed saved-run receipt, artifact integrity/lineage validation,
  allowlisted static export, video/frame viewer, model provenance and failure labels.
- **Tested offline:** export and viewer contracts, including explicitly synthetic
  test data. Exporting files does not execute either model.
- **Tested locally with real models:** `scripts/g1_local_smoke.py` captured a
  MuJoCo camera/state observation, ran one GR00T action chunk on the laptop GPU,
  then consumed it through original SONIC ONNX inference in MuJoCo. All 40 steps
  completed (0.8 simulated seconds). Task success remains **not evaluated**.
  The exporter itself does not execute models.
- Existing SO-101 scripted simulation and workbench snapshots are separate evidence.

The inspected laptop is an RTX 4070 Laptop GPU with 8188 MiB VRAM. NVIDIA's
[N1.7 requirements](https://github.com/NVIDIA/Isaac-GR00T#installation) specify
16 GB+ for inference; memory offloading/quantization has not been tested here.
The default N1.7 model also loads the gated Cosmos-Reason2-2B backbone.
The published base model's `embodiment_id.json` does not list `unitree_g1_sonic`.
A compatible task-trained checkpoint and matching SONIC latent space are required.
Third-party checkpoints exist; for example, BonesSeed-V2 explicitly describes
memorized prompts and relaxed fall terminations, not validated task generalization.
The local diagnostic selects `wsagi/GR00T-N1.7-G1-SONIC-BonesSeed-V2`
at `b2c6b57e0780ead42cf12cdcdf1d67dd210e142d`, paired with the default
`nvidia/GEAR-SONIC` controller at `6733128a3d8a523b1418b06bca3cdf61c8b0987f`.
The gated Cosmos backbone download succeeded after a fresh cache-bypassed access
check returned HTTP 200. Its revision is `9ce19a195e423419c349abfc86fd07178b230561`.
The bounded test requests `squat`: one 40-step GR00T chunk, at most 0.8 simulated
seconds of SONIC state-feedback control, and no task-success evaluation.
It preserves the checkpoint's legacy state layout and uses an approximate camera,
BF16 GR00T loading with SDPA attention, and CPU ONNX/MuJoCo execution.

## Execution boundary

| Layer | GPU-host responsibility | Retained evidence |
| --- | --- | --- |
| GR00T | Camera/state + task → compatible action chunks | Exact checkpoint/revision, observations, predicted actions |
| SONIC | Actions + robot state → whole-body control in simulation | Matching checkpoint/config, consumed actions, joint/state trace |
| Recorder | Capture the actual simulation and measured timing | MP4, before/after frames, failures, task outcome |
| Vercel | Display only saved outputs | Manifest, selected artifacts, checksums |

Use the upstream [G1 VLA workflow](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/vla_workflow.html)
and [inference guide](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/vla_inference.html).
For that workflow the action space is 64 motion-token values plus 7 values per hand.
Use `UNITREE_G1_SONIC`, not the separate decoupled `UNITREE_G1` workflow or SO-101.
The upstream inference launcher has a `--sim` option. Hardware defaults must not be
used for this simulation path. No paid host is provisioned by the export command.

## Export a saved run

The checked-in receipt honestly records the blocked local preflight:

```bash
python -m protocol_pipeline.gpu_replay \
  --manifest examples/gpu-replay/blocked.json \
  --output runs/g1-static-preflight-001
```

Open `runs/g1-static-preflight-001/index.html` directly or serve it with any static
server. It deliberately contains no simulated-success video. Choose a new output
directory each time; existing outputs are never replaced.

After actual execution, the recorder must supply a manifest conforming to
`protocol_pipeline.gpu_replay.GPUReplay`. Generate its JSON Schema with:

```bash
python -c "import json; from protocol_pipeline.gpu_replay import GPUReplay; print(json.dumps(GPUReplay.model_json_schema(), indent=2))"
```

Required run fields include `run_id`, timezone-aware `recorded_at`, `task`, `gpu`,
`source_revision`, `status`, `evidence`, `simulator`, `limitations`, `attribution`,
`gr00t`, `sonic` and `artifacts`. Each artifact has a relative `artifacts/...` path,
role, SHA-256, byte count and caption. Stage input/output lists reference those
exact indexed paths. Record immutable model revisions or checkpoint checksums.

To mark a run `completed`, both stages must be completed with identities and:

1. GR00T inputs reference an `observations` artifact.
2. GR00T outputs reference an `actions` artifact that SONIC consumes.
3. SONIC outputs reference a `controller_trace` and simulation `video` or `frame`.

Use `evidence: recorded_inference_simulation` only for actual recorded inference.
Use `synthetic_test` for fixtures; the viewer keeps that label even if all files and
links validate. Preserve partial execution as `failed`; use `blocked` plus
`no_execution` when neither model ran. Task `outcome` is separate from process
status: completion does not imply success, and unevaluated outcomes stay explicit.

The exporter verifies file bytes and references. It cannot prove that a producer's
model/execution declarations are true, nor that a controller trace used a video's
exact states. Review the recorded trace and timing before making that claim.
Only explicitly indexed files are copied; sibling checkpoints, `.env`, cache files
and other raw logs are excluded. Select public-safe artifacts and attribution.

## Publish

For a standalone Vercel static project, deploy the exported directory with its
generated `vercel.json`. For the existing judge site, copy the export under a new
route such as `humanoid/` in a **new staging copy** of the existing public bundle.
Keep its walkthrough and viewer assets, add the navigation link, regenerate the
site-level checksum index and deploy using the existing Vercel project linkage.
The nested export's manifest describes only that run. Its `vercel.json` applies
when deployed standalone; the containing site owns configuration when nested.

Publishing a blocked receipt documents readiness, not execution. Publish real
results only after the GPU run and its evidence have been checked. Historical
versions remain immutable; a new result belongs in a new export directory.

## Initial readiness publication on October 30, 2026 (UTC)

- Published readiness receipt: https://mapped-assembly-judge-demo.vercel.app/humanoid/index.html
- Vercel deployment: `dpl_EqdsAePSwBDki6y7UVvsoWxd7dbv`.
- Full offline suite after initial implementation: **321 passed, 4 skipped,
  12 subtests passed**. Subsequent Windows-console regression and checksum-index
  fix: **13 focused tests passed** with `python -m pytest -q tests/test_gpu_replay.py`.
- `python scripts/run_e2e.py --check`: **passed**, including native setup and
  provider catalogs; `inference_compatibility_verified` remained **false**.
- Playwright: anonymous desktop (1440×1000) and mobile (390×844), explicit blocked
  state, working manifest link, no page errors or document-width overflow.
- Local-only synthetic PNG/MP4 fixture rendered and played with its synthetic
  label. It was not published as an inference result.
- All **15 indexed public files** matched their byte counts and SHA-256 hashes.
  Vercel's root configuration file is intentionally excluded from the public
  checksum index because Vercel does not serve it.
- Existing walkthrough and both original comparison videos still played after
  deployment. Browser evidence and deployment receipt are retained locally under
  `runs/gpu-replay-ui-20261030/`.
- **No GR00T inference, SONIC execution, paid GPU job or physical motion occurred.**
  This statement describes the initial readiness publication above.
- Subsequent full offline check: **322 passed, 4 skipped, 12 subtests passed**
  (`python -m pytest -q`, 63.89 seconds).

## Recorded local diagnostic: attempt02

- GR00T: finite `(1, 40, 64)` motion tokens; **3.421 seconds** measured inference,
  **35.590 seconds** loading, **6,350,513,152 bytes** peak PyTorch GPU allocation.
- SONIC: **40 control steps**, average decoder time **2.269 ms** on CPU. This
  excludes physics/rendering and does not establish end-to-end real-time speed.
- Pelvis height: **0.734 m** initially, **0.723 m** finally, minimum **0.720 m**.
  The 0.4 m stop threshold was not crossed; this is not a balance benchmark.
- Verified observation/action hashes, exact raw and snapped token consumption,
  finite state traces, and MP4 decoding (**40 frames, 50 fps, 640×480**).
- Attempt01 failed because the upstream processor rejected `state_noise_std`
  and `state_noise_prob`. Attempt02 explicitly excludes those custom training
  augmentation fields during inference. Original checkpoint files are unchanged.
  The local source patch is included in the saved receipt, alongside BF16 loading
  settings and the pinned Cosmos revision. Training with this patch is unsupported.
- Raw evidence: `runs/g1-local-20261030-attempt02/`; validated receipt:
  `runs/g1-local-20261030-receipt02/run.json`; public export:
  `runs/g1-local-20261030-export02/`. Attempt01 is retained separately.
- New judge-site staging copy: `runs/judge-demo-gpu-static-20261030-v3/`.
  Its `humanoid/` route contains the recorded diagnostic; the initial blocked
  receipt remains under `humanoid-preflight/`.
- This is **local inference + simulation**, not Nebius-hosted inference,
  continuous GR00T replanning, a successful squat, or physical execution.
- Published: https://mapped-assembly-judge-demo.vercel.app/humanoid/index.html
  (deployment `dpl_4BxkJsemvhLG84Th6FdkDbgqBWsM`). All **29 public indexed files**
  matched their byte counts and SHA-256 hashes. Anonymous Playwright checks at
  **1440×1000** and **390×844** confirmed playback through the entire 0.8-second
  clip, correct evidence/outcome labels, loaded images and no horizontal overflow.
  The existing walkthrough and both comparison videos still played.

The experimental runner requires the pinned upstream trees/checkpoints and
separate installed inference/simulation environments documented in the receipt.
Run `prepare` once into a new directory; then run `infer` and `simulate` against
that same directory with their respective Python environments:

```bash
python scripts/g1_local_smoke.py prepare --root /path/to/g1-local --output runs/new-attempt
python scripts/g1_local_smoke.py infer --root /path/to/g1-local --output runs/new-attempt
python scripts/g1_local_smoke.py simulate --root /path/to/g1-local --output runs/new-attempt
```

Retain logs and the exact local compatibility patch. The runner is a bounded
diagnostic, not a replacement for the upstream G1 deployment workflow.
