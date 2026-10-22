# Workbench snapshot — 2026-10-22

Frozen source and generated example at commit `a90ec05` from [PR #49](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/pull/49).

## Open the snapshot

Extract `snapshot.zip` into an empty directory. It contains:
- `source/`: the committed implementation, tests and documentation.
- `runs/workbench/2b36990135d7406c8db35e9504221fce/`: source video, frame evidence, extraction/design data, seven machine assets, previews, native scenes and lab plans.
- `evidence/`: six browser screenshots.
- `README.md`: detailed reopening instructions and runtime requirements.
- `manifest.json`: SHA-256 hashes for the 688 captured files.

The archive is packaged to keep the frozen source and generated files separate from the active source tree. `manifest.json` beside the archive describes paths **inside the extracted archive**. `snapshot.zip.sha256` verifies the archive itself.

## Known limitation

This captures semantic staging, **not an integrated functional workcell**. The vacuum tool is not attached to the robot wrist and the camera mount/target remains unresolved. See [issue #48](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/48) for shared assembly contracts and integrated-cell generation. Placement counts are not assembly validation.

Source verification at capture: **163 tests and 10 subtests passed**. The latest live GMI credential checks returned HTTP 401; model registration does not establish current access.

No environment files, configured credential values, logs or OpenCode session/response transcripts are included. External dependencies are not bundled. Historical provenance contains original local paths and process IDs.

Archive SHA-256: `8fa3f38be7de47d5160b82b426bca18c51d28390af00524497471ec117bdd889`
