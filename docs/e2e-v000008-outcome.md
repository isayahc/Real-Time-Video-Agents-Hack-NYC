# Completed live E2E demonstration: v000008

On 2026-10-28, one user-authorized fresh live run completed from commit `2eec7f9`:

```powershell
python scripts/run_e2e.py --snapshot snapshots/e2e/v000006/snapshot.json --visual-passes 1
```

The permitted BridgeData input and settings were inherited; observations, protocol,
proposal, CAD and critique were regenerated. Requested routing was Nebius
`nvidia/Nemotron-3.5-Super-VL` for vision and GMI `openai/gpt-6-astra` for reasoning
and OpenCode CAD authoring. This is a BridgeData demonstration, not a tested HA4M
fixture intervention. See [source attribution](bridgedata-small-sample.md).

## Verified result

- Snapshot: `snapshots/e2e/v000008/snapshot.json`, status **completed**.
- Workbench run: `13a32fa0c0164a099640baef77b8a36e`.
- All seven stages completed: preflight, extraction, proposal, CAD, scene,
  visual review and lab. Elapsed stage span: approximately **12 minutes 12 seconds**.
- `protocol_pipeline.snapshots.verify_snapshot` successfully verified all **192**
  indexed files after completion. No missing temporary checkpoint reference.
- One visual correction pass was applied. Final critique: **50**,
  **needs_improvement**, with a remaining high-severity geometry issue.
- Final lab has isometric, reverse and top render artifacts. The lab isometric
  image was inspected and shows the equipment on a workbench and an inventory area.

The critique reports that gantry, gripper and vision mounts remain insufficiently
distinguishable and that reverse/top critique views did not show equipment. Thus
pipeline completion does not establish satisfactory CAD completeness or view
coverage. The reported score is a model judgment, not measured physical quality.

## Global milestone

**One uninterrupted live video → observations → procedure/proposal → native CAD →
scene → visual review → lab workflow is now demonstrated with verified artifacts.**
This is one successful execution, not a repeatability rate or guaranteed future
outcome. Physical execution, accepted-product equivalence and intervention savings
remain unverified. No ROI claim follows from this result.

Offline suite at the run's code revision: **273 passed, 4 skipped, 12 subtests
passed**. This follow-up adds documentation only. Historical v000006/v000007 remain
unchanged. Outputs stay local; no footage or trace was published.

Next smallest action: review this saved snapshot in the workbench and choose the
demo's presentation boundary, without another generation run or fixture expansion.
