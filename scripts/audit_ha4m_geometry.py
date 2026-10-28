# SPDX-License-Identifier: MPL-2.0
"""Offline source-CAD audit and hypothetical FJ-01 envelope checks (not fit validation)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys


def verify_source(source: Path) -> dict:
    """Verify every retained publisher/source byte before native geometry work."""
    manifest = json.loads((source / 'source-manifest.json').read_text())
    for name, expected in manifest['files'].items():
        path = source / name.replace('\\', '/')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Source checksum mismatch: {name}')
    return manifest


def audit(source: Path, output: Path) -> dict:
    """Import millimeter STEP geometry and measure explicit discrete guide poses."""
    manifest = verify_source(source)
    import cadquery as cq
    from OCP.gp import gp_Trsf
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    output.mkdir(parents=True, exist_ok=False)
    shapes = {}
    inventory = []
    for path in sorted((source / 'source-step').glob('*.STEP')):
        if not re.search(r'SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.\s*\)', path.read_text()):
            raise ValueError(f'Unverified units: {path.name}')
        shape = cq.importers.importStep(str(path)).val()
        if not shape.isValid():
            raise ValueError(f'Invalid source shape: {path.name}')
        shapes[path.name] = shape
        box = shape.BoundingBox()
        inventory.append({'file': path.name, 'valid': True, 'solids': len(shape.Solids()),
                          'volume_mm3': shape.Volume(),
                          'bounds_mm': {k: getattr(box, k) for k in
                                        ('xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax')}})

    # Proper rigid rotation: xL=88-zG, yL=xG-20, zL=22.5-yG.
    matrix = [[0, 0, -1, 88], [1, 0, 0, -20], [0, -1, 0, 22.5], [0, 0, 0, 1]]
    transform = gp_Trsf()
    transform.SetValues(*[value for row in matrix[:3] for value in row])
    assembly = shapes['00_PlanetaryGearbox_NEW.STEP'].transformShape(cq.Matrix(transform))
    ring = shapes['01_RingGear_OFFSET_0.2_NEW.STEP']
    assembled_ring = assembly.Solids()[0]
    overlap = ring.intersect(assembled_ring).Volume()
    registration = {'standalone_volume_mm3': ring.Volume(),
                    'assembly_ring_volume_mm3': assembled_ring.Volume(),
                    'intersection_mm3': overlap,
                    'symmetric_difference_mm3': ring.Volume() + assembled_ring.Volume() - 2 * overlap}
    if overlap / ring.Volume() < .999:
        raise ValueError('Ring-local registration failed overlap check')

    def arc(start: float) -> cq.Shape:
        """Make an exact 90-degree annular sector, without a polygon approximation."""
        def point(radius: float, angle: float) -> tuple[float, float]:
            """Convert an explicit angle to planar millimeter coordinates."""
            return radius * math.cos(math.radians(angle)), radius * math.sin(math.radians(angle))
        return (cq.Workplane('XY').moveTo(*point(73.5, start))
                .threePointArc(point(73.5, start + 45), point(73.5, start + 90))
                .lineTo(*point(78.5, start + 90))
                .threePointArc(point(78.5, start + 45), point(78.5, start))
                .close().extrude(12.5).val())

    collar = cq.Workplane('XY').circle(78.5).circle(73.5).extrude(12.5).val()
    arcs = cq.Compound.makeCompound([arc(45), arc(225)])
    guides = {'full_collar': collar, 'open_arcs': arcs}
    rows = []
    for name, guide in guides.items():
        if not guide.isValid():
            raise ValueError('Invalid candidate envelope')
        cq.exporters.export(guide, str(output / f'{name}.step'))
        for angle in (-45, -30, -15, 0, 15, 30, 45):
            for axial in (-20, 0, 20):
                posed = assembled_ring.rotate((0, 0, 0), (0, 0, 1), angle).translate((0, 0, axial))
                volume = guide.intersect(posed).Volume()
                rows.append({'guide': name, 'rotation_deg': angle, 'axial_mm': axial,
                             'intersection_mm3': volume, 'positive_volume_collision': volume > 1e-5,
                             'minimum_distance_mm': guide.distance(posed)})
        print(f'Completed {name} discrete ring checks', flush=True)

    nominal = {name: [{'solid_index': i, 'intersection_mm3': guide.intersect(solid).Volume()}
                      for i, solid in enumerate(assembly.Solids())] for name, guide in guides.items()}
    # Render tessellated source surfaces; collision results above use native B-reps.
    fig = plt.figure(figsize=(14, 7))
    for panel, (name, guide) in enumerate(guides.items(), 1):
        ax = fig.add_subplot(1, 2, panel, projection='3d')
        for shape, color, alpha in ((assembly, '#8098aa', .22), (guide, '#e47b26', .85)):
            vertices, triangles = shape.tessellate(1.0, .2)
            points = [v.toTuple() for v in vertices]
            ax.add_collection3d(Poly3DCollection([[points[i] for i in tri] for tri in triangles],
                                                facecolor=color, alpha=alpha, linewidths=0))
        ax.set(xlim=(-100, 100), ylim=(-100, 100), zlim=(-50, 50),
               xlabel='ring-local x (mm)', ylabel='y (mm)', zlabel='z (mm)', title=name)
        ax.set_box_aspect((2, 2, 1))
        ax.view_init(elev=55, azim=35)
    fig.suptitle('Hypothetical envelopes / publisher final assembly — not recorded joining pose')
    fig.savefig(output / 'guide-review.png', dpi=160)
    plt.close(fig)
    report = {'kind': 'offline-native-geometry-envelope-audit', 'source_doi': manifest['doi'],
              'source_license': manifest['license'], 'source_hashes_verified': True,
              'cadquery_version': cq.__version__, 'units': 'mm', 'inventory': inventory,
              'assembly_to_ring_local': matrix, 'registration': registration,
              'assumptions': {'inner_radius_mm': 73.5, 'outer_radius_mm': 78.5,
                              'z_mm': [0, 12.5], 'open_arcs_deg': [[45, 135], [225, 315]],
                              'positive_volume_threshold_mm3': 1e-5},
              'discrete_ring_checks': rows, 'nominal_assembly_checks': nominal,
              'limitations': ['No continuous sweep, tilt, lateral-offset or tolerance test.',
                              'Whole-ring poses are envelope probes, not valid geared-assembly kinematics.',
                              'No guide base, lead-in, fastening or lower-support registration designed.',
                              'Open angular windows are not validated human hand or tool access.',
                              'Publisher final assembly is not registered to recorded action-9 pose.',
                              'No physical validation, quality acceptance or savings measurement.'],
              'new_inference_calls': 0}
    report['artifact_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in output.iterdir() if p.is_file()}
    (output / 'audit.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> None:
    """Run in a disposable native worker with a new evidence directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.input, args.output)


if __name__ == '__main__':
    main()
    # Match machine_worker: avoid OCCT DLL finalizer crashes only after successful writes.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
