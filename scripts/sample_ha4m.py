# SPDX-License-Identifier: MPL-2.0
"""Fetch ten HA4M label timelines and sparse RGB previews from the official host."""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_pipeline.assembly_baseline import summarize_recording, summarize_sample

ROOT = 'https://cloud.cnr.it'
DAV = '/owncloud/public.php/webdav/'
# Public share identifier linked by the authors; not a private account credential.
SHARE = 'j5BZvG1sXPzh6x1'
RECORDINGS = tuple(f'IDU{i:03d}V001' for i in range(1, 11))
PREVIEW_COUNT = 12
FRAME_PATTERN = re.compile(r'FrameID(\d+)_DeviceTimeStamp(\d+)us\.png')


def fetch(path: str, limit: int, listing: bool = False) -> bytes:
    """Bound each official public-share response and never request an archive."""
    if not path.startswith(DAV) or '..' in unquote(path).split('/') or urlparse(path).netloc:
        raise ValueError('Unexpected source path')
    headers = {'Authorization': 'Basic ' + base64.b64encode((SHARE + ':').encode()).decode()}
    if listing:
        headers['Depth'] = '1'
    with urlopen(Request(ROOT + path, method='PROPFIND' if listing else 'GET', headers=headers), timeout=90) as response:
        if response.status != (207 if listing else 200):
            raise ValueError('Unexpected HTTP status')
        if int(response.headers.get('Content-Length', '0')) > limit:
            raise ValueError('Source exceeds download limit')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Source exceeds download limit')
    return data


def entries(data: bytes) -> list[dict]:
    """Parse public WebDAV metadata without fetching contained recordings."""
    return [{'href': row.findtext('{DAV:}href'),
             'size': int(row.findtext('.//{DAV:}getcontentlength') or 0),
             'etag': row.findtext('.//{DAV:}getetag')}
            for row in ET.fromstring(data).findall('{DAV:}response')]


def digest(data: bytes) -> str:
    """Hash exact publisher bytes."""
    return hashlib.sha256(data).hexdigest()


def download(output: Path, resume: bool = False) -> dict:
    """Retain source bytes, timestamps, derived summaries and twelve previews per trial."""
    output.mkdir(parents=True, exist_ok=resume)
    manifest = {'dataset': 'HA4M', 'doi': '10.57760/sciencedb.01872',
                'source': f'{ROOT}/owncloud/index.php/s/{SHARE}',
                'license': 'https://creativecommons.org/licenses/by/4.0/',
                'attribution': "Cicirelli, Marani, Romeo, Garcia Dominguez, Heras, Perri and D'Orazio, Scientific Data 9, 745 (2022)",
                'selection': 'First trial of participants 001 through 010; convenience sample, not held-out.',
                'modifications': 'Original labels and sampled PNG bytes retained; 12-frame uniformly spaced preview MP4 per recording.',
                'full_rgb_recordings_downloaded': False, 'official_split': None,
                'new_inference_calls': 0, 'status': 'downloading', 'recordings': []}
    if resume:
        manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
        if [row['recording_id'] for row in manifest['recordings']] != list(RECORDINGS):
            raise ValueError('Resume requires all ten indexed label timelines')
        for row in manifest['recordings']:
            folder = output / row['recording_id']
            for name, key in [('Labels.txt', 'labels_sha256'), ('rgb-listing.xml', 'rgb_listing_sha256'),
                              ('camera-listing.xml', 'camera_listing_sha256')]:
                if digest((folder / name).read_bytes()) != row[key]:
                    raise ValueError('Source metadata changed; refusing resume')
        manifest.pop('error', None)
        manifest['status'] = 'resuming_previews'

    def save() -> None:
        """Preserve partial progress on all failures."""
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    save()
    try:
        planned_bytes = 0
        for recording in (() if resume else RECORDINGS):
            folder = output / recording
            folder.mkdir()
            label_path = DAV + recording + '/Labels.txt'
            labels = fetch(label_path, 1024 * 1024)
            (folder / 'Labels.txt').write_bytes(labels)
            color = DAV + recording + '/Color/'
            camera_listing = fetch(color, 1024 * 1024, True)
            (folder / 'camera-listing.xml').write_bytes(camera_listing)
            cameras = [row['href'] for row in entries(camera_listing) if row['href'] != color and row['href'].endswith('/')]
            if len(cameras) != 1:
                raise ValueError('Expected one RGB camera')
            listing = fetch(cameras[0], 8 * 1024 * 1024, True)
            (folder / 'rgb-listing.xml').write_bytes(listing)
            frames = []
            for row in entries(listing):
                match = FRAME_PATTERN.fullmatch(row['href'].rsplit('/', 1)[-1])
                if match:
                    frames.append({**row, 'frame_id': int(match[1]), 'timestamp_us': int(match[2])})
            frames.sort(key=lambda row: row['frame_id'])
            summary = summarize_recording(labels.decode('utf-8-sig'), frames)
            summary['recording_id'] = recording
            (folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
            selected = [frames[round(i * (len(frames) - 1) / (PREVIEW_COUNT - 1))] for i in range(PREVIEW_COUNT)]
            if any(not 0 < frame['size'] <= 10 * 1024 * 1024 for frame in selected):
                raise ValueError('Frame outside size bound')
            planned_bytes += sum(frame['size'] for frame in selected)
            if planned_bytes > 800 * 1024 * 1024:
                raise ValueError('Preview sample exceeds 800 MiB')
            manifest['recordings'].append({'recording_id': recording, 'label_url': ROOT + label_path,
                'labels_sha256': digest(labels), 'camera_listing_sha256': digest(camera_listing),
                'rgb_listing_sha256': digest(listing), 'selected_frames': selected,
                'summary': summary, 'preview_status': 'pending'})
            save()
            print(f'Validated labels/index: {recording} ({len(frames)} frames)', flush=True)
        baseline = summarize_sample([row['summary'] for row in manifest['recordings']])
        (output / 'baseline.json').write_text(json.dumps(baseline, indent=2) + '\n', encoding='utf-8')
        for row in manifest['recordings']:
            folder = output / row['recording_id']
            previews = folder / 'preview-frames'
            previews.mkdir(exist_ok=resume)

            def get_frame(pair: tuple[int, dict]) -> dict:
                """Download and header-check a PNG; FFmpeg later decodes the sequence."""
                index, frame = pair
                target = previews / f'{index:03d}.png'
                if target.exists():
                    known = next((item for item in row.get('frames', []) if item['path'] == target.relative_to(output).as_posix()), None)
                    if known is None or digest(target.read_bytes()) != known['sha256']:
                        raise ValueError('Existing preview has no matching recorded hash')
                    return known
                data = fetch(frame['href'], frame['size'])
                if len(data) != frame['size'] or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
                    raise ValueError('Frame length or PNG header mismatch')
                width, height = struct.unpack('>II', data[16:24])
                with target.open('xb') as stream:
                    stream.write(data)
                return {**frame, 'path': target.relative_to(output).as_posix(),
                        'sha256': digest(data), 'png_dimensions': [width, height]}

            with ThreadPoolExecutor(max_workers=4) as pool:
                row['frames'] = list(pool.map(get_frame, enumerate(row['selected_frames'])))
            save()
            video = folder / 'sparse-preview.mp4'
            # Explicit slideshow timebase; original timestamps are in the manifest.
            if not video.exists():
                subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-n', '-framerate', '1', '-i', str(previews / '%03d.png'),
                    '-vf', 'scale=1024:-2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
            elif row.get('preview_sha256') != digest(video.read_bytes()):
                raise ValueError('Existing video has no matching recorded hash')
            row.update(preview_status='complete', preview_sha256=digest(video.read_bytes()),
                       preview_timebase='1 sampled image/second slideshow; NOT original action timing')
            save()
            print(f'Preview complete: {row["recording_id"]}', flush=True)
        manifest['status'] = 'complete_labels_and_sparse_previews'
        save()
        return manifest
    except Exception as error:
        manifest.update(status='failed', error=f'{type(error).__name__}: {error}')
        save()
        raise


def main() -> None:
    """Run bounded public retrieval into a new directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='Verify retained source hashes and complete previews')
    args = parser.parse_args()
    download(args.output, args.resume)


if __name__ == '__main__':
    main()
