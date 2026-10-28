# SPDX-License-Identifier: MPL-2.0
"""Encode existing native scene animation for side-by-side review, without inference."""
from __future__ import annotations

import base64
import math
from pathlib import Path
import subprocess
import tempfile

from .pipeline import sha256
from .snapshots import atomic_json, read_json
from .viewer import native_viewer_bundle


def export_scene_video(folder: Path) -> dict:
    """Render actual saved keyframes; never invent a physical operating cycle."""
    from playwright.sync_api import sync_playwright

    manifest = read_json(folder / 'scene.oi.json')
    preview = read_json(folder / 'preview.json')
    duration = float(preview['duration'])
    if not math.isfinite(duration) or not 0 < duration <= 120:
        raise ValueError('Scene video duration must be within (0, 120] seconds')
    for name in ('storyboard.mp4', 'storyboard.gif'):
        if (folder / name).exists():
            raise ValueError('Refusing to overwrite existing machine video')
    manifest.setdefault('storyboard', {}).setdefault('caption', 'Generated CAD concept | assumed timing | not physical execution')
    fps = 12
    count = math.ceil(duration * fps)
    with tempfile.TemporaryDirectory(prefix='scene-video-') as temporary:
        temp = Path(temporary)
        bundle = native_viewer_bundle(temp)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=['--enable-unsafe-swiftshader'])
            try:
                page = browser.new_page()
                page.add_script_tag(path=str(bundle))
                page.evaluate('(document) => {window.capture = OpenIndustriesNative.storyboardCapture(document)}', manifest)
                for index in range(count):
                    time_s = index / fps
                    segment = next((s for s in preview['segments'] if s['start_s'] <= time_s < s['end_s']), preview['segments'][-1])
                    data = page.evaluate('([time,label]) => window.capture.frame(time,label)', [time_s, segment['label']])
                    (temp / f'{index:05d}.png').write_bytes(base64.b64decode(data.split(',', 1)[1], validate=True))
                page.evaluate('() => window.capture.dispose()')
            finally:
                browser.close()
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-n', '-framerate', str(fps), '-i',
                        str(temp / '%05d.png'), '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', str(folder / 'storyboard.mp4')], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-n', '-i', str(folder / 'storyboard.mp4'),
                        '-vf', 'fps=8,scale=640:-2', str(folder / 'storyboard.gif')], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(folder / 'storyboard.mp4'), '-f', 'null', '-'], check=True)
    report = {'basis': 'Existing generated-scene keyframes; illustrative concept, not validated machine kinematics',
              'video': 'storyboard.mp4', 'gif': 'storyboard.gif', 'fps': fps, 'frames': count,
              'duration_s': count / fps, 'source_scene_sha256': sha256(folder / 'scene.oi.json'),
              'video_sha256': sha256(folder / 'storyboard.mp4'), 'physical_validation': False,
              'new_inference_calls': 0}
    atomic_json(folder / 'storyboard-report.json', report)
    scene_report = read_json(folder / 'scene-report.json')
    scene_report['storyboard'] = report
    atomic_json(folder / 'scene-report.json', scene_report)
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    export_scene_video(parser.parse_args().folder)
