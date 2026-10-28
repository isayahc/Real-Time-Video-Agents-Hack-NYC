# SPDX-License-Identifier: MPL-2.0
"""Package a saved, improved CAD candidate into an offline native lab continuation."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protocol_pipeline.e2e import native_capture
from protocol_pipeline.environment import load_environment
from protocol_pipeline.lab_layout import plan_lab
from protocol_pipeline.pipeline import sha256
from protocol_pipeline.snapshots import atomic_json, contained_file, file_index, read_json, verify_snapshot
from protocol_pipeline.visual_review import VisualCritique, save_capture, visibly_improved


def main() -> None:
    """Reuse verified artifacts without calling inference or changing historical runs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--source-snapshot', type=Path, required=True)
    parser.add_argument('--source-review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    load_environment()
    verify_snapshot(args.source_snapshot)
    hashes = read_json(args.candidate/'artifact-hashes.json')
    for relative, digest in hashes.items():
        if sha256(contained_file(args.candidate, relative.replace('\\', '/'))) != digest:
            raise ValueError(f'Candidate checksum mismatch: {relative}')
    required = ['before-critique.json', 'after-critique.json', 'scene/scene.oi.json',
                'scene/preview.json', 'provenance.json']
    indexed = {name.replace('\\', '/') for name in hashes}
    if not set(required).issubset(indexed):
        raise ValueError('Candidate index omits required review/scene evidence')
    provenance = read_json(args.candidate/'provenance.json')
    if provenance['source_snapshot_sha256'] != sha256(args.source_snapshot):
        raise ValueError('Candidate belongs to a different source snapshot')
    before = VisualCritique.model_validate(read_json(args.candidate/'before-critique.json'))
    after = VisualCritique.model_validate(read_json(args.candidate/'after-critique.json'))
    if not visibly_improved(before, after):
        raise ValueError('Candidate did not pass the existing visual-improvement gate')
    source_root = args.source_snapshot.resolve().parent
    for name in ['source-proposal.json', 'source-protocol.json']:
        relative = (args.source_review/name).resolve().relative_to(source_root).as_posix()
        contained_file(source_root, relative)
        entries = {row['path']: row['sha256'] for row in read_json(args.source_snapshot)['files']}
        if entries.get(relative) != sha256(args.source_review/name):
            raise ValueError('Source review inputs are not indexed by the source snapshot')
    args.output.mkdir(parents=True, exist_ok=False)
    document = {'kind': 'offline-lab-continuation', 'status': 'running',
                'physical_validation': False, 'new_inference_calls': 0,
                'source_snapshot_sha256': sha256(args.source_snapshot),
                'candidate_index_sha256': sha256(args.candidate/'artifact-hashes.json'),
                'before_score': before.score, 'after_score': after.score,
                'limitations': ['Reuses saved live CAD and critiques; not a fresh all-stage E2E run.',
                                'Lab placement is offline and has not received a live visual critique.',
                                'Inspection-open housing does not establish protective performance.']}
    try:
        shutil.copytree(args.candidate, args.output/'candidate')
        for name in ['source-proposal.json', 'source-protocol.json']:
            shutil.copy2(args.source_review/name, args.output/name)
        proposal = read_json(args.output/'source-proposal.json')['proposal']
        original = read_json(args.output/'candidate/scene/scene.oi.json')
        preview = read_json(args.output/'candidate/scene/preview.json')
        report, scene = plan_lab(original, preview, proposal)
        if report['status'] != 'planned':
            raise ValueError('Lab planner could not place every instance')
        original_assets = {asset['id']: asset for asset in original['bundledAssets']}
        result_assets = {asset['id']: asset for asset in scene['bundledAssets']}
        if any(result_assets.get(key) != value for key, value in original_assets.items()):
            raise ValueError('Lab planning unexpectedly modified original CAD assets')
        report.update(source_scene_sha256=sha256(args.output/'candidate/scene/scene.oi.json'),
                      source_proposal_sha256=sha256(args.output/'source-proposal.json'),
                      physical_validation=False)
        atomic_json(args.output/'lab/report.json', report)
        atomic_json(args.output/'lab/scene.oi.json', scene)
        with native_capture() as capture:
            save_capture(args.output/'lab/renders', capture(scene, None))
        document.update(status='completed', machine_assets_unchanged=True,
                        placed_count=report['placed_count'], total_count=report['total_count'])
    except Exception as error:
        document.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        document['files'] = file_index(args.output)
        atomic_json(args.output/'continuation.json', document)
        verify_snapshot(args.source_snapshot)
    print(args.output)


if __name__ == '__main__':
    main()
