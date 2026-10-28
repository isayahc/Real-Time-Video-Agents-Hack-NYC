# SPDX-License-Identifier: MPL-2.0
"""Retrieve exactly ten mirror videos using bounded ZIP byte ranges, without inference."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen
import zipfile

REVISION = 'c408f6effaa96512bd4eb5036c871bb7601ddc3e'
URL = f'https://huggingface.co/datasets/Zzitang/IndustReal/resolve/{REVISION}/IndustReal_videos.zip?download=true'
SIZE = 2505914072
BUDGET = 1024 * 1024 * 1024
CHUNK = 8 * 1024 * 1024


class RangeReader(io.RawIOBase):
    """Seekable pinned archive access that refuses full responses and oversize reads."""

    def __init__(self) -> None:
        """Track position and an aggregate one-GiB network budget."""
        super().__init__()
        self.position = 0
        self.downloaded = 0

    def seekable(self) -> bool:
        """Allow ZIP central-directory seeking."""
        return True

    def tell(self) -> int:
        """Return the virtual archive offset."""
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        """Resolve seeks within the known pinned archive length."""
        if whence not in (0, 1, 2):
            raise ValueError('Invalid seek origin')
        position = offset + (0 if whence == 0 else self.position if whence == 1 else SIZE)
        if not 0 <= position <= SIZE:
            raise ValueError('Seek outside archive')
        self.position = position
        return position

    def read(self, size: int = -1) -> bytes:
        """Require exact Content-Range before reading any body bytes."""
        size = SIZE - self.position if size < 0 else min(size, SIZE - self.position)
        if size == 0:
            return b''
        if size > CHUNK or self.downloaded + size > BUDGET:
            raise ValueError('Range exceeds small-sample budget')
        end = self.position + size - 1
        byte_range = f'{self.position}-{end}'
        request = Request(URL + '&range=' + byte_range, headers={'Range': 'bytes=' + byte_range})
        with urlopen(request, timeout=90) as response:
            if response.status != 206 or response.headers.get('Content-Range') != f'bytes {byte_range}/{SIZE}':
                raise ValueError('Refusing full archive or mismatched byte range')
            data = response.read(size + 1)
        if len(data) != size:
            raise ValueError('Range length mismatch')
        self.position += size
        self.downloaded += size
        return data


def download_sample(output: Path) -> dict:
    """Keep ten videos, CRC/SHA checks and decoding evidence; labels remain unresolved."""
    output.mkdir(parents=True, exist_ok=False)
    source = RangeReader()
    manifest = {
        'dataset': 'IndustReal', 'mirror_url': URL, 'mirror_revision': REVISION,
        'publisher_doi': '10.4121/b008dd74-020d-4ea4-a8ba-7bb60769d224.v1',
        'newer_publisher_version': '10.4121/b008dd74-020d-4ea4-a8ba-7bb60769d224.v2',
        'license': 'Apache-2.0 (publisher metadata; mirror has no license card)',
        'attribution': 'Tim J. Schoonbeek, Tim Houben, Hans Onvlee, Peter H.N. de With, Fons van der Sommen',
        'archive_published_sha256': '5f355ff8110f0e8a777c60f8ff23f5101500e5396555f47e7a1e78ea582ff2b4',
        'archive_sha256_verified': False, 'publisher_byte_identity_verified': False,
        'selection': 'Ten smallest compressed MP4 members, then filename; size-biased convenience sample, not representative or held-out.',
        'official_split': None, 'annotations_available': False,
        'annotation_alignment_verified': False, 'baseline_status': 'blocked_missing_authoritative_labels',
        'new_inference_calls': 0, 'status': 'downloading', 'recordings': [],
    }

    def save() -> None:
        """Persist progress and failures without removing partial evidence."""
        manifest['downloaded_archive_bytes'] = source.downloaded
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    save()
    try:
        with zipfile.ZipFile(source) as archive:
            videos = [entry for entry in archive.infolist()
                      if re.fullmatch(r'\d{2}_(assy|main)_\d+_\d+\.mp4', entry.filename)]
            selected = sorted(videos, key=lambda item: (item.compress_size, item.filename))[:10]
            if len(selected) != 10 or len({item.filename for item in selected}) != 10:
                raise ValueError('Expected ten distinct recordings')
            if sum(item.compress_size for item in selected) > BUDGET - CHUNK:
                raise ValueError('Selected sample exceeds budget')
            manifest['selected_recordings'] = [item.filename for item in selected]
            save()
            for item in selected:
                if item.file_size > 200 * 1024 * 1024:
                    raise ValueError('Uncompressed member exceeds budget')
                target = output / item.filename
                digest = hashlib.sha256()
                with archive.open(item) as member, target.open('xb') as destination:
                    while data := member.read(CHUNK // 2):
                        digest.update(data)
                        destination.write(data)
                probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,duration',
                    '-of', 'json', str(target)], capture_output=True, text=True, check=True)
                subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(target),
                                '-map', '0:v:0', '-f', 'null', '-'], check=True, capture_output=True)
                manifest['recordings'].append({'path': item.filename, 'bytes': target.stat().st_size,
                    'sha256': digest.hexdigest(), 'zip_crc32': f'{item.CRC:08x}',
                    'zip_crc_verified': True, 'full_video_decode_passed': True,
                    'media': json.loads(probe.stdout), 'official_split': None})
                save()
                print(f'Downloaded and decoded {len(manifest["recordings"])}/10: {item.filename}', flush=True)
        manifest['status'] = 'videos_downloaded_labels_blocked'
        save()
        return manifest
    except Exception as error:
        manifest.update(status='failed', error=f'{type(error).__name__}: {error}')
        save()
        raise


def main() -> None:
    """Download a fixed ten-recording subset to a new local directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    download_sample(args.output)


if __name__ == '__main__':
    main()
