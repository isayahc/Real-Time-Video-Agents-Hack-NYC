# Fresh live E2E attempt: v000007

Run on 2026-10-28 from merged commit `fa7dabb`, with user authorization for one
fresh paid run. Input/settings inherited from v000006's permitted BridgeData clip;
all model stages regenerated, with one maximum visual pass.

```powershell
python scripts/run_e2e.py --snapshot snapshots/e2e/v000006/snapshot.json --visual-passes 1
```

Preflight, live extraction, proposal and CAD completed. Before scene generation,
checkpoint replacement failed with Windows `PermissionError` / WinError 5 on
`snapshot.tmp` → `snapshot.json`. Scene remains marked running in the retained
failed manifest; scene execution, visual review and lab completion are not proven.
The original snapshot remains unchanged at `snapshots/e2e/v000007/`.

Portable verification also fails: error finalization indexed the pending
`snapshot.tmp`, then consumed it when replacing the manifest. Thus this historical
snapshot is **not a verified portable package**, even though stage artifacts remain.
Do not present it as full E2E success or silently repair its historical manifest.

The follow-up fix retries only atomic replacement for Windows errors 5/32/33,
bounded to six attempts (1.55 seconds total backoff). It does not repeat provider
calls. Permanent errors still raise and preserve pending evidence. Root checkpoint
temporary files are excluded from future artifact indexes. A transient lock is a
plausible explanation, not an identified locking process.

Offline regression suite after both fixes: **273 passed, 4 skipped, 12 subtests
passed**. Tests cover transient locks, bounded persistent failures, unrelated
permission failures and exclusion of pending checkpoints. No fresh live rerun was
performed after the fix. Next: authorize one new live run to verify the corrected
checkpoint path end to end. Quality acceptance and intervention savings remain
unverified.
