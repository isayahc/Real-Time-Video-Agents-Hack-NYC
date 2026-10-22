# SPDX-License-Identifier: MPL-2.0
"""Bundle the unmodified native OpenIndustries viewer from the configured checkout."""
import hashlib
from pathlib import Path
import shutil
import subprocess
from .scenes import openindustries_runtime


def native_viewer_bundle(cache: Path) -> Path:
    runtime = openindustries_runtime()
    if not runtime['available']:
        raise ValueError(runtime['message'])
    root = Path(runtime['root'])
    local = Path(__file__).parent
    inputs = [local / 'native_viewer.tsx', local / 'viewer_bundle.mts',
              root / 'src/components/workspace-viewer.tsx', root / 'src/lib/workspace.ts', root / 'src/lib/world.ts']
    digest = hashlib.sha256(b''.join(path.read_bytes() for path in inputs)).hexdigest()[:24]
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f'openindustries-{digest}.js'
    if not target.is_file():
        temporary = cache / f'openindustries-{digest}.tmp.js'
        result = subprocess.run([shutil.which('node'), '--import', (root / 'node_modules/tsx/dist/loader.mjs').as_uri(),
                                 str(local / 'viewer_bundle.mts'), str(root), str(temporary.resolve())],
                                cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=60, check=False)
        if result.returncode:
            raise RuntimeError('Native OpenIndustries viewer build failed: ' + result.stderr.strip())
        temporary.replace(target)
    return target
