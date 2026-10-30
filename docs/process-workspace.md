# Process improvement workspace

For a visual introduction, see the **[main user-flow walkthrough with screenshots](main-user-flow.md)**.

## Current judge-facing entry point

### Latest flow: automatic research and agent selection

#### Current delivery limitations

- Required human/CAD packages remain ignored local outputs under
  `runs/ha4m-fastening-release-20261028/` and
  `runs/ha4m-planet-assembly-example-20261028/`. A fresh clone does not contain
  those media or their provenance/checksum manifests. Robot renders are also
  local-only under `runs/task-robot-concepts-20261030/`.
- Tab 3 requires a completed analysis. Clicking tab 2 alone does not start it;
  use **Analyze task** in step 1. The synchronous request currently disables
  all buttons until research and agent selection finish. Background job status,
  cancellation and improved navigation feedback remain follow-up work.
- The automatic GMI decision path is implemented but was not live-verified in
  this change. Local robot rendering and media delivery were exercised; no
  additional paid inference or test-suite run was performed.

Only two prepared tasks are offered: screw tightening (default) and planet-gear
placement. Both use continuous task-matched human clips. The selector explicitly
labels them **pre-run demos**. Clicking **Analyze task** always invokes Tavily,
then the existing GMI structured-response adapter chooses between **SO-101**,
**Unitree G1** and custom tooling and chooses a planning profile. All three
assessments, supplied-source citations, unresolved gates, model trace and rationale
are persisted. No manual embodiment/profile/research selection remains. Failures
retain sources and diagnostics; no heuristic recommendation replaces the agent.

`scripts/render_task_robot_concepts.py` creates four ten-second MP4s using original
MuJoCo Menagerie robot meshes, authored position-only IK and proxy workpieces.
The local package `runs/task-robot-concepts-20261030/` retains robot source OIDs,
licenses, scene XMLs, joint poses, video hashes and IK residuals. These are pre-run
3D concept animations, not policy rollouts, validated manipulation or physics
execution. Custom tooling uses the existing task-matched CAD animations.
The prior 2D schematic renderer is removed, including from historical replay.

Render dependencies are isolated from the application environment. To reproduce,
install `mujoco`, `mujoco-menagerie`, `imageio`, `imageio-ffmpeg`, `pillow` and `numpy`
in a separate environment and run the renderer with `--output <new-directory>`.
It refuses to overwrite an existing output directory. No paid model call occurs
during rendering. The following sections describe earlier iterations.

The three-step flow now includes a task picker (fastening by default), and robot
arm / humanoid / custom-tooling candidate selection. A deterministic task-constraint
heuristic suggests a candidate; it does not establish the best physical solution.
Each embodiment scales the explicit planning allowances, with unverified cycle and
attendance assumptions. These are not supplier quotes or measured robot results.
Optional Tavily research saves cited leads without silently replacing those inputs.

Step 3 pairs human evidence with the selected concept and cost. Fastening/custom
tooling reuses the saved authored CAD animation. Other combinations generate a local
2D procedural task-sequence schematic, not new CAD, a physics simulation or a robot
trajectory. Other task selections currently show a labeled assembly-context slideshow,
not isolated human-task clips. Task, candidate reasons and animation specifications
are persisted and included in the exported analysis. No paid generation is invoked.

The homepage now focuses on **one task: HA4M screw tightening**, with no text or
numeric inputs. Three screens show the recorded task, a saved automated-station
concept, then both videos side by side with estimated cost breakdowns. Select
lean/integrated/conservative planning assumptions using buttons. The default
integrated scenario can cost more than human work; no favorable outcome is forced.

`protocol_pipeline/fastening_flow.py` reuses `evaluate_process`, snapshot helpers
and the existing checksum-indexed `runs/ha4m-fastening-release-20261028` media.
All deployment, labor, supervision, yield and volume inputs are explicit unverified
scenario assumptions. Accepted yield is assumed 100% only for conditional arithmetic;
actual accepted-output metrics remain unknown. Animation timing is not used as
machine performance. The comparison is task-processing scope, not full-process ROI.

Snapshots and exports live under `<WORKBENCH_RUNS>/fastening/`. Reopening makes no
calls. An optional Tavily action makes one basic search with no retries, saves
citations/excerpts and retains errors. It does not auto-price equipment from search
snippets or establish arm/humanoid feasibility. No live search was executed during
implementation. The same existing media must be available to run this local demo.

The broader nine-screen prototype below remains at `/process-review`.

Primary user: a lab/workshop manager or operations lead deciding whether a change
is worth implementing while maintaining output quality and safe operation.

## One local journey

Run `python -m protocol_pipeline.web` and open `/process-review`. The nine screens are:

1. **Workspace & output:** describe the process, responsible operator and goal.
2. **Import procedure:** paste/upload a text SOP, or import a completed saved
   extraction. Lines become editable steps; text import is not AI extraction.
3. **Review steps:** correct steps and confirm full-boundary coverage.
4. **Acceptance & boundary:** share the accepted output, batch boundary, quality,
   safety, space and budget requirements across both alternatives.
5. **Current baseline:** enter sourced counts, elapsed time, operator labor and costs.
6. **Proposed change:** equipment, tooling, layout or procedure; separate evidence.
7. **Compare:** four headline metrics, evidence types, supporting accounting and
   separate investment/capacity unknowns.
8. **Decision:** supported change, retain current process or insufficient evidence;
   required gates, missing inputs and next action accompany the result.
9. **Save/export:** reopen local revisions or download a checksummed decision ZIP.

The coherent example reuses the coil benchmark's manual workflow and first two
existing illustrative apparatus alternatives (manual fixture/motorized winder).
Its numbers are invented planning inputs, not video-derived measurements. The
first-pass count is unknown; eventual acceptance is not used as a substitute.
Mock reviews cannot establish physical improvement even if all values are edited.
Start a blank review to collect user-supplied evidence.

## Existing capability → connection

| Capability | Current connection |
| --- | --- |
| Extraction/compiler | Import a completed saved protocol; retain its exact JSON/hash. Failed/incomplete runs cannot supply steps. New paid analysis stays explicit in `/video`. |
| Evaluation | `evaluate_process` calculates throughput, labor, resource and recurring-cost metrics. A thin wrapper adds first-pass yield, retaining the original evaluator contract. |
| Alternatives/investment | `evaluate_alternatives` reuses the existing investment comparator. Annual demand/capacity, capital and fixed allocations remain unknown until separately supplied; no mock investment values are inherited. |
| CAD/OpenIndustries/layout | Open the existing saved-run tools from the proposed-change screen. These are optional design evidence, not validated production performance. |
| Iteration | Existing design review/restore remains in the tools. Process edits create separate immutable local revisions; source changes invalidate old comparisons. |
| Snapshots | Reuse atomic JSON, version allocation, containment, file-index and SHA-256 helpers. Exports are `process-comparison` snapshots, not video E2E imports. |

No provider call, cloud provisioning, geometry generation or simulation occurs
when using the comparison screens. Saved video snapshots can be restored in the
existing tools and their completed extraction imported into a process review.

## Accounting and recommendation rules

- Accepted outputs/hour = 3600 × accepted units / full batch elapsed seconds.
- Hands-on labor/output = total operator-seconds / eventually accepted units;
  sum distinct operators' attendance, without substituting elapsed time.
- First-pass yield = units accepted without rework / initially attempted units.
  Reworked units remain in the original denominator, not new initial attempts.
- Cost/output uses the existing evaluator's full declared recurring-cost inputs,
  including applicable overhead and rework. Missing components make total cost
  unknown; a partial subtotal is not a full cost or a guaranteed lower bound.
- Batch setup, cleanup and changeover inputs describe included overhead; they
  are not added a second time. Resource inputs keep explicit units and sources.
- A failed proposal gate prevents adoption regardless of speed. A supported-change
  result requires reviewed steps, passed gates, measured headline inputs, and no
  worsening headline metric. Conflicting metric directions require an operator
  tradeoff decision. A single batch does not establish repeatability.
- Gate status is an operator-supplied assessment, not safety certification.
- Changing output/boundary clears old numeric evidence and gate approvals. New
  SOP/extraction imports also clear performance values and approvals. Changed
  proposal text invalidates unchanged candidate quantities and candidate gates.

## Persistence and failures

Reviews live at `<WORKBENCH_RUNS>/processes/<id>/v000001/…`; the atomic current
pointer selects a finalized revision. Saves invalidate stale comparisons;
revision conflicts reject overwrites from older browser tabs. Evaluation failures
retain inputs and error details, support retry and remain exportable. Reopening
never regenerates models. ZIPs contain `decision.md`, `review.json` (including
source captures, provenance and calculations) and a checked `snapshot.json`.

The first complete experience connects text/saved extraction and deterministic
evaluation. It does not automatically measure resources from videos, interpret
arbitrary PDF SOPs, choose robots or validate machine performance. Investment
input editing and direct linking of CAD artifacts into process exports remain
incremental connections; the original tools and their evidence exports are retained.
