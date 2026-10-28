# SPDX-License-Identifier: MPL-2.0
"""Append an authored joining illustration using saved CAD and labeled proxy parts."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_pipeline.scene_video import export_scene_video
from protocol_pipeline.snapshots import allocate_snapshot, atomic_json, file_index, read_json, verify_snapshot


def ring_mesh(outer: float, inner: float, height: float) -> tuple[list[float], list[int]]:
    """Create an explicit annular proxy mesh in meters, not source component CAD."""
    vertices, indices = [], []
    count = 48
    for y, radius in ((0, outer), (height, outer), (0, inner), (height, inner)):
        for i in range(count):
            angle = 2 * math.pi * i / count
            vertices.extend([radius * math.cos(angle), y, radius * math.sin(angle)])
    for a, b in ((0, 1), (1, 3), (3, 2), (2, 0)):
        for i in range(count):
            j = (i + 1) % count
            indices.extend([a * count + i, b * count + i, b * count + j,
                            a * count + i, b * count + j, a * count + j])
    return vertices, indices


def animate(source: Path, root: Path) -> Path:
    """Preserve the live run; create a distinct, explicitly authored presentation version."""
    original = verify_snapshot(source)
    run_source = source.parent / original['run_path']
    job = read_json(run_source / 'scene/job.json')
    scene_source = run_source / 'scene' / job['attempt_id']
    scene = read_json(scene_source / 'scene.oi.json')
    if len(scene['instances']) != 1 or scene['instances'][0]['rotation'] != [0, 0, 0]:
        raise ValueError('This reviewed illustration requires one unrotated integrated station')
    machine = scene['instances'][0]
    asset = next(a for a in scene['bundledAssets'] if a['id'] == machine['assetId'])
    parts = {p['metadata'].get('sourceId'): p for p in asset['parts']}
    names = {'x_carriage', 'z_guide', 'z_ram', 'force_sensor', 'gripper_palm', 'finger_left', 'finger_right', 'input_nest', 'output_nest'}
    if not names <= parts.keys():
        raise ValueError('Expected generated moving bodies and nests are missing')
    # This trajectory is tied to the reviewed v11 CAD coordinates, never generic.
    for name, expected in (('input_nest', -.1), ('output_nest', .1)):
        xs = parts[name]['vertices'][0::3]
        if abs((min(xs) + max(xs)) / 2 - expected) > .001:
            raise ValueError('Station geometry changed; re-review the authored trajectory')
    output = allocate_snapshot(root.resolve())
    document = copy.deepcopy(original)
    document.update(version=int(output.name[1:]), status='running', created_at=time.time(),
                    execution_mode='authored-concept-animation-continuation', new_inference_calls=0,
                    parent={'version': original['version'], 'document_sha256': hashlib.sha256(source.read_bytes()).hexdigest()},
                    presentation_limitations=['Motion and workpiece proxies authored by assistant, not generated operating kinematics.',
                                             'Proxy sizes are illustrative and do not reproduce the original HA4M CAD dimensions.',
                                             'No collision, fit, force, gear engagement or timing validation.'])
    for row in original['files']:
        target = output / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.parent / row['path'], target)
    run = output / document['run_path']
    attempt = uuid.uuid4().hex
    folder = run / 'scene' / attempt
    folder.mkdir()
    document['stages']['concept_animation'] = {'status': 'running', 'started_at': time.time()}
    try:
        for row in scene['animation'].get('tracks', []):
            if row.get('instanceId') == machine['id']:
                raise ValueError('Refusing to replace existing machine motion')
        tracks = []

        def track(instance: str, poses: list, part: str | None = None) -> None:
            """Add native OpenIndustries keys with explicit absolute part offsets."""
            ident = instance + ':' + (part or 'instance')
            row = {'id': ident, 'instanceId': instance, 'keys': [
                {'id': f'{ident}-{i}', 'time': t, 'position': pos, 'rotation': [0, 0, 0]}
                for i, (t, pos) in enumerate(poses)]}
            if part:
                row['partId'] = part
            tracks.append(row)

        # Time, carriage offset, vertical offset, jaw offset from saved mesh pose.
        poses = [(0, 0, .08, .017), (1.2, -.2, .08, .017), (2.2, -.2, -.01, .017),
                 (2.6, -.2, -.01, .012), (3.6, -.2, .08, .012), (5, 0, .08, .012),
                 (6.4, 0, .016, .012), (7.2, 0, .016, .012), (7.6, 0, .016, .017),
                 (8.8, 0, .08, .017), (10, 0, .08, .017)]
        for name in ('x_carriage', 'z_guide', 'z_ram', 'force_sensor', 'gripper_palm', 'finger_left', 'finger_right'):
            offsets = []
            for t, dx, dy, jaw in poses:
                offsets.append((t, [dx + (-jaw if name == 'finger_left' else jaw if name == 'finger_right' else 0),
                                     0 if name in ('x_carriage', 'z_guide') else dy, 0]))
            track(machine['id'], offsets, parts[name]['id'])
            parts[name]['color'] = [.22, .48, .64] if name in ('x_carriage', 'z_guide') else [.28, .34, .38]

        def proxy(ident: str, outer: float, inner: float, height: float, position: list, color: list) -> None:
            """Add a visibly colored, explicitly illustrative workpiece actor."""
            vertices, indices = ring_mesh(outer, inner, height)
            part = {'id': ident + '/part', 'name': ident, 'vertices': vertices, 'indices': indices,
                    'color': color, 'metadata': {'representation': 'Authored proxy, assumed dimensions; not source CAD'}}
            actor = {'id': ident, 'name': ident, 'schemaVersion': 1, 'units': 'm', 'upAxis': 'Y',
                     'dimensions': [outer * 2, height, outer * 2], 'originOffset': [0, 0, 0],
                     'source': {'kind': 'generated', 'generator': 'form-industries', 'filename': ident + '.json',
                                'digest': hashlib.sha256(json.dumps(part).encode()).hexdigest()},
                     'parts': [part], 'hierarchy': {'id': ident + '/root', 'name': ident,
                                                  'partIds': [part['id']], 'children': []},
                     'warnings': ['Illustrative proxy only; not the HA4M part model.']}
            scene['bundledAssets'].append(actor)
            scene['assets'].append({k: actor[k] for k in ('id', 'name', 'source', 'dimensions')})
            scene['instances'].append({'id': ident, 'name': ident, 'assetId': ident, 'position': position,
                                       'rotation': [0, 0, 0], 'visible': True})

        base = machine['position']
        def world(x: float, y: float) -> list[float]:
            """Convert the unrotated station-local proxy position to world coordinates."""
            return [base[0] + x, base[1] + y, base[2]]
        proxy('upper-proxy', .04, .023, .012, world(-.1, .03), [.96, .64, .16])
        proxy('lower-proxy', .034, .014, .02, world(.1, .036), [.16, .64, .52])
        track('upper-proxy', [(t, world(-.1, .03) if t <= 2.6 else world(.1, .056) if t >= 7.2
                              else world(.1 + dx, .04 + dy)) for t, dx, dy, jaw in poses])
        scene['animation'] = {'duration': 10, 'loop': False, 'tracks': tracks}
        scene['storyboard'] = {'caption': 'Authored concept motion + proxy parts | not physical execution',
                               'basis': 'Assistant-authored illustration of reviewed upper-transfer/lower-support sequence'}
        labels = [(0, 2.6, '1 / Acquire upper proxy from staging'), (2.6, 5, '2 / Lift and transfer upper proxy'),
                  (5, 7.2, '3 / Lower onto supported lower proxy'), (7.2, 10, '4 / Release and retract (proposed)')]
        preview = read_json(scene_source / 'preview.json')
        template = preview['segments'][0]
        preview.update(duration=10, segments=[{**template, 'start_s': start, 'end_s': end, 'label': label,
                                              'implementation': label + '; authored timing and proxy geometry.'}
                                             for start, end, label in labels])
        report = read_json(scene_source / 'scene-report.json')
        report.update(duration_s=10, animation_tracks=len(tracks), instances=len(scene['instances']))
        report['limitations'] += document['presentation_limitations']
        atomic_json(folder / 'scene.oi.json', scene)
        atomic_json(folder / 'preview.json', preview)
        atomic_json(folder / 'scene-report.json', report)
        atomic_json(folder / 'concept-provenance.json', {'source_snapshot_sha256': document['parent']['document_sha256'],
                    'original_cad_mesh_vertices_unchanged': True, 'motion': 'authored', 'workpieces': 'assumed proxies',
                    'limitations': document['presentation_limitations']})
        export_scene_video(folder)
        job.update(attempt_id=attempt, stage='completed', finished_at=time.time(), authored_animation=True)
        atomic_json(run / 'scene/job.json', job)
        document['stages']['concept_animation'].update(status='completed', finished_at=time.time())
        document['status'] = 'completed'
    except Exception as error:
        document.update(status='failed', error_type=type(error).__name__, error=str(error))
        document['stages']['concept_animation'].update(status='failed', error=str(error))
        raise
    finally:
        document.update(finished_at=time.time(), files=file_index(output))
        atomic_json(output / 'snapshot.json', document)
    verify_snapshot(output / 'snapshot.json')
    verify_snapshot(source)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, default=Path('snapshots/e2e'))
    args = parser.parse_args()
    print(animate(args.source, args.output_root))
