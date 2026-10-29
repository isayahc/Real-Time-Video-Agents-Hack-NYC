# OpenCode startup compatibility — October 27, 2026

## Reproduction and fix

On `nebius-continuation`, installed OpenCode **2.1.4** started successfully, but
the CAD adapter still polled V1 `/global/health` without authentication. It timed
out after 20 seconds. The V1 `/provider`, session, prompt and message contracts
also differ from V2; changing the health URL alone would not fix the workflow.

The adapter now detects the installed API version. V2 uses authenticated
`/api/info`, project-scoped `/api/model`, native session creation, durable prompt
admission and paginated message timelines. Existing V1 behavior remains available
for V1 installations. Provider assignments, model IDs, user environment overrides,
CAD exports and snapshot contracts are preserved.

Managed V2 servers inherit the project's configured environment and absolute
configuration path, use an ephemeral loopback port and in-memory random password,
and stop their owned process tree at worker exit. This avoids modifying the shared
service. Passwords are redacted from the new startup log. Earlier legacy startup
logs may contain credentials and must not be published unreviewed.

Session recovery retains model/provider and input identity. The V2 adapter waits
for a terminal idle outcome after the matching user message, rejects truncated
output or a different model, and retains failure diagnostics. Transport tests
exercise the actual V2 payload/envelope shapes with synthetic provider output.

## Live checks without inference

`python scripts/run_e2e.py --check` now **passes**, including:

- Native dependencies and CAD runtime presence.
- Authenticated Nebius catalog: `nvidia/Nemotron-3.5-Super-VL`.
- Authenticated GMI catalog: `openai/gpt-6-astra`.
- OpenCode V2 startup and configured GMI/Astra model visibility.
- Native viewer build and Chromium WebGL2 startup.

The result explicitly retains `inference_compatibility_verified=false`.

A separate local API smoke check created and reopened a V2 CAD session after
private-server restart, checked the selected GMI/Astra model and deny-all tool
permissions, and confirmed an empty message timeline. No prompt was submitted.
The server adds `variant: default` to the requested model reference; the initial
smoke assertion was adjusted to check provider/model IDs without rejecting this
server-supplied field. Evidence is local at
`runs/opencode-v2-preflight-20261027-01/check.json`.

Final offline suite: **215 passed, 4 skipped, 12 subtests passed**. Coverage includes
authenticated transport, owned-server startup/cleanup, explicit-server failure,
exact model routing, saved-session drift, message pagination, input correlation,
terminal failures, truncated output and polling recovery without resubmission.
The final Windows cleanup check found **zero** remaining listeners from the owned
test servers. `git diff --check` passed.

## Remaining boundary

This resolves the startup/preflight blocker. Live V2 prompt execution and generated
CAD quality still need the separately authorized paid E2E run and a permitted
video. Native tests use deterministic provider fixtures; catalog/API smoke results
do not establish model response compatibility, physical execution or performance.

API contracts were checked against the running server's `/openapi.json` and the
[V2 API](https://opencode.ai/v2/docs/api),
[client guide](https://opencode.ai/v2/docs/build/client), and
[migration guide](https://opencode.ai/v2/docs/migrate-v1).
