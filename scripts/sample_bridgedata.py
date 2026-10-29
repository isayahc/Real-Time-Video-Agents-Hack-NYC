# SPDX-License-Identifier: MPL-2.0
"""Download only 10 or 20 BridgeData trajectories via individual JPEG URLs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import BinaryIO
from urllib.request import urlopen

SITE = 'https://rail-berkeley.github.io/bridgedata/'
DATA = 'https://rail.eecs.berkeley.edu/datasets/bridge_release/'
LICENSE = 'https://creativecommons.org/licenses/by/4.0/'
MAX_FRAME_BYTES = 3 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024


def select_trajectories(stream: BinaryIO, count: int) -> list[dict]:
    """Read only the requested index rows, refusing unbounded or malformed paths."""
    if count not in (10, 20):
        raise ValueError('Choose exactly 10 or 20 trajectories')
    selected = []
    for _ in range(count):
        line = stream.readline(16385)
        if not line or len(line) > 16384:
            raise ValueError('Missing or oversized trajectory index row')
        parts = line.decode('utf-8').strip().split(',')
        if len(parts) < 2:
            raise ValueError('Missing frame references')
        first, last = map(PurePosixPath, parts[:2])
        match = re.fullmatch(r'im_(\d+)\.jpg', last.name)
        if (not match or first.parent != last.parent or first.name != 'im_0.jpg'
                or first.is_absolute() or '..' in first.parts or first.parts[0] != 'raw'
                or '\\' in str(first) or ':' in str(first)):
            raise ValueError('Invalid source frame path')
        frames = int(match.group(1)) + 1
        if not 2 <= frames <= 300:
            raise ValueError('Trajectory frame count outside small-sample limit')
        selected.append({'source_id': str(first.parent.parent), 'frame_directory': str(first.parent),
                         'frame_count': frames, 'evaluation_only_annotations': parts[2:]})
    if len({row['source_id'] for row in selected}) != count:
        raise ValueError('Duplicate trajectory in selected index rows')
    return selected


def download_sample(output: Path, count: int = 10) -> dict:
    """Retain bounded source frames, checksums and derived 5-fps MP4s, never archives."""
    if count not in (10, 20):
        raise ValueError('Choose exactly 10 or 20 trajectories')
    output.mkdir(parents=True, exist_ok=False)
    with urlopen(SITE + 'traj_links.csv', timeout=30) as response:
        selected = select_trajectories(response, count)
    manifest = {'dataset': 'BridgeData V2', 'source': SITE, 'license': LICENSE,
                'attribution': 'BridgeData V2 — Homer Walke et al., CoRL 2023; BridgeData contributors.',
                'selection': f'First {count} trajectories in publisher website index; convenience sample, not held-out benchmark.',
                'timing': 'MP4 encoded at publisher-reported 5 Hz control frequency; per-frame capture timestamps unavailable. Not measured action durations.',
                'modifications': 'Original JPEG bytes retained; MP4s encoded from primary-camera JPEGs with H.264/yuv420p. No overlays or labels sent to inference.',
                'status': 'downloading', 'downloaded_frame_bytes': 0, 'trajectories': selected}

    def save() -> None:
        """Keep partial provenance if any bounded download or encoding fails."""
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    save()
    try:
        for number, row in enumerate(selected, 1):
            directory = output / f'episode-{number:02d}'
            frames = directory / 'frames'
            frames.mkdir(parents=True)
            row['frames'] = []
            for index in range(row['frame_count']):
                url = DATA + row['frame_directory'] + f'/im_{index}.jpg'
                remaining = MAX_TOTAL_BYTES - manifest['downloaded_frame_bytes']
                limit = min(MAX_FRAME_BYTES, remaining)
                if limit <= 0:
                    raise ValueError('Sample download exceeds 100 MiB budget')
                with urlopen(url, timeout=30) as response:
                    data = response.read(limit + 1)
                if len(data) > limit or not data.startswith(b'\xff\xd8'):
                    raise ValueError('Oversized or invalid JPEG response')
                target = frames / f'im_{index}.jpg'
                target.write_bytes(data)
                manifest['downloaded_frame_bytes'] += len(data)
                row['frames'].append({'url': url, 'path': target.relative_to(output).as_posix(),
                                      'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            video = directory / 'source.mp4'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n', '-framerate', '5',
                            '-i', str(frames / 'im_%d.jpg'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                            '-movflags', '+faststart', str(video)], check=True, timeout=120)
            row['video'] = {'path': video.relative_to(output).as_posix(),
                            'sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
                            'bytes': video.stat().st_size}
            save()
        manifest['status'] = 'completed'
    except Exception as error:
        manifest.update(status='failed', error=str(error))
        raise
    finally:
        save()
    return manifest


def main() -> None:
    """Fetch a capped sample without downloading a dataset archive or training shard."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, choices=(10, 20), default=10)
    args = parser.parse_args()
    result = download_sample(args.output, args.count)
    print(json.dumps({'status': result['status'], 'trajectories': len(result['trajectories']),
                      'downloaded_frame_bytes': result['downloaded_frame_bytes']}))


if __name__ == '__main__':
    main()
