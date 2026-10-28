# SPDX-License-Identifier: MPL-2.0
"""Tessellate verified publisher gearbox STEP without substituting proxy geometry."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_ha4m_geometry import verify_source


def prepare(source: Path, output: Path) -> None:
    """Retain all source solids, applying only a rigid pose and mm-to-m conversion."""
    import cadquery as cq

    provenance = verify_source(source)
    path = source / 'source-step/00_PlanetaryGearbox_NEW.STEP'
    shape = cq.importers.importStep(str(path)).val()
    if not shape.isValid() or len(shape.Solids()) != 13:
        raise ValueError('Expected the valid 13-solid publisher assembly')
    output.mkdir(parents=True, exist_ok=False)
    ident = 'mindbot-source-gearbox'
    parts = []
    for index, solid in enumerate(shape.Solids()):
        vertices, faces = solid.tessellate(.15, .15)
        # Proper rigid orientation: horizontal ring, source tab axes on scene X.
        # Pose only, not inferred alignment to the filmed hardware.
        transformed = [[(88-v.z)/1000, (119-v.y)/1000, (20-v.x)/1000] for v in vertices]
        parts.append({'id': f'{ident}/solid-{index}', 'name': f'Publisher STEP solid {index}',
                      'vertices': [n for point in transformed for n in point],
                      'indices': [n for face in faces for n in face],
                      'color': [.88, .87, .81] if index == 0 else [.52, .61, .65],
                      'metadata': {'representation': 'Publisher STEP tessellation; rigid pose only',
                                   'sourceId': f'publisher-solid-{index}'}})
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    asset = {'id': ident, 'name': 'MindBot original 13-solid gearbox (reference CAD)',
             'schemaVersion': 1, 'units': 'm', 'upAxis': 'Y',
             'dimensions': [.176, .089, .145], 'originOffset': [0, 0, 0],
             'source': {'kind': 'generated', 'generator': 'form-industries',
                        'filename': path.name, 'digest': digest},
             'parts': parts,
             'hierarchy': {'id': ident+'/root', 'name': 'Publisher assembly',
                           'partIds': [p['id'] for p in parts], 'children': []},
             'warnings': ['Reference CAD identity with recorded hardware is unverified.',
                          'No screw solids in publisher assembly; fastening targets are design assumptions.']}
    (output / 'gearbox.asset.json').write_text(json.dumps(asset)+'\n')
    (output / path.name).write_bytes(path.read_bytes())
    record = {'source_doi': provenance['doi'], 'license': provenance['license'],
              'source_step_sha256': digest, 'source_manifest': provenance,
              'source_solids': 13, 'exported_parts': len(parts), 'units_conversion': 'mm to m',
              'rigid_pose': 'scene_m = [(88-z)/1000, (119-y)/1000, (20-x)/1000]',
              'tessellation_tolerance_mm': .15, 'angular_tolerance_rad': .15,
              'mesh_sha256': hashlib.sha256((output/'gearbox.asset.json').read_bytes()).hexdigest(),
              'geometry_reconstruction': False, 'physical_validation': False}
    (output / 'provenance.json').write_text(json.dumps(record, indent=2)+'\n')
    # Separate proposed hardware, never merged into the publisher's thirteen solids.
    screw = cq.Workplane('XY').circle(2.5).extrude(10).union(
        cq.Workplane('XY').workplane(offset=10).circle(4).extrude(5))
    socket = cq.Workplane('XY').workplane(offset=12).polygon(6, 4.618802).extrude(4)
    screw = screw.cut(socket).val()
    if not screw.isValid():
        raise ValueError('Invalid proposed fastener geometry')
    vertices, faces = screw.tessellate(.05, .15)
    additions = []
    for side, x in (('left', -.0805), ('right', .0805)):
        additions.append({'id': 'proposed-fastener-'+side, 'name': 'Proposed socket screw '+side,
                          'vertices': [n for v in vertices for n in (x+v.x/1000, .1045+v.z/1000, -v.y/1000)],
                          'indices': [n for face in faces for n in face], 'color': [.28, .31, .35],
                          'metadata': {'representation': 'Assistant-authored illustrative screw; not publisher geometry'}})
    (output / 'proposed-fasteners.json').write_text(json.dumps({
        'parts': additions, 'assumptions': '5mm shank, 8mm head, 4mm hex socket; posed at reference tab targets; specification and fit unverified.',
        'physical_validation': False})+'\n')
    print(output, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source, args.output)
    # Native OCCT finalizer workaround, matching the existing geometry audit worker.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
