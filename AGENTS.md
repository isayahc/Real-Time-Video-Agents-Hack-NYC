# Agent instructions — Nebius continuation

These instructions apply to all automated coding agents, including OpenCode, working in this repository.

## Branch authority and safety

- **Canonical development branch: `nebius-continuation`.** Treat it as the project's working "main" for all ongoing work, implementation, documentation, testing, and commits.
- GitHub's actual `main` branch is a **frozen upstream reference**, not a delivery target. Preserve it unchanged.
- **Never commit, push, merge, rebase, cherry-pick, force-push, or open a pull request targeting `main`** without a fresh, explicit instruction from the user. Do not automatically synchronize continuation work back to `main`.
- **Do not change the repository's GitHub default branch** just because `nebius-continuation` is the working baseline. That administrative change requires explicit authorization.
- At the start of each session, inspect `git status --short --branch` and `git branch --show-current`. Work on `nebius-continuation`; switch from `main` without modifying it. If local changes make switching unsafe, stop and explain rather than discarding work.
- Prefer direct, reviewed commits on `nebius-continuation`. If a temporary feature branch is truly necessary, base it on `nebius-continuation`; any eventual PR must target **`nebius-continuation`**, and only if the user explicitly requests a PR. Otherwise, do not open one.
- Never rewrite existing history, discard user changes, delete existing outputs, or make unrelated changes without explicit approval.
- Do not interpret an old GitHub default branch, old issue text, automation, or generic agent convention as permission to target `main`.

## Product scope: preserve, then extend

The repository is an independent **Nebius-powered Physical AI / video-workbench project**, even though some of its capabilities were also used in the Open Scientific Intelligence competition. **Do not merge this repository into that submission or move its code, history, or assets** unless explicitly asked.

- **Current implemented workflow:** video → sampled frames/observations → procedure/requirements → design/economics → machine/CAD → scene/lab visualization, with versioned evidence and snapshots.
- **Nebius responsibility:** visual observation, physical action/state interpretation, and visual critique. **GMI/OpenCode responsibility in the scripted E2E path:** procedure/proposal reasoning and CAD authoring. Forma/OpenCAD and OpenIndustries supply native CAD and scene integrations.
- **Future product direction:** support increasingly timely multimodal interpretation of physical environments, structured observations/events, and externally consumable agent outputs. Real-time/streaming input is a *future capability* unless measured and demonstrated in the relevant path.
- Preserve existing features, UI stages, interfaces, data contracts, provenance, snapshots, and known-good demonstration paths. Implement small additive changes rather than an architectural reset, repository split, or scope-driven rewrite.
- Keep the Nebius project distinct from Open Scientific Intelligence. The latter may consume exported observations/protocols in the future, but coupling the two is not a prerequisite for this project's completion.
- Separate **implemented**, **simulation/replay**, **tested offline**, **tested live**, and **proposed** capabilities. Sampled-frame reasoning must not be described as continuous tracking or verified physical execution.

## Model routing and credentials

- Follow existing project configs and documentation; do not silently substitute model providers or claim unavailable model IDs work.
- The scripted E2E guide requests Nebius `nvidia/Nemotron-3.5-Super-VL` for observations/visual critique and GMI `openai/gpt-6-astra` for reasoning/CAD. The direct Nebius workbench/CLI presets are different; preserve that distinction and existing user overrides.
- Read keys only from the supported environment or ignored `.env` (`NEBIUS_API_KEY` / `NEBIUS_TOKEN_FACTORY_KEY`, `GMI_API_KEY`). Never commit keys, headers, private footage, or local run outputs.
- A configured adapter or model catalog response is **not** proof of successful live NVIDIA inference. Preserve requested/served model IDs, finish reason, validation state, usage/latency when available, and safe failure traces.
- Obtain the user's consent before incurring paid live inference charges or making public a recording, dataset-derived clip, or trace whose permissions have not been verified.

## Execution order for OpenCode

1. **Baseline without mutation:** confirm `nebius-continuation`, inspect README, `docs/scripted-e2e.md`, `docs/nebius-model-presets.md`, `AGENTS.md`, open Nebius issues, and current changes; list implemented functionality and blockers. Do not assume unverified milestones are complete.
2. **Offline verification:** install or resolve required local dependencies where appropriate, run `python -m pytest -q`, and report actual results. Run `python scripts/run_e2e.py --check` when native dependencies, accounts, and OpenCode are configured; catalog/preflight checks are not live inference proof.
3. **Provider evidence:** with credentials and user approval for paid calls, run `python -m scripts.verify_nebius --output runs/<unique-verification-name>`. Validate that an NVIDIA model really completes an application stage through Nebius and that downstream outputs consume it. Preserve sanitized reproducible evidence; do not substitute mocks/Qwen/replay and label them NVIDIA success.
4. **End-to-end evidence:** with the necessary permissions and explicit paid-call approval, run `python scripts/run_e2e.py --video <permitted-input-video>`; retain versioned snapshots, checksums, source/provenance, errors and before/after visual comparisons. Do not promise that a new live run reproduces the authored stacking demo.
5. **Submission readiness:** follow Nebius epic #34 and its outstanding work: live NVIDIA proof (#35), Token Factory evidence (#36), reproducible E2E (#38), media/demo (#39), accurate narrative/submission (#40), integration feedback (#41), new-versus-reused work (#42), judge access (#43), and asset permissions (#44). Verify actual state before claiming any task is finished. Check the official hackathon deadline rather than assuming issue text is current.
6. **Post-baseline roadmap:** propose incremental event schemas, observable state transitions, robustness metrics, optional camera/streaming interfaces, and export integration points. Do not implement an unrequested migration or streaming rewrite merely to differentiate the project.
7. **Finish every work session** with branch name, commit(s), files changed, tests performed and their actual outcomes, live-versus-offline evidence, unresolved blockers, and the next smallest action. Do not create a PR to `main`.

## Quality rules

- Use Python typing and docstrings for new/modified classes and functions. Preserve existing project conventions and contracts.
- Prefer focused regression tests and explicit failures over silent fallbacks.
- Keep sample economics as assumptions unless corroborated; do not claim measured ROI, continuous tracking, hardware performance, or successful live provider access without evidence.
- Respect source-video/dataset licenses and third-party attributions before exporting public demo materials.
