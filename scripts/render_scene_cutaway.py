# SPDX-License-Identifier: MPL-2.0
"""Render a separate, explicitly altered diagnostic scene without provider calls."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protocol_pipeline.e2e import native_capture
from protocol_pipeline.pipeline import save_json, sha256
from protocol_pipeline.visual_review import save_capture


def main() -> None:
    """Hide explicitly named parts in a new copy and preserve camera geometry/time."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--hide-name', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    scene = json.loads(args.scene.read_text(encoding='utf-8'))
    frames = json.loads(args.captures.read_text(encoding='utf-8'))['frames']
    altered = deepcopy(scene)
    removed = []
    for asset in altered['bundledAssets']:
        for part in asset['parts']:
            if part['name'] in args.hide_name:
                removed.append({'asset_id': asset['id'], 'part_id': part['id'], 'name': part['name']})
        asset['parts'] = [part for part in asset['parts'] if part['name'] not in args.hide_name]
        retained = {part['id'] for part in asset['parts']}

        def prune(node: dict) -> dict:
            """Keep the native hierarchy consistent with the diagnostic part list."""
            node['partIds'] = [part_id for part_id in node['partIds'] if part_id in retained]
            node['children'] = [child for child in (prune(child) for child in node['children'])
                                if child['partIds'] or child['children']]
            return node

        if asset.get('hierarchy'):
            prune(asset['hierarchy'])
    if {part['name'] for part in removed} != set(args.hide_name):
        raise ValueError('Every requested hidden name must match a bundled scene part')
    # Never overwrite historical captures or an earlier diagnostic run.
    args.output.mkdir(parents=True, exist_ok=False)
    label = 'DIAGNOSTIC CUTAWAY - enclosure removed - not final design'
    diagnostic_frames = [{**frame, 'label': label+' / '+frame['label']} for frame in frames]
    save_json(args.output/'scene.oi.json', altered)
    save_json(args.output/'provenance.json', {
        'mode': 'offline native diagnostic rendering', 'physical_validation': False,
        'label': label, 'source_scene': str(args.scene.resolve()), 'source_sha256': sha256(args.scene),
        'source_captures': str(args.captures.resolve()), 'captures_sha256': sha256(args.captures),
        'removed_parts': removed, 'original_frames': frames,
        'limitations': ['Altered diagnostic geometry, not a corrected machine or accepted review.',
                        'Part visibility does not establish assembly correctness or physical feasibility.'],
    })
    with native_capture() as capture:
        bundle = capture(altered, diagnostic_frames)
        save_capture(args.output/'renders', bundle)
    print(args.output)


if __name__ == '__main__':
    main()
