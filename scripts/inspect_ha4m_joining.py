# SPDX-License-Identifier: MPL-2.0
"""Build bounded action-9 contact sheets from the existing ten HA4M trials."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_pipeline.assembly_baseline import summarize_recording
from scripts.sample_ha4m import FRAME_PATTERN, RECORDINGS, digest, entries, fetch


def select_frames(start: int, end: int, count: int) -> list[int]:
    """Select nine in-action samples and available immediately adjacent frames."""
    if not 0 <= start < end <= count:
        raise ValueError('Invalid half-open action interval')
    selected = {start + round(i * (end - start - 1) / 8) for i in range(9)}
    if start:
        selected.add(start - 1)
    if end < count:
        selected.add(end)
    return sorted(selected)


def inspect(source: Path, output: Path) -> dict:
    """Verify label/index provenance, fetch <=110 frames, and retain review views."""
    source_bytes = (source / 'manifest.json').read_bytes()
    original = json.loads(source_bytes)
    if [row['recording_id'] for row in original['recordings']] != list(RECORDINGS):
        raise ValueError('Only the existing fixed ten-trial subset is supported')
    plans = []
    for row in original['recordings']:
        folder = source / row['recording_id']
        labels, listing = (folder / 'Labels.txt').read_bytes(), (folder / 'rgb-listing.xml').read_bytes()
        if digest(labels) != row['labels_sha256'] or digest(listing) != row['rgb_listing_sha256']:
            raise ValueError('Source checksum mismatch')
        frames = []
        for entry in entries(listing):
            match = FRAME_PATTERN.fullmatch(entry['href'].rsplit('/', 1)[-1])
            if match:
                frames.append({**entry, 'frame_id': int(match[1]), 'timestamp_us': int(match[2])})
        frames.sort(key=lambda f: f['frame_id'])
        summary = summarize_recording(labels.decode('utf-8-sig'), frames)
        segments = [s for s in summary['segments'] if s['action_id'] == 9]
        if len(segments) != 1:
            raise ValueError('Expected one contiguous block-joining interval')
        segment = segments[0]
        ids = select_frames(segment['start_frame'], segment['end_frame_exclusive'], len(frames))
        plans.append({'recording_id': row['recording_id'], 'segment': segment,
                      'selected_frames': [frames[i] for i in ids], 'frames': [],
                      'labels_sha256': digest(labels), 'rgb_listing_sha256': digest(listing)})
    sizes = [f['size'] for p in plans for f in p['selected_frames']]
    if any(not 0 < size <= 10 * 1024 * 1024 for size in sizes) or sum(sizes) > 500 * 1024 * 1024:
        raise ValueError('Targeted frame sample exceeds byte budget')
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'kind': 'ha4m-action9-sparse-inspection', 'source_manifest_sha256': digest(source_bytes),
                'status': 'downloading', 'recordings': plans, 'new_inference_calls': 0,
                'planned_png_bytes': sum(sizes), 'license': original['license'],
                'attribution': original['attribution'],
                'selection': 'Nine evenly spaced in-action frames plus immediately adjacent frames, per trial.',
                'limitations': ['Sparse images do not establish continuous motion, contact force, fit, or accepted output.',
                               'Crop views are review derivatives; original PNGs retained.']}

    def save() -> None:
        """Retain partial evidence without changing the original dataset run."""
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    save()
    try:
        for plan in plans:
            folder = output / plan['recording_id']
            folder.mkdir()

            def get_frame(frame: dict) -> dict:
                """Download one size-bounded original and validate its full PNG decode."""
                data = fetch(frame['href'], frame['size'])
                if len(data) != frame['size']:
                    raise ValueError('Frame byte count mismatch')
                with Image.open(io.BytesIO(data)) as image:
                    if image.format != 'PNG':
                        raise ValueError('Expected PNG')
                    image.load()
                    dimensions = list(image.size)
                target = folder / f'{frame["frame_id"]:06d}.png'
                target.write_bytes(data)
                return {**frame, 'path': target.relative_to(output).as_posix(),
                        'sha256': digest(data), 'dimensions': dimensions}

            with ThreadPoolExecutor(max_workers=4) as pool:
                for frame in pool.map(get_frame, plan['selected_frames']):
                    plan['frames'].append(frame)
                    save()
            for cropped in (False, True):
                sheet = Image.new('RGB', (1920, 4 * 460), '#202020')
                draw = ImageDraw.Draw(sheet)
                for i, frame in enumerate(plan['frames']):
                    with Image.open(output / frame['path']) as image:
                        image = image.convert('RGB')
                        if cropped:
                            w, h = image.size
                            image = image.crop((int(w * .2), int(h * .4), int(w * .85), h))
                        image.thumbnail((640, 420))
                        x, y = (i % 3) * 640, (i // 3) * 460
                        sheet.paste(image, (x, y + 40))
                        start_us = plan['selected_frames'][1 if plan['segment']['start_frame'] else 0]['timestamp_us']
                        relative = (frame['timestamp_us'] - start_us) / 1e6
                        draw.text((x + 8, y + 10), f'{plan["recording_id"]} f{frame["frame_id"]} action9 t={relative:.3f}s', fill='white')
                target = folder / ('joining-crop.jpg' if cropped else 'joining-full.jpg')
                sheet.save(target, quality=92)
                plan[target.stem + '_sha256'] = digest(target.read_bytes())
            save()
            print(f'Inspection sheets ready: {plan["recording_id"]}', flush=True)
        manifest['status'] = 'complete'
        save()
        return manifest
    except Exception as error:
        manifest.update(status='failed', error=f'{type(error).__name__}: {error}')
        save()
        raise


def main() -> None:
    """Build reproducible local evidence views without inference calls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    inspect(args.input, args.output)


if __name__ == '__main__':
    main()
