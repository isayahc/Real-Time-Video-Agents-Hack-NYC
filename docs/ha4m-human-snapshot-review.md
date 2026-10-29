# Human-input snapshot: media complete, semantic review failed

## Evidence

- Source: HA4M IDU001V001 action 9; 253 consecutive RGB frames, nominal 8.433 s.
  Source provenance and attribution accompany the input. No new participants.
- v000009: authorized live extraction, proposal, native CAD, scene and visual review
  completed; machine-video export failed due to nested synchronous Playwright contexts.
  All 186 indexed artifacts verify; the snapshot remains failed and unchanged.
- Export now runs in a separate process. A real native export succeeded with the
  parent's Playwright context active, reproducing the previously failing arrangement.
- v000010: new **offline media/lab continuation**, reusing v000009's live artifacts.
  MP4/GIF export and lab rendering completed with no new inference. All **196**
  indexed artifacts verify. This is not a fresh uninterrupted live E2E result.
- Imported v000010 into the workbench as `7eea6989083a4cddadd7df4e87b16d8c`.
  Browser playback of both source (8.433 s) and machine video (12 s) succeeded.
  Screenshot: `.playwright-mcp/ha4m-v10-content-review.png` (local).

## Why this is not the requested proper automation demo

Vision interpreted the joining sequence as lifting, inspecting and replacing one
white object, rather than joining two gearbox subassemblies. It also promoted
the experimenter's numbered card into a task action. Protocol/proposal/CAD inherited
that scope error. A successful media export cannot correct the meaning of the task.

The saved visual review retained the original CAD (`kept_original`); the after
critique scored 75 but still reported unclear grippers/cameras and a loose-looking
component. That score is not task fidelity, mechanical verification or acceptance.
The exported video renders existing scene keyframes, not validated joining kinematics.

**Presentation acceptance: failed.** The package is available for diagnosis, not
as proof that human gearbox joining was automated. Physical quality and savings
remain unverified.

## Next smallest correction

Pass explicit, separately attributed task context into extraction: publisher action
9 is joining block 2 onto block 1; the numbered card is experiment metadata. Preserve
two subassembly identities and uncertain contacts rather than inventing geometry.
Review the resulting observations/protocol before spending on downstream CAD.
That scoped model retry requires fresh paid-call approval; none was made here.

Code changes: isolated video exporter plus `scripts/finish_snapshot_media.py` for
verified, append-only, explicitly offline continuation. Full suite: **275 passed,
4 skipped, 12 subtests passed**. Workbench server restarted to load the new config.
