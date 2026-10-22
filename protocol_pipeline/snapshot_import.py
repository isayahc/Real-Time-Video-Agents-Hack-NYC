# SPDX-License-Identifier: MPL-2.0
"""Restore saved workbench data without running archived code or model requests."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import time
import uuid
from zipfile import ZipFile

from .pipeline import sha256, save_json
from .snapshots import contained_file, read_json, verify_snapshot

MAX_SNAPSHOT_BYTES = 1024 * 1024 * 1024


def safe_relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Snapshot paths must be relative and cannot traverse directories')
    return path


def restore_snapshot(source: Path, destination: Path) -> dict:
    """Import either an E2E snapshot or the legacy full-run snapshot directory/ZIP."""
    source = source.expanduser().resolve(strict=True)
    if source.is_dir():
        source = next((source/name for name in ('snapshot.json','snapshot.zip','manifest.json') if (source/name).is_file()), source)
    if source.suffix.lower() == '.zip':
        checksum = source.with_suffix('.zip.sha256')
        if checksum.is_file() and sha256(source) != checksum.read_text().split()[0]:
            raise ValueError('Snapshot archive checksum mismatch')
        with tempfile.TemporaryDirectory(prefix='workbench-import-') as temporary:
            root = Path(temporary)
            with ZipFile(source) as archive:
                entries = archive.infolist()
                if len(entries)>20000 or sum(row.file_size for row in entries)>MAX_SNAPSHOT_BYTES:
                    raise ValueError('Snapshot expands beyond the supported import limit')
                seen = set()
                for row in entries:
                    relative = safe_relative(row.filename)
                    key = relative.as_posix().casefold()
                    if key in seen or stat.S_ISLNK(row.external_attr >> 16):
                        raise ValueError('Snapshot contains duplicate paths or symlinks')
                    seen.add(key)
                    if row.is_dir():
                        continue
                    target = root.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(row) as stream, target.open('xb') as output:
                        shutil.copyfileobj(stream, output)
            manifest = root / ('snapshot.json' if (root/'snapshot.json').is_file() else 'manifest.json')
            return restore_directory(manifest, destination, source.name)
    if source.name not in ('snapshot.json','manifest.json'):
        raise ValueError('Choose a snapshot directory, snapshot.json, manifest.json, or snapshot.zip')
    return restore_directory(source, destination, str(source))


def restore_directory(manifest: Path, destination: Path, label: str) -> dict:
    document = read_json(manifest)
    if document.get('kind') == 'workbench-e2e':
        document = verify_snapshot(manifest)
        run_path = document.get('run_path','')
        if not re.fullmatch(r'workbench/[a-f0-9]{32}', run_path):
            raise ValueError('Snapshot has no saved workbench run to restore')
    else:
        files = document.get('files',[])
        if not files or len({row['path'] for row in files}) != len(files):
            raise ValueError('Snapshot requires a unique checksummed file index')
        for row in files:
            path = contained_file(manifest.parent,row['path'])
            if path.stat().st_size != row['bytes'] or sha256(path) != row['sha256']:
                raise ValueError('Snapshot checksum mismatch: '+row['path'])
        runs = {row['path'].rsplit('/',1)[0] for row in files
                if re.fullmatch(r'runs/workbench/[a-f0-9]{32}/job.json', row['path'])}
        if len(runs) != 1:
            raise ValueError('Snapshot must contain exactly one saved workbench run')
        run_path = runs.pop()
    files = document['files']
    prefix = run_path+'/'
    selected = [row for row in files if row['path'].startswith(prefix)]
    if not any(row['path'] == prefix+'job.json' for row in selected):
        raise ValueError('Snapshot run metadata is not indexed')
    run_id = uuid.uuid4().hex
    destination.mkdir(parents=True,exist_ok=True)
    staging = destination / ('.import-'+run_id)
    staging.mkdir()
    try:
        for row in selected:
            original = contained_file(manifest.parent,row['path'])
            target = staging.joinpath(*safe_relative(row['path'][len(prefix):]).parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(original,target)
        # Imported processes/sessions are historical, never active workers here.
        for pointer in staging.rglob('current.json'):
            value = read_json(pointer).get('attempt_id')
            if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{32}',value):
                raise ValueError('Invalid snapshot attempt pointer')
        for path in staging.rglob('job.json'):
            job = read_json(path)
            for name in ('attempt_id','resume_attempt_id','batch_id','video_file'):
                value = job.get(name)
                if value is not None and (not isinstance(value,str) or not value or value in ('.','..') or any(c in value for c in '/\\:')):
                    raise ValueError('Unsafe saved job file reference: '+name)
            if job.get('stage') not in ('completed','failed'):
                job.update(stage='failed',finished_at=time.time(),error='Imported unfinished stage; no computation was resumed.')
            if path == staging/'job.json':
                job.update(id=run_id, imported_snapshot={'source':label,'original_run_id':run_path.split('/')[-1],
                           'imported_at':time.time(),'snapshot_sha256':sha256(manifest)})
                if not isinstance(job.get('created_at'), (int,float)):
                    raise ValueError('Snapshot run has no creation timestamp')
                contained_file(staging,job['video_file'])
            save_json(path,job)
        for path in staging.glob('machines/batches/*/worker.json'):
            worker=read_json(path);worker.update(pid=0,stage='finished');save_json(path,worker)
        # Do not reactivate a historical visual-review subprocess.
        for path in staging.glob('visual-reviews/*/worker.json'):
            worker=read_json(path);worker.update(pid=0,stage='finished');save_json(path,worker)
        staging.rename(destination/run_id)
    except BaseException:
        shutil.rmtree(staging,ignore_errors=True)
        raise
    return {'id':run_id,'imported_files':len(selected),'source':label}
