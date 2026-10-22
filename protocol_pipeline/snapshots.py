# SPDX-License-Identifier: MPL-2.0
"""Append-only, checksummed E2E snapshots and portable source input loading."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any, Literal
from zipfile import ZipFile

from pydantic import Field

from .models import StrictModel
from .pipeline import sha256
from .scenes import SceneOptions

MAX_VIDEO_BYTES = 100 * 1024 * 1024
VIDEO_SUFFIXES = {'.mp4', '.mov', '.webm'}


class E2EConfig(StrictModel):
    """Serializable settings; credentials and runtime installation paths stay in env."""

    vision_provider: Literal['nebius'] = 'nebius'
    vision_model: str = Field(default='nvidia/Nemotron-3.5-Super-VL', min_length=1)
    text_provider: Literal['gmi'] = 'gmi'
    text_model: str = Field(default='openai/gpt-6-astra', min_length=1)
    cad_authoring: Literal['opencode'] = 'opencode'
    frame_count: int = Field(default=8, ge=2, le=24)
    scene: SceneOptions = Field(default_factory=SceneOptions)
    visual_passes: int = Field(default=1, ge=1, le=10)


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object rather than executing snapshot contents."""
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected JSON object: {path.name}')
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    """Replace one checkpoint atomically, keeping valid JSON after interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def contained_file(root: Path, relative: str) -> Path:
    """Reject absolute paths, traversal and symlinks in portable file references."""
    parts = PurePosixPath(relative)
    if not relative or parts.is_absolute() or '..' in parts.parts or '\\' in relative or ':' in relative:
        raise ValueError('Snapshot paths must be relative POSIX paths')
    path = root.joinpath(*parts.parts)
    if any(root.joinpath(*parts.parts[:i]).is_symlink() for i in range(1, len(parts.parts) + 1)):
        raise ValueError('Snapshot references cannot contain symlinks')
    if not path.is_file():
        raise ValueError(f'Missing snapshot file: {relative}')
    return path


def numbered_snapshots(root: Path) -> list[Path]:
    """Sort by integer version, including allocated but interrupted versions."""
    return sorted((p for p in root.glob('v*') if p.is_dir() and re.fullmatch(r'v\d{6,}', p.name)),
                  key=lambda p: int(p.name[1:]))


def latest_snapshot(root: Path) -> Path:
    """Use the latest finalized snapshot, including a failed run's retained source."""
    for path in reversed(numbered_snapshots(root)):
        manifest = path / 'snapshot.json'
        if manifest.is_file():
            document = read_json(manifest)
            if document.get('source') and document.get('status') in {'completed', 'failed', 'interrupted'}:
                return manifest
    raise ValueError('No finalized E2E snapshot exists; supply --video or --snapshot first')


def allocate_snapshot(root: Path) -> Path:
    """Reserve a unique increasing version with atomic mkdir, never overwrite one."""
    root.mkdir(parents=True, exist_ok=True)
    versions = numbered_snapshots(root)
    version = int(versions[-1].name[1:]) + 1 if versions else 1
    while True:
        path = root / f'v{version:06d}'
        try:
            path.mkdir()
            return path
        except FileExistsError:
            version += 1


def file_index(root: Path) -> list[dict[str, Any]]:
    """Inventory relative artifact paths and hashes, excluding the manifest itself."""
    return [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256(p)}
            for p in sorted(root.rglob('*')) if p.is_file() and p != root / 'snapshot.json']


def verify_snapshot(manifest: Path) -> dict[str, Any]:
    """Validate the portable contract and every indexed artifact before reuse."""
    document = read_json(manifest)
    if document.get('schema_version') != 1 or document.get('kind') != 'workbench-e2e':
        raise ValueError('Unsupported E2E snapshot schema')
    if document.get('status') not in {'completed', 'failed', 'interrupted'} or not isinstance(document.get('version'), int):
        raise ValueError('Only finalized, numbered snapshots can be used as input')
    E2EConfig.model_validate(document['config'])
    files = document.get('files', [])
    if not files or len({item['path'] for item in files}) != len(files):
        raise ValueError('Snapshot requires a nonempty, unique artifact index')
    for item in files:
        path = contained_file(manifest.parent, item['path'])
        if path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
            raise ValueError(f'Snapshot checksum mismatch: {item["path"]}')
    source = document['source']
    if source['path'] not in {item['path'] for item in files}:
        raise ValueError('Snapshot source is absent from artifact index')
    if sha256(contained_file(manifest.parent, source['path'])) != source['sha256']:
        raise ValueError('Snapshot source checksum mismatch')
    return document


def resolve_input(video: Path | None, snapshot: Path | None, root: Path) -> tuple[Path, dict[str, Any] | None]:
    """Choose explicit video/snapshot, otherwise the newest finalized E2E version."""
    if video is not None:
        return video.resolve(strict=True), None
    path = snapshot.resolve(strict=True) if snapshot else latest_snapshot(root).resolve()
    if path.is_dir():
        path = path / ('snapshot.json' if (path / 'snapshot.json').is_file() else 'snapshot.zip')
    if path.suffix == '.zip':
        return path, None
    document = verify_snapshot(path)
    return contained_file(path.parent, document['source']['path']), document


def copy_source(source: Path, destination: Path) -> dict[str, Any]:
    """Copy source video, or import only a verified video from the PR #50 ZIP."""
    destination.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == '.zip':
        checksum = source.with_suffix(source.suffix + '.sha256')
        if checksum.is_file() and sha256(source) != checksum.read_text().split()[0]:
            raise ValueError('Legacy snapshot ZIP checksum mismatch')
        # Read a selected member; never extract archived paths or execute frozen code.
        with ZipFile(source) as archive:
            candidates = [n for n in archive.namelist() if re.fullmatch(
                r'runs/workbench/[a-f0-9]{32}/source\.(mp4|mov|webm)', n)]
            if len(candidates) != 1:
                raise ValueError('Legacy snapshot must contain exactly one workbench source video')
            name = candidates[0]
            info = archive.getinfo(name)
            if not 0 < info.file_size <= MAX_VIDEO_BYTES:
                raise ValueError('Source video must be between 1 byte and 100 MiB')
            output = destination / ('source' + Path(name).suffix)
            with archive.open(name) as stream, output.open('xb') as target:
                shutil.copyfileobj(stream, target)
        manifest = source.parent / 'manifest.json'
        if manifest.is_file():
            entries = [row for row in read_json(manifest).get('files', []) if row['path'] == name]
            if len(entries) != 1 or entries[0]['sha256'] != sha256(output):
                raise ValueError('Legacy snapshot video checksum mismatch')
    else:
        if source.suffix.lower() not in VIDEO_SUFFIXES or not 0 < source.stat().st_size <= MAX_VIDEO_BYTES:
            raise ValueError('Supply a nonempty MP4, MOV or WebM video, at most 100 MiB')
        output = destination / ('source' + source.suffix.lower())
        with source.open('rb') as stream, output.open('xb') as target:
            shutil.copyfileobj(stream, target)
    return {'path': output.relative_to(destination.parent).as_posix(), 'sha256': sha256(output)}
