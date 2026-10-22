# SPDX-License-Identifier: MPL-2.0
"""Content-addressed, lightweight card previews for immutable CAD revisions."""
from __future__ import annotations
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import shutil
import struct
import subprocess
import threading
import time
import uuid

from .pipeline import save_json,sha256

PREVIEW_VERSION='openindustries-asset-turntable-320-2s-10fps-v1'
MAX_GIF_BYTES=4*1024*1024
_write_lock=threading.Lock()


@lru_cache(maxsize=256)
def _cad_digest(path: str,mtime_ns: int,size: int) -> str:
    return sha256(Path(path))


def preview_info(asset: Path,machine_directory: Path,url_prefix: str) -> dict:
    stat=asset.stat();cad_sha=_cad_digest(str(asset.resolve()),stat.st_mtime_ns,stat.st_size)
    key=hashlib.sha256((cad_sha+PREVIEW_VERSION).encode()).hexdigest()
    root=machine_directory/'previews'
    ready=(root/f'{key}.gif').is_file() and (root/f'{key}.png').is_file()
    return {'cache_key':key,'cad_sha256':cad_sha,'ready':ready,'size':320,'frames':20,
            'duration_s':2,'fps':10,'gif_url':f'{url_prefix}/{key}.gif',
            'poster_url':f'{url_prefix}/{key}.png','version':PREVIEW_VERSION}


def validate_gif(data: bytes) -> None:
    if len(data)<32 or len(data)>MAX_GIF_BYTES or data[:6] not in (b'GIF87a',b'GIF89a'):
        raise ValueError('Preview must be a GIF under 4 MiB')
    if struct.unpack('<HH',data[6:10])!=(320,320):
        raise ValueError('Card previews must be the canonical 320 × 320 native GIF')


def save_preview(asset: Path,machine_directory: Path,url_prefix: str,key: str,data: bytes) -> dict:
    validate_gif(data)
    with _write_lock:
        info=preview_info(asset,machine_directory,url_prefix)
        if info['cache_key']!=key:
            raise ValueError('The CAD revision changed while the preview rendered; reload its card')
        if info['ready']:return info
        executable=shutil.which('ffmpeg');probe=shutil.which('ffprobe')
        if not executable or not probe:raise ValueError('ffmpeg and ffprobe are required to validate the GIF and extract its still poster')
        root=machine_directory/'previews';root.mkdir(exist_ok=True)
        token=uuid.uuid4().hex;temporary_gif=root/f'.{token}.gif';temporary_png=root/f'.{token}.png'
        try:
            temporary_gif.write_bytes(data)
            checked=subprocess.run([probe,'-v','error','-select_streams','v:0','-count_frames',
                '-show_entries','stream=nb_read_frames','-of','json',str(temporary_gif)],capture_output=True,
                text=True,encoding='utf-8',check=False,timeout=10)
            streams=json.loads(checked.stdout).get('streams',[]) if checked.returncode==0 else []
            if not streams or int(streams[0].get('nb_read_frames',0))!=20:
                raise ValueError('Native turntable preview must contain exactly 20 frames')
            result=subprocess.run([executable,'-v','error','-i',str(temporary_gif),'-frames:v','1',str(temporary_png)],
                                  capture_output=True,text=True,encoding='utf-8',check=False,timeout=10)
            if result.returncode or not temporary_png.is_file():
                raise ValueError('Native GIF could not be decoded: '+result.stderr.strip())
            temporary_gif.replace(root/f'{key}.gif');temporary_png.replace(root/f'{key}.png')
            save_json(root/f'{key}.json',{'cad_sha256':info['cad_sha256'],'preview_version':PREVIEW_VERSION,
                'width':320,'height':320,'frames':20,'duration_s':2,'motion':'camera_turntable_not_machine_operation',
                'renderer':'client OpenIndustries native renderGif','created_at':time.time(),
                'gif_sha256':sha256(root/f'{key}.gif')})
        finally:
            temporary_gif.unlink(missing_ok=True);temporary_png.unlink(missing_ok=True)
        return preview_info(asset,machine_directory,url_prefix)


def preview_file(machine_directory: Path,filename: str) -> Path:
    key,dot,extension=filename.partition('.')
    if len(key)!=64 or any(character not in '0123456789abcdef' for character in key) or not dot or extension not in ('gif','png'):
        raise ValueError('Unknown machine preview')
    path=machine_directory/'previews'/filename
    if not path.is_file():raise FileNotFoundError('Machine preview has not been cached yet')
    return path
