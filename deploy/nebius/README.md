# SO-101 evaluation on Nebius Serverless Jobs

This container runs the existing full matched PyBullet comparison, records MP4s
and trajectories, converts both candidates to native Open-Industries replay,
verifies their evidence, and writes comparison accounting. It makes no inference
calls and controls no hardware. A completed Job can contain failed grasp trials;
process completion is not evidence of successful planting.

The simulator uses CPU physics and software rendering. Select a CPU platform and
preset available in your Nebius project; this workload does not require a GPU.
Start with 8 vCPUs and 32 GiB RAM if available, then measure actual requirements.

## 1. Build and test the image (WSL2 with Docker)

From the repository root on `nebius-continuation`, with a clean committed tree:

```bash
export SO101_REVISION="$(git rev-parse HEAD)"
export SO101_IMAGE="ghcr.io/isayahc/so101-evaluation:${SO101_REVISION}"
docker build --platform linux/amd64 \
  --build-arg SOURCE_REVISION="$SO101_REVISION" \
  -f deploy/nebius/Dockerfile -t "$SO101_IMAGE" .
mkdir -p runs/nebius-output
docker run --rm --platform linux/amd64 \
  --mount "type=bind,src=$PWD/runs/nebius-output,dst=/output" \
  "$SO101_IMAGE"
```

The image includes hash-verified robot inputs, the existing fixture archive,
Python 3.11, Node 22, and OI revision
`9b34ec217563e2a6788d5e60d9cc74c0bcd21330`. It downloads dependencies during build.
Base image tags and some transitive Python dependencies remain mutable; record
and use the resulting registry digest to reproduce a particular built image.
Only the allowlisted build files enter the Docker context; local `.env`, videos,
credentials, and run outputs are excluded.

Authenticate Docker to your registry, then push:

```bash
docker push "$SO101_IMAGE"
docker inspect --format '{{index .RepoDigests 0}}' "$SO101_IMAGE"
```

Use that `ghcr.io/...@sha256:...` reference for the cloud Job. A private image
requires registry authentication configured in Nebius; keep credentials in its
secret storage. Do not make the package public just to bypass authentication.

## 2. Configure the Nebius account

Use [Nebius AI Cloud](https://console.nebius.com), not the Token Factory console.
You need a project with editor access, available VM quota, a subnet, and a writable
Object Storage bucket or shared filesystem for results. A Token Factory API key
does not by itself configure AI Cloud CLI authentication.

Install and configure the [Nebius CLI](https://docs.nebius.com/cli/quickstart).
Inspect the available resources in the console before selecting IDs below.
Confirm the selected CPU preset's price and storage charges in your account.
No Job has been launched by adding these files.

Console configuration under **Serverless AI → Jobs → Create job**:

| Field | Value |
| --- | --- |
| Container image | The pushed image digest |
| Working directory | `/app` |
| Command | `python` |
| Arguments | `scripts/run_so101_job.py` |
| Compute | Available CPU platform/preset; initially 8 vCPU / 32 GiB if offered |
| Container disk | At least 20 GiB; increase if required by image size |
| Mounted volume | Your output bucket/filesystem, read-write at `/output` |
| Job timeout | 1 hour |
| Restart policy | Never |

The runner allows 45 minutes for evaluation, leaving time for artifact copying.
Nebius's documented minimum Job timeout is 1 hour. Runtime charges stop after
completion, but retained object storage has its own charges.

Equivalent CLI command, after setting the six account-specific variables:

```bash
: "${NEBIUS_PROJECT_ID:?Set project ID}"
: "${NEBIUS_SUBNET_ID:?Set subnet ID}"
: "${NEBIUS_CPU_PLATFORM:?Set available CPU platform}"
: "${NEBIUS_CPU_PRESET:?Set matching CPU preset}"
: "${NEBIUS_OUTPUT_VOLUME:?Set bucket or filesystem resource ID}"
: "${SO101_IMAGE_DIGEST:?Set pushed image@sha256 digest}"
export SO101_JOB_NAME="so101-evaluation-$(date -u +%Y%m%d-%H%M%S)"
nebius ai job create \
  --parent-id "$NEBIUS_PROJECT_ID" \
  --name "$SO101_JOB_NAME" \
  --image "$SO101_IMAGE_DIGEST" \
  --container-command python \
  --args scripts/run_so101_job.py \
  --working-dir /app \
  --platform "$NEBIUS_CPU_PLATFORM" \
  --preset "$NEBIUS_CPU_PRESET" \
  --disk-size 20Gi \
  --subnet-id "$NEBIUS_SUBNET_ID" \
  --volume "$NEBIUS_OUTPUT_VOLUME:/output:rw" \
  --timeout 1h \
  --restart-policy never
```

This creates billable compute. Inspect `nebius ai job create --help` for the
installed CLI; if it supports `--dry-run`, validate the same command with that
flag before creation. Do not submit repeatedly while waiting for provisioning.

## 3. Inspect and retrieve results

Use the Job's console page for status and logs. The output volume contains a
unique UTC/UUID directory for each invocation:

- `job.json`: final execution receipt, source revision and completed step count.
- `job.log`: simulator, replay and verifier stdout/stderr.
- `comparison/comparison.json`: verified matched comparison.
- `comparison/{reference_pocket,cad_seat}/`: summaries, per-trial trajectories,
  videos, OI scenes and hashed evidence.

The runner copies diagnostics even if a subprocess fails, then exits nonzero.
It writes `job.json` last, after copying all artifacts. Missing receipt means
the copy did not finish. An external hard kill, volume failure or cloud timeout
can prevent final copying; retain Nebius console logs and treat that run as
incomplete. There is no automatic retry or resume.

Download the run from the bucket/filesystem and retain the cloud Job ID and image
digest alongside it. Before claiming live Nebius execution, verify the Job reached
`COMPLETED`, its receipt says `verified_simulation`, and the downloaded bundles
pass the repository's verifier. Local execution alone is not cloud evidence.

## References

- [Managing Jobs, volumes, commands and timeout limits](https://docs.nebius.com/serverless/jobs/manage)
- [First Job and resource lifecycle](https://docs.nebius.com/serverless/quickstart/jobs)
- [Existing benchmark semantics](../../examples/so101-comparison/README.md)
