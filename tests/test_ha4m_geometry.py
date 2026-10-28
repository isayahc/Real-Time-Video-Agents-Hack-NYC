# SPDX-License-Identifier: MPL-2.0
"""Reject changed source evidence before importing optional native CAD libraries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.audit_ha4m_geometry import verify_source


def test_source_hashes_handle_manifest_windows_paths(tmp_path: Path) -> None:
    """Keep downloaded manifest paths portable and reject altered STEP bytes."""
    folder = tmp_path / 'source-step'
    folder.mkdir()
    step = folder / 'part.STEP'
    step.write_bytes(b'original publisher bytes')
    manifest = {'files': {'source-step\\part.STEP': hashlib.sha256(step.read_bytes()).hexdigest()}}
    (tmp_path / 'source-manifest.json').write_text(json.dumps(manifest))
    assert verify_source(tmp_path) == manifest
    step.write_bytes(b'changed bytes')
    with pytest.raises(ValueError, match='Source checksum mismatch'):
        verify_source(tmp_path)
