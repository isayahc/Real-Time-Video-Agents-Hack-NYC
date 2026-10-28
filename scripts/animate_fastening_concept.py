# SPDX-License-Identifier: MPL-2.0
"""Append a source-CAD fastening illustration with explicitly authored tool motion."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_pipeline.pipeline import sha256
from protocol_pipeline.scene_video import export_scene_video
from protocol_pipeline.snapshots import allocate_snapshot, atomic_json, file_index, read_json, verify_snapshot


def compose(scene: dict, source_asset: dict, fasteners: dict | None = None) -> tuple[dict, dict]:
    """Require the reviewed driver coordinate contract, then add reference CAD and motion."""
    scene = copy.deepcopy(scene)
    if len(scene['instances']) != 1:
        raise ValueError('Fastening illustration requires one integrated generated machine')
    machine = scene['instances'][0]
    asset = next(a for a in scene['bundledAssets'] if a['id'] == machine['assetId'])
    parts = {p.get('metadata', {}).get('sourceId'): p for p in asset['parts']}
    traveling = ('z_slide', 'spindle_housing', 'rotating_chuck', 'hex_bit')
    for name in ('x_carriage', *traveling):
        if name not in parts:
            raise ValueError(f'Missing separately animatable body: {name}')
    for name, part in parts.items():
        part['color'] = ([.96, .51, .12] if name == 'rotating_chuck' else
                         [.18, .21, .25] if name == 'hex_bit' else
                         [.16, .37, .51] if name in ('x_carriage', 'z_slide', 'spindle_housing') else
                         [.34, .40, .43] if name in ('base_frame', 'rear_gantry') else [.51, .58, .60])
    if fasteners:
        additions = copy.deepcopy(fasteners['parts'])
        asset['parts'].extend(additions)
        asset['hierarchy']['partIds'].extend(p['id'] for p in additions)
    bit = parts['hex_bit']['vertices']
    bounds = [(min(bit[i::3]), max(bit[i::3])) for i in range(3)]
    axis_x, axis_z = [(lo+hi)/2 for lo, hi in (bounds[0], bounds[2])]
    if abs(axis_x + .0805) > .002 or abs(axis_z) > .002 or abs(bounds[1][0] - .180) > .003:
        raise ValueError(f'Generated bit violates reviewed pose contract: {bounds}')
    if len(source_asset['parts']) != 13:
        raise ValueError('Expected all thirteen publisher source solids')
    if scene.get('animation', {}).get('tracks'):
        raise ValueError('Refusing to replace existing generated animation tracks')
    # Turn the entire scene so the native camera looks into the open front.
    machine.update(position=[0, 0, 0], rotation=[0, 180, 0])
    scene['bundledAssets'].append(copy.deepcopy(source_asset))
    scene['assets'].append({k: source_asset[k] for k in ('id', 'name', 'source', 'dimensions')})
    scene['instances'].append({'id': 'reference-gearbox', 'name': source_asset['name'],
                              'assetId': source_asset['id'], 'position': [0, 0, 0],
                              'rotation': [0, 180, 0], 'visible': True})
    # The two axis locations come from reference CAD; not a video-derived screw count.
    # Proposed screw head contact above the tab, not a claimed seating measurement.
    contact_y = .117 if fasteners else .1195
    down = contact_y - bounds[1][0]
    poses = [(0, 0, 0), (1, 0, 0), (2, 0, down), (5, 0, down),
             (6, 0, 0), (7.5, .161, 0), (8.5, .161, down),
             (11.5, .161, down), (12.5, .161, 0), (14, .161, 0)]
    tracks = []
    for name in ('x_carriage', *traveling):
        keys = []
        times = sorted({t for t, _, _ in poses} | {2+i/8 for i in range(25)} | {8.5+i/8 for i in range(25)})
        for i, t in enumerate(times):
            left = max((p for p in poses if p[0] <= t), key=lambda p: p[0])
            right = min((p for p in poses if p[0] >= t), key=lambda p: p[0])
            mix = 0 if right[0] == left[0] else (t-left[0])/(right[0]-left[0])
            dx, dy = [left[j]+mix*(right[j]-left[j]) for j in (1, 2)]
            angle = 360 * (max(0, min(3, t-2)) + max(0, min(3, t-8.5)))
            keys.append({'id': f'{name}-{i}', 'time': t,
                         'position': [dx, 0 if name == 'x_carriage' else dy, 0],
                         'rotation': [0, angle if name in ('rotating_chuck', 'hex_bit') else 0, 0]})
        tracks.append({'id': machine['id']+':'+parts[name]['id'], 'instanceId': machine['id'],
                       'partId': parts[name]['id'], 'keys': keys})
    if fasteners:
        for part, start in zip(fasteners['parts'], (2, 8.5)):
            keys = [{'id': part['id']+f'-{i}', 'time': t, 'position': [0, 0, 0],
                     'rotation': [0, 360*max(0, min(3, t-start)), 0]}
                    for i, t in enumerate(sorted({0, 14} | {start+j/8 for j in range(25)}))]
            tracks.append({'id': machine['id']+':'+part['id'], 'instanceId': machine['id'],
                           'partId': part['id'], 'keys': keys})
    scene['animation'] = {'duration': 14, 'loop': False, 'tracks': tracks}
    scene['storyboard'] = {'caption': 'Original reference CAD | authored motion | fastening not physically validated'}
    evidence = {'basis': 'Assistant-authored feed, traverse and rotation; live-generated station and publisher workpiece CAD',
                'proposed_fasteners': fasteners.get('assumptions') if fasteners else None,
                'source_workpiece_parts': 13, 'source_workpiece_mesh_unchanged': True,
                'bit_neutral_bounds_m': bounds, 'proposed_tool_axes_m': [[-.0805, 0], [.0805, 0]],
                'proposed_contact_y_m': contact_y, 'duration_s': 14,
                'limitations': ['CAD identity with filmed hardware is unverified.',
                                'Fastener locations, tool dimensions, rotations and timing are design assumptions; no thread advance is modeled.',
                                'No torque control, contact physics, seating, continuous collision or safety validation.',
                                'Inherited model critique and lab do not validate this added geometry or motion.'],
                'physical_validation': False, 'new_inference_calls': 0}
    return scene, evidence


def animate(source: Path, asset_folder: Path, root: Path) -> Path:
    """Append an independently indexed derivative without changing the live snapshot."""
    original = verify_snapshot(source)
    provenance = read_json(asset_folder / 'provenance.json')
    if sha256(asset_folder / 'gearbox.asset.json') != provenance['mesh_sha256']:
        raise ValueError('Source mesh checksum mismatch')
    if sha256(asset_folder / '00_PlanetaryGearbox_NEW.STEP') != provenance['source_step_sha256']:
        raise ValueError('Source STEP checksum mismatch')
    old_run = source.parent / original['run_path']
    job = read_json(old_run / 'scene/job.json')
    old_scene = old_run / 'scene' / job['attempt_id']
    additions = asset_folder/'proposed-fasteners.json'
    scene, evidence = compose(read_json(old_scene/'scene.oi.json'), read_json(asset_folder/'gearbox.asset.json'),
                              read_json(additions) if additions.exists() else None)
    output = allocate_snapshot(root.resolve())
    document = copy.deepcopy(original)
    document.pop('presentation_pending', None)
    document.update(version=int(output.name[1:]), status='running', created_at=time.time(),
                    execution_mode='source-cad-authored-fastening-animation', new_inference_calls=0,
                    parent={'version': original['version'], 'document_sha256': sha256(source)},
                    presentation_limitations=evidence['limitations'])
    for row in document['stages'].values():
        row['reused_from_version'] = original['version']
    document['stages']['fastening_animation'] = {'status': 'running', 'started_at': time.time()}
    try:
        for row in original['files']:
            target = output / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source.parent / row['path'], target)
        run = output / document['run_path']
        shutil.copytree(asset_folder, run / 'source-gearbox')
        attempt = uuid.uuid4().hex
        folder = run / 'scene' / attempt
        folder.mkdir()
        preview = read_json(old_scene / 'preview.json')
        labels = [(0, 1, '1 / Gearbox held in fixture; align driver'), (1, 2, '2 / Feed driver toward first target'),
                  (2, 5, '3 / Rotate driver at first target'), (5, 6, '4 / Retract driver'),
                  (6, 7.5, '5 / Traverse above the fixed gearbox'), (7.5, 8.5, '6 / Feed toward second target'),
                  (8.5, 11.5, '7 / Rotate driver at second target'), (11.5, 14, '8 / Retract; proposed cycle ends')]
        template = preview['segments'][0]
        preview.update(duration=14, segments=[{**template, 'start_s': a, 'end_s': b, 'label': label,
                                               'implementation': label+'; authored illustration'} for a, b, label in labels])
        report = read_json(old_scene/'scene-report.json')
        report.update(duration_s=14, animation_tracks=len(scene['animation']['tracks']), instances=2)
        report['limitations'] += evidence['limitations']
        atomic_json(folder/'scene.oi.json', scene)
        atomic_json(folder/'preview.json', preview)
        atomic_json(folder/'scene-report.json', report)
        atomic_json(folder/'concept-provenance.json', evidence)
        export_scene_video(folder)
        job.update(attempt_id=attempt, stage='completed', finished_at=time.time(), authored_animation=True)
        atomic_json(run/'scene/job.json', job)
        document['stages']['fastening_animation'].update(status='completed', finished_at=time.time())
        document['status'] = 'completed'
    except Exception as error:
        document.update(status='failed', error=str(error), error_type=type(error).__name__)
        document['stages']['fastening_animation'].update(status='failed', error=str(error))
        raise
    finally:
        document.update(finished_at=time.time(), files=file_index(output))
        atomic_json(output/'snapshot.json', document)
    verify_snapshot(output/'snapshot.json')
    verify_snapshot(source)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--asset', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, default=Path('snapshots/e2e'))
    args = parser.parse_args()
    print(animate(args.source, args.asset, args.output_root))
