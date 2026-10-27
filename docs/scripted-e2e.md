# Scripted workbench E2E and versioned snapshots

## Open saved outputs in the existing workbench

Use **Import snapshot · populate this workbench** above the wizard navigation.
Enter a local snapshot directory/`snapshot.json`/`snapshot.zip` path, or upload a ZIP.
The importer verifies the indexed checksums and restores the saved run under a new
ID in the normal saved-run list. Video, frames, extraction, proposal/costs, machine
CAD, and available scene/lab artifacts open in the same seven-step UI, with scene and lab combined. No inference,
archived Python execution, or regeneration occurs. Partial snapshots retain failed
or missing stages; in-flight stages become interrupted failures rather than resuming.
The original snapshot is not modified. Both scripted E2E snapshots and the full-run
archive from PR #50 are supported; source-video-only or CAD-only ZIPs are not full
workbench snapshots. ZIPs may contain at most 1 GiB of expanded content.

Run the full workbench without browser clicks:

```bash
python scripts/run_e2e.py --video /path/to/procedure.mp4
```

The runner samples frames, extracts observations and a protocol, compiles resource reports, generates an autonomous proposal and economics, authors each machine through **OpenCode → GMI → OpenCAD**, validates/exports CAD through Forma, builds the native OpenIndustries scene, captures three real WebGL views, runs visual critique/correction with matched after captures, and builds and renders the final lab layout. A failed stage exits nonzero and retains its artifacts. It calls the same services as the web workbench without automating UI button selectors.

| Stage | Provider | Model |
| --- | --- | --- |
| Video observations and visual critique | Nebius | `nvidia/Nemotron-3.5-Super-VL` |
| Protocol extraction and autonomous proposal | GMI | `openai/gpt-6-astra` |
| CAD authoring and corrections | GMI through OpenCode | `openai/gpt-6-astra` |

These are requested IDs, not a claim that both accounts currently serve them. Preflight checks both authenticated catalogs and the OpenCode connection. An unavailable ID stops the run without a substitute. Catalog presence does not establish inference/structured-response compatibility. The web UI's existing model defaults are unchanged.

## Setup once

From the repository root:

```bash
python -m pip install -e ".[e2e,design,test]"
python -m playwright install chromium
```

Install FFmpeg/FFprobe, Node.js, OpenCode CLI, and the native Forma/OpenCAD and OpenIndustries dependencies described in [the workbench guide](video-workbench.md). Linux may also require `python -m playwright install-deps chromium`. Set `FORMA_ROOT` to the Forma checkout supplying `cad.py`, and `OPENINDUSTRIES_ROOT` to a compatible OpenIndustries checkout with npm dependencies installed.

Installing the Forma Python package may not install its hardware skill. Both preflight and direct CAD builds now use the same resolver: `FORMA_CAD_ADAPTER_PATH`, then `FORMA_ROOT` (or the sibling `forma-oss` checkout), then installed-package/cwd skill locations. An explicitly invalid adapter path is an error. On Windows PowerShell, for your existing checkout:

```powershell
$env:FORMA_ROOT = Join-Path $env:USERPROFILE 'forma-oss'
# Alternatively, select the adapter directly:
$env:FORMA_CAD_ADAPTER_PATH = Join-Path $env:FORMA_ROOT '.agents\skills\forma-hardware\scripts\cad.py'
```

Native CAD exporters run in a short temporary directory instead of the deeply nested snapshot attempt directory. All generated artifacts and partial failure/timeout diagnostics are copied back before cleanup. If your system temp directory itself is long, select a short writable root such as `$env:WORKBENCH_CAD_TEMP_ROOT = 'C:\cad-tmp'`. The worker creates that directory if needed. It exports and validates the complete STEP assembly and each component's native mesh itself; adapters without optional `articulated_bodies` metadata remain usable. The adapter's own STEP/metadata are retained separately as diagnostics, and cannot replace the complete assembly output.

Set both `NEBIUS_API_KEY` (or `NEBIUS_TOKEN_FACTORY_KEY`) and `GMI_API_KEY` in your environment or repository `.env`. The script loads `.env` from the current directory and does not copy it into snapshots. The repository `opencode.json` registers the GMI model. The managed OpenCode server starts automatically if its CLI is on PATH, with an absolute `OPENCODE_CONFIG` path so external snapshot directories work too.

With **OpenCode V2**, the adapter starts its own authenticated loopback server on
an allocated port, inheriting the project environment. Its generated password stays
in memory and is redacted from `runs/opencode-v2.log`. The owned process tree stops
when the worker exits, including the Windows npm launcher. The user's shared
OpenCode service is not restarted or reconfigured. Saved V2 sessions can be reopened
from the same OpenCode database after the private server restarts.

To reuse an explicit V2 server, start it with this repository's configuration and
provider environment, set `MACHINE_OPENCODE_URL`, and supply its `OPENCODE_PASSWORD`
(or compatible `OPENCODE_SERVER_PASSWORD`). Authentication failures are explicit.
V2 automatically reloads configuration; server environment changes require starting
the selected server with that environment. Existing V1 installations retain their
legacy adapter path; the installed CLI determines the expected server API version.

The V2 CAD session selects the exact provider/model at creation and denies tool
execution; CAD source is returned as JSON for the existing native validation worker.
Inputs retain their message identity before submission. Status-read failures do not
resubmit paid prompts; completed turns must match the submitted input and requested
model. Startup/catalog success is not proof of live CAD authoring compatibility.

Check installation and account catalogs without inference:

```bash
python scripts/run_e2e.py --check
```

This builds the native viewer, launches Chromium, verifies WebGL2, checks CAD runtime presence and provider/model catalogs. It creates no snapshot, but may start the managed OpenCode server. It does not install missing tools.

## Append the next version

Output defaults to `snapshots/e2e/v000001/`, then `v000002/`, etc. Atomic directory creation prevents concurrent invocations overwriting each other. Generated versions are gitignored and never auto-pushed.

```bash
# Import the video from PR #50 and regenerate every stage.
python scripts/run_e2e.py \
  --snapshot snapshots/workbench-20261022-184138Z-a90ec05

# Inherit the latest finalized version's video/settings and append another run.
python scripts/run_e2e.py

# Use any previous snapshot, optionally in another output directory.
python scripts/run_e2e.py \
  --snapshot snapshots/e2e/v000001/snapshot.json \
  --snapshots-dir /path/to/experiment-snapshots

# Override inherited settings with JSON or flags.
python scripts/run_e2e.py --config examples/e2e/config.json --visual-passes 3
```

`python -m protocol_pipeline.e2e` is equivalent. `--video` and `--snapshot` are mutually exclusive. With neither, the latest finalized snapshot supplies the input. A failed/interrupted version can supply its intact source/settings; a running version is never auto-selected. Numbering advances above **all** version directories, including unfinished ones. No input on the first run is an error.

Each invocation **reruns all stages from the saved video**. It does not reuse old model results, execute archived Python or resume old OpenCode sessions. Snapshots are portable between machines and keep prior results for comparison; each new run incurs fresh inference costs. `--visual-passes` is a maximum of 1–10. Each pass may revise one CAD asset plus layout; further passes run only after an accepted correction. The loop ends if no change is proposed or the candidate does not improve. A successful exit means the pipeline completed, not that quality or physical feasibility is verified. Critiques and unresolved issues remain in the output. Integrated workcell/assembly refactoring is still tracked in #48.

## Serialization contract

| Path inside a version | Contents |
| --- | --- |
| `snapshot.json` | Schema/version, parent fingerprint, resolved config, source checksum, runtime provenance, stage status/timing, final status, every artifact's relative path/bytes/SHA-256 |
| `input/source.*` | Original video |
| `workbench/<run-id>/ingested/` and `extracted/` | Timestamped frames, observations, protocol, provider traces, compiled reports |
| `workbench/<run-id>/autonomy/` | Proposal, cost assumptions and evaluated economics |
| `workbench/<run-id>/machines/` | Jobs, CAD programs, Python source, STEP/STL, native checks, meshes, provider candidates and diagnostics |
| `workbench/<run-id>/scene/` | Portable native scenes, animation, placements and geometry hashes |
| `workbench/<run-id>/visual-reviews/` | Before/after PNGs, serialized cameras, image hashes, critiques, candidate/acceptance records and summary |
| `workbench/<run-id>/lab/` | Lab scene/report, three PNGs and serialized camera metadata |

The input contract uses relative paths and verifies **every indexed artifact** before reuse. Move the whole version directory and supply its `snapshot.json`; the original video location and server process are unnecessary. Some native-worker diagnostics retain absolute runtime paths as historical records; those paths are not used for rerunning a snapshot. Do not edit a finalized version: use `--config` or `--video` to create another. Checksums detect changes but are not signed attestations.

Legacy `snapshot.zip` input reads only its single `runs/workbench/<id>/source.*` member, checks adjacent ZIP/video checksums when present, and rejects ambiguous multi-video archives. It never extracts archive paths or executes bundled source. New snapshots are directories with JSON manifests. They include source video and detailed model/build evidence, so choose what to share deliberately.

On an exception or Ctrl+C, the manifest is finalized as failed/interrupted with stage checkpoints. A hard kill may leave a `running` directory, which later invocations preserve and skip as automatic input. Interrupted computation is not resumed automatically. The artifact index is finalized after browser/worker cleanup.

## Regression scripts

```bash
# Offline suite, no provider requests.
python -m pytest -q

# Deterministic model responses; real FFmpeg, OCCT/OpenCAD, Forma,
# OpenIndustries and Chromium render/correction/lab stages.
WORKBENCH_NATIVE_E2E_TESTS=1 WORKBENCH_NATIVE_CAD_TESTS=1 \
  python -m pytest -q tests/test_e2e.py tests/test_opencad_program.py tests/test_scenes.py
```

The native test verifies exact provider/model routing, real STEP output, matched before/after cameras, changed render hashes, accepted correction, lab renders and final checksums. It tests integration, not the quality or availability of live models.

Pytest discovery is restricted to `tests/`; expanded historical snapshots under `runs/` or `snapshots/` are excluded. The symlink tampering test skips only when Windows reports missing symlink privileges (WinError 1314); it still runs on capable systems. No privilege or Developer Mode changes are required by the suite.

Equivalent PowerShell native-test invocation:

```powershell
$env:WORKBENCH_NATIVE_E2E_TESTS = '1'
$env:WORKBENCH_NATIVE_CAD_TESTS = '1'
python -m pytest -q
```
