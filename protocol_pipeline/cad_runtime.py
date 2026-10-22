# SPDX-License-Identifier: MPL-2.0
"""Resolve the same native Forma adapter for preflight, workers and direct builds."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ADAPTER_RELATIVE_PATH = Path('.agents/skills/forma-hardware/scripts/cad.py')


def forma_source() -> Path:
    """Resolve an explicitly configured Forma checkout or the conventional sibling."""
    return Path(os.getenv('FORMA_ROOT') or Path(__file__).resolve().parents[2] / 'forma-oss').expanduser().resolve()


def cad_adapter_path() -> Path:
    """Honor explicit configuration, then search checkout, installed package and cwd."""
    explicit = os.getenv('FORMA_CAD_ADAPTER_PATH')
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f'FORMA_CAD_ADAPTER_PATH does not name an existing cad.py: {path}')
        return path
    candidates = [forma_source() / ADAPTER_RELATIVE_PATH]
    spec = importlib.util.find_spec('forma_core')
    if spec and spec.origin:
        package = Path(spec.origin).resolve().parent
        candidates.extend([package / ADAPTER_RELATIVE_PATH, package.parent / ADAPTER_RELATIVE_PATH])
    candidates.append(Path.cwd() / ADAPTER_RELATIVE_PATH)
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise ValueError('The Forma OpenCAD adapter is unavailable. Set FORMA_ROOT to its checkout or '
                     'FORMA_CAD_ADAPTER_PATH to .agents/skills/forma-hardware/scripts/cad.py. '
                     'Installing caid-forma-core alone may not install the hardware skill.')
