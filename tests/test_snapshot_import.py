# SPDX-License-Identifier: MPL-2.0
import json
import zipfile
from pathlib import Path

import pytest

from protocol_pipeline.snapshot_import import restore_snapshot
from protocol_pipeline.snapshots import E2EConfig, file_index
from protocol_pipeline.pipeline import sha256


def snapshot(tmp_path):
    root=tmp_path/'snapshot';run=root/'workbench'/('a'*32);run.mkdir(parents=True)
    (run/'source.mp4').write_bytes(b'synthetic test media')
    (run/'job.json').write_text(json.dumps({'id':'a'*32,'stage':'completed','created_at':0,'video_file':'source.mp4'}))
    machine=run/'machines'/'fixture';machine.mkdir(parents=True)
    (machine/'job.json').write_text(json.dumps({'stage':'generating','created_at':0,'attempt_id':'b'*32}))
    document={'kind':'workbench-e2e','schema_version':1,'status':'failed','version':1,'config':E2EConfig().model_dump(),
              'run_path':'workbench/'+('a'*32),'source':{'path':'workbench/'+('a'*32)+'/source.mp4','sha256':sha256(run/'source.mp4')},'files':file_index(root)}
    (root/'snapshot.json').write_text(json.dumps(document))
    return root,run


def test_restore_preserves_source_and_never_resumes_jobs(tmp_path):
    root,run=snapshot(tmp_path)
    original=(run/'job.json').read_bytes()
    result=restore_snapshot(root,tmp_path/'runs')
    imported=tmp_path/'runs'/result['id']
    assert result['id']!='a'*32
    assert (imported/'source.mp4').read_bytes()==b'synthetic test media'
    assert json.loads((imported/'job.json').read_text())['stage']=='completed'
    assert json.loads((imported/'machines/fixture/job.json').read_text())['stage']=='failed'
    assert (run/'job.json').read_bytes()==original


def test_zip_import_and_checksum_rejection(tmp_path):
    root,run=snapshot(tmp_path);archive=tmp_path/'snapshot.zip'
    with zipfile.ZipFile(archive,'w') as output:
        for path in root.rglob('*'):
            if path.is_file():output.write(path,path.relative_to(root).as_posix())
    assert restore_snapshot(archive,tmp_path/'runs')['imported_files']==3
    (run/'source.mp4').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='checksum'):
        restore_snapshot(root,tmp_path/'runs')


def test_archive_traversal_rejected(tmp_path):
    archive=tmp_path/'snapshot.zip'
    with zipfile.ZipFile(archive,'w') as output:output.writestr('../escape.txt','bad')
    with pytest.raises(ValueError,match='traverse'):
        restore_snapshot(archive,tmp_path/'runs')
    assert not (tmp_path/'escape.txt').exists()
