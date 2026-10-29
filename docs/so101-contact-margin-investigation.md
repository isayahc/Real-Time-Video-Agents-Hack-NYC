# SO-101 contact-margin correction — draft follow-up to #71

**Verified scope: an opt-in PyBullet runtime correction. Grasping remains failed;
#71 remains open pending physical evidence.** This patch does not change the
project's default dependency, robot geometry, production controller or CAD v1.

## Defect and correction

PyBullet 3.2.7's `b3ChangeDynamicsInfoSetCollisionMargin` sets `m_linkIndex = -1`.
Thus Python `changeDynamics(robot, jaw_index, collisionMargin=...)` targets the
base, even when other link-specific properties are passed in the same call.
Separately, the server's link branch changes only the outer collision shape;
URDF mesh hulls can be children of compound shapes.

[`pybullet-3.2.7-link-margin.patch`](../scripts/patches/pybullet-3.2.7-link-margin.patch):

- Adds a link-aware setter and uses it from Python; preserves the old C entry point.
- Propagates requested link margins through compound children and recalculates
  compound AABBs. Source vertices, joint limits and inertias stay unchanged.
- Labels the custom build `3.2.7+issue71margin1` and bounds compilation to four jobs.

This is a local diagnostic patch, not an upstream release. The base-body margin
implementation is not generalized by this patch. Numerical margin values remain
simulation assumptions, not hardware tolerances.

## Reproduce in an isolated Linux Python 3.11 environment

Requires a C++ compiler (`build-essential` on Ubuntu), Git and network access for
dependencies. Preserve the stock runtime. From the repository root:

```bash
REPO="$PWD"
python3.11 -m venv /path/to/new-margin-venv
source /path/to/new-margin-venv/bin/activate
python -m pip install setuptools wheel 'numpy==2.3.5' -e '.[test,robot,simulation]'
mkdir -p runs/margin-build
curl -fL https://files.pythonhosted.org/packages/de/95/b9a98cd4ed948d4f25a7d0b13cb0c1f87e58dc6d113be9e18940641eb25f/pybullet-3.2.7.tar.gz -o runs/margin-build/pybullet-3.2.7.tar.gz
echo '042879db8d101ac7590dee475fc6aded508b85fe1273fdbbfde1d88bd200e14f  runs/margin-build/pybullet-3.2.7.tar.gz' | sha256sum -c -
tar -xzf runs/margin-build/pybullet-3.2.7.tar.gz -C runs/margin-build
cd runs/margin-build/pybullet-3.2.7
git apply --check "$REPO/scripts/patches/pybullet-3.2.7-link-margin.patch"
git apply "$REPO/scripts/patches/pybullet-3.2.7-link-margin.patch"
python setup.py bdist_wheel
python -m pip install dist/pybullet-3.2.7+issue71margin1-*.whl
cd "$REPO"
SO101_MARGIN_RUNTIME_TESTS=1 python -m pytest -q tests/test_pybullet_link_margin.py
SO101_SOURCE_ROOT=runs/so101-source python -m pytest -q -rs tests/test_robot_contract.py tests/test_seed_simulation.py tests/test_seed_comparison.py
```

Fetch pinned robot sources using the existing robot-contract guide before the
second test command. The new margin tests use generated geometry and need no
robot download. They are opt-in because they intentionally fail on stock 3.2.7.
Default simulation execution does not request the corrected jaw margin; adopting
it in a production run requires explicit configuration and runtime provenance.

## Actual verification (2026-10-29)

- New regression tests on stock 3.2.7: **2 failed**, reproducing base mutation and
  unchanged child contact distance. Same tests on custom runtime: **2 passed**.
- Existing robot/simulation/comparison tests on custom runtime: **66 passed**,
  no skips (219.42 s); yourdfpy deprecation warnings remain.
- Eight frozen failed-pose contact queries changed by exactly **+0.99 mm** when
  the requested jaw margin decreased from 1 mm to 0.01 mm. Only the intended link
  changed. At one failed lift pose, source/FCL clearance was 0.829129 mm;
  stock Bullet reported -0.176321 mm, corrected Bullet +0.813679 mm.
- Not all Bullet distances equal source/FCL distances: one commanded-pose query
  remained 0.360981 mm versus 0.083006 mm. Convex approximation and numerical
  distance behavior are still distinct from source-surface and hardware evidence.

The original WSL offline suite had **419 passed, 17 skipped, 12 subtests passed**;
native fixture verification later had **39 passed, 2 skipped**. Those earlier
counts predate the two new opt-in tests. Unchanged baseline trajectories and
frames reproduced the original #66 artifact byte-for-byte for both tools.

## Motion results and explicit limitations

The completed stock-runtime +6 mm-offset comparison had **0 pickups / 9 and
0 accepted / 9 for both tools**; reference had 0 collision attempts, CAD had 9.
Both complete bundles passed the existing evidence verifier and native OI replay
checks; these are evidence-integrity checks, not task success.

With corrected margins, paired +6 mm smoke trials still failed pickup. Neither
nominal attempt contacted the seed during descent/closure; the moving jaw touched
it only briefly during lift. A separate 1.2 mm supporting-web mesh prototype also
failed pickup/collision in all six attempted cases, and the comparator rejected
its controlled inputs as mismatched. It is **not** a valid matched campaign,
fabrication-ready CAD revision, or adopted fix. Its failed results remain local.

No sustained bilateral pickup, successful transport, physical fabrication,
hardware calibration, authorized physical trial or live provider call is claimed.
The rigid-body evaluator has no seed-damage channel. The next motion step is to
diagnose the failed relief/controller path and its input mismatch before adopting
any revised geometry or launching another full comparison.

## Retained local evidence (not uploaded)

- `runs/issue71-baseline-20261029/verification-report.md`: prior commands/results.
- `runs/issue71-offset6-full-20261029/`: complete stock-runtime failed comparison,
  22 videos, trajectories, source hashes, OI replays and verifier manifests.
- `runs/issue71-contact-model/`: source archive, build logs, patch/wheel hashes,
  frozen-pose probes, tilted-pose failures and diagnostic wrapper source.
- `runs/issue71-margin10um-offset6-smoke/`: corrected-margin failed smoke.
- `runs/issue71-relief-prototype-smoke/`: failed, comparator-rejected prototype.

Local custom wheel SHA-256:
`7ff113a80d76755e2902017eace696c9be6b39aadec342fd25af6f0f055cbcc8`.
Build outputs may have different hashes; record each build's own identity.
Prior public textual findings: [#71 verification comment](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/71#issuecomment-6502575704).
Recordings, binary outputs and private runtime data are excluded from this change.
