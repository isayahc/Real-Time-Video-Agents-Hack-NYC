# Forma apparatus generation → OpenIndustries scene

The `build` command consumes `apparatus-request.json` from protocol analysis, calls Forma Core, validates the Hardware IR and imports it with OpenIndustries' native `importForm`. It creates/reads an empty planning room through the **actual local stdio MCP server**, then exports a portable scene containing the apparatus with the native workspace APIs.

It can attach design artifacts to a saved prediction/revision digest. Revision rationale and proposed changes are included in the synthesis prompt. Numeric accounting records remain unchanged until explicit updated predictions or measured outcomes are supplied.

## Runtime setup

Python 3.11+, Node 22+ and both compatible runtimes are required. The tested Forma Core version is 0.3.6. Use an installed package or the existing source checkout:

```bash
python -m pip install -e '.[design]'
```

For a Forma source checkout, install its dependencies and pass `--forma-root /path/to/forma-oss` instead. The adapter runs the native Python API, not a hosted backend. The tested OpenIndustries source package reports 0.1.1. Run `npm ci` in that checkout, then pass `--oi-root /path/to/open-industries`. The small `.mts` bridge is packaged with this Python project because OI's native import/export functions are TypeScript.

## Live generation

Configure the selected provider's credentials through Forma's normal environment/configuration. Credentials are not CLI arguments. Choose an explicit provider/model supported by Forma; no hosted model availability is assumed.

```bash
python -m protocol_pipeline build \
  --requirements runs/t1-001/apparatus-request.json \
  --output runs/t1-design-001 \
  --oi-root /path/to/open-industries \
  --mode live --provider '<configured-provider>' --model '<configured-model>' \
  --brief 'Generate an apparatus implementing these protocol requirements' \
  --store runs/process-loop --prediction p1
```

The source prediction is optional; provide both `--store` and `--prediction` when attaching to a loop. For a saved revision such as `p2`, the same command automatically includes its revision rationale/changes in the prompt. The requirements remain a separately supplied protocol contract; a design link does not independently prove they describe the same task as the prediction.

Live mode uses Forma's strict production preflight/fallback controls. Failed/fallback/simulation output is rejected. Successful artifact creation still does not establish requirement coverage or physical readiness. **Live generation has not been verified here because no provider credentials are configured.**

## Offline integration checks

Explicit simulation mode calls the real Forma generation API with its built-in deterministic fixture generator:

```bash
python -m protocol_pipeline build \
  --requirements examples/design-handoff/coil-requirements.json \
  --output runs/forma-simulation-check \
  --forma-root /path/to/forma-oss --oi-root /path/to/open-industries \
  --mode simulation --brief 'Exercise the apparatus generation and scene pipeline'
```

Forma's fixture currently returns a generic electronics/lock example for this prompt. This checks the adapter and envelope geometry import; it is **not a newly synthesized coil apparatus** or a physical simulator.

To verify the existing CW-02 concept itself:

```bash
python -m protocol_pipeline build \
  --requirements examples/design-handoff/coil-requirements.json \
  --output runs/cw02-import-check \
  --forma-root /path/to/forma-oss --oi-root /path/to/open-industries \
  --mode replay --project snapshots/v2/coil-winder.forma.json \
  --brief 'Verify the existing CW-02 concept through the native import pipeline'
```

Replay validates/imports the supplied artifact without invoking generation. `coil-requirements.json` is a labeled concept handoff from the existing design discussion; it is not a video-backed protocol. The emitted ingestion request is accepted directly when the real video run is available.

## Artifacts and limits

Every output directory must be new. Outputs preserve:

| File | Meaning |
| --- | --- |
| `requirements.original.json` | Original handoff bytes |
| `build-input.json`, `synthesis-prompt.txt` | Typed mode, requirements, scene planning inputs, source prediction digest and revision context |
| `apparatus.forma.json` | Native Hardware IR wrapped for import |
| `forma-result.json` | Core version, schema validity, deterministic validation and BOM/component counts |
| `apparatus.oi.json` | Portable native scene with embedded apparatus geometry/retained Form data |
| `oi-result.json` | Actual local MCP room ID, native import/roundtrip, geometry representation and warnings |
| `design-manifest.json` | Artifact hashes, source prediction link, mode and explicit unresolved coverage/physical validation |
| `build-failure.json` | Safe failed-stage marker when execution stops |

The MCP room is an empty local shell. The populated apparatus is in the portable file, created with native APIs; there is no local MCP tool for replacing that room's instances. The adapter does not edit the MCP room file or create a cloud scene. Cloud scene tools require separate Supabase configuration/login and immutable uploaded asset references.

Inline CAD meshes or mechanical placements/render dimensions must exist for native geometry import. OI can display approximate envelopes when fabrication CAD is unavailable. A native `CAD mesh` label describes the imported data format; CW-02's meshes remain schematic concept geometry, not fabrication specifications. The default room/pose are planning assumptions; clearance, collision, station routing and plant feasibility are not solved.

BOM counts/prices remain design data. No BOM price, rendering or model-generated power estimate is automatically promoted into observed cost/resource measurements. Requirement coverage and physical equivalence require review and testing.

## Verified here

`integration-checks.json` records the executed local checks:

- Real Forma simulation generation → 5 BOM lines, approximate envelopes, actual OI MCP room creation/read, native portable roundtrip.
- CW-02 replay → 12 BOM lines retained, 33 mesh parts, actual OI MCP room creation/read, native portable roundtrip.
- Both are schema-valid and have deterministic validation findings (`deterministic_is_valid: false`). Neither establishes electrical/mechanical completion, requirement coverage, measured performance or physical equivalence.
- 53 Python tests pass. Additional CLI integration runs exercised the real optional runtimes; live provider calls were not made.

The builder is separate from data collection and the numerical controller. It links artifacts to that controller and carries revision instructions forward; it does not autonomously invent new designs, collect observations or loop indefinitely.
