# SPDX-License-Identifier: MPL-2.0
"""Fetch every frame of one human joining interval from the existing HA4M sample."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sample_ha4m import FRAME_PATTERN, digest, entries, fetch


def prepare(source: Path, output: Path) -> None:
    """Retain contiguous original frames and encode a nominal-30-FPS human clip."""
    original = json.loads((source / 'manifest.json').read_text())
    row = next(r for r in original['recordings'] if r['recording_id'] == 'IDU001V001')
    folder = source / row['recording_id']
    labels = (folder / 'Labels.txt').read_bytes()
    listing = (folder / 'rgb-listing.xml').read_bytes()
    if digest(labels) != row['labels_sha256'] or digest(listing) != row['rgb_listing_sha256']:
        raise ValueError('Source annotations/index changed')
    segment = next(s for s in row['summary']['segments'] if s['action_id'] == 9)
    frames = []
    for entry in entries(listing):
        match = FRAME_PATTERN.fullmatch(entry['href'].rsplit('/', 1)[-1])
        if match and segment['start_frame'] <= int(match[1]) < segment['end_frame_exclusive']:
            frames.append({**entry, 'frame_id': int(match[1]), 'timestamp_us': int(match[2])})
    frames.sort(key=lambda f: f['frame_id'])
    if [f['frame_id'] for f in frames] != list(range(segment['start_frame'], segment['end_frame_exclusive'])):
        raise ValueError('Noncontiguous interval')
    if len(frames) > 300 or sum(f['size'] for f in frames) > 1024 ** 3:
        raise ValueError('Demo exceeds 300-frame / 1-GiB budget')
    if any(not 0 < f['size'] <= 10 * 1024 ** 2 for f in frames):
        raise ValueError('Frame size outside bound')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'frames').mkdir()
    manifest = {'dataset': 'HA4M', 'recording_id': row['recording_id'], 'segment': segment,
                'source_manifest_sha256': digest((source / 'manifest.json').read_bytes()),
                'license': original['license'], 'attribution': original['attribution'],
                'selection': 'First participant first trial, action 9 only; demo selection, not a performance target.',
                'modifications': 'All consecutive action-9 RGB frames; downscaled, encoded at nominal publisher 30 FPS; no interpolation.',
                'status': 'downloading', 'frames': [], 'new_inference_calls': 0}

    def save() -> None:
        """Retain completed frame evidence on interruption."""
        (output / 'source-provenance.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    def download(pair: tuple[int, dict]) -> dict:
        """Fetch one original PNG with explicit byte bounds."""
        index, frame = pair
        data = fetch(frame['href'], frame['size'])
        if len(data) != frame['size'] or not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid source PNG')
        path = output / 'frames' / f'{index:04d}.png'
        path.write_bytes(data)
        return {**frame, 'path': path.relative_to(output).as_posix(), 'sha256': digest(data)}

    save()
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for frame in pool.map(download, enumerate(frames)):
                manifest['frames'].append(frame)
                save()
        video = output / 'human-block-joining.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-n', '-framerate', '30', '-i',
                        str(output / 'frames/%04d.png'), '-vf', 'scale=1280:-2', '-c:v', 'libx264',
                        '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(video), '-f', 'null', '-'], check=True)
        manifest.update(status='complete', video_sha256=digest(video.read_bytes()),
                        video_bytes=video.stat().st_size, nominal_duration_s=len(frames) / 30)
        shutil.copy2(folder / 'Labels.txt', output / 'Labels.txt')
        save()
        print(f'Continuous human clip ready: {video} ({len(frames)} frames)', flush=True)
    except Exception as error:
        manifest.update(status='failed', error=f'{type(error).__name__}: {error}')
        save()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.input, args.output)
