# SPDX-License-Identifier: MPL-2.0
"""Preview identity, validation and immutable reuse without new renderer/model work."""
import json
import shutil
import struct
import subprocess
import pytest

from protocol_pipeline.machine_previews import preview_file,preview_info,save_preview,validate_gif


def test_preview_keys_follow_cad_bytes_and_reject_bad_gif_or_paths(tmp_path):
    asset=tmp_path/'machine.forma.json';asset.write_text('{"revision":1}')
    first=preview_info(asset,tmp_path,'/preview')
    assert not first['ready']
    assert len(first['cache_key'])==64
    asset.write_text('{"revision":2,"changed":true}')
    assert preview_info(asset,tmp_path,'/preview')['cache_key']!=first['cache_key']
    for data in (b'not a gif',b'GIF89a'+struct.pack('<HH',1,1)+b'0'*30):
        with pytest.raises(ValueError):validate_gif(data)
    with pytest.raises(ValueError):preview_file(tmp_path,'../../private.gif')


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='Real GIF decoding requires ffmpeg/ffprobe')
def test_cached_turntable_and_poster_are_reused_and_cad_changes_invalidate(tmp_path,monkeypatch):
    source=tmp_path/'fixture.gif'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=320x320:rate=10','-t','2',str(source)],
                   check=True,capture_output=True,timeout=15)
    asset=tmp_path/'machine.forma.json';asset.write_text('{"fixture":1}')
    info=preview_info(asset,tmp_path,'/preview')
    result=save_preview(asset,tmp_path,'/preview',info['cache_key'],source.read_bytes())
    assert result['ready']
    assert preview_file(tmp_path,info['cache_key']+'.png').read_bytes().startswith(b'\x89PNG')
    metadata=json.loads((tmp_path/'previews'/f"{info['cache_key']}.json").read_text())
    with monkeypatch.context() as scoped:
        scoped.setattr('protocol_pipeline.machine_previews.subprocess.run',lambda *args,**kwargs:pytest.fail('Cached preview unexpectedly re-rendered or re-decoded'))
        assert save_preview(asset,tmp_path,'/preview',info['cache_key'],source.read_bytes())['ready']
    assert json.loads((tmp_path/'previews'/f"{info['cache_key']}.json").read_text())['created_at']==metadata['created_at']
    asset.write_text('{"fixture":2,"changed":true}')
    changed=preview_info(asset,tmp_path,'/preview')
    assert changed['cache_key']!=info['cache_key'] and not changed['ready']
    with pytest.raises(ValueError,match='revision changed'):
        save_preview(asset,tmp_path,'/preview',info['cache_key'],source.read_bytes())
    assert preview_file(tmp_path,info['cache_key']+'.gif').exists()
