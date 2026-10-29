# SPDX-License-Identifier: MPL-2.0
"""Append an explicitly offline media/lab continuation of a verified saved run."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_pipeline.e2e import native_capture
from protocol_pipeline.environment import load_environment
from protocol_pipeline.lab_layout import plan_lab
from protocol_pipeline.pipeline import sha256
from protocol_pipeline.scene_video import export_scene_video
from protocol_pipeline.snapshots import allocate_snapshot, atomic_json, file_index, read_json, verify_snapshot
from protocol_pipeline.visual_review import save_capture


def finish(source: Path, root: Path) -> Path:
    """Reuse indexed artifacts in a new version; never rerun models or edit source."""
    original = verify_snapshot(source)
    for stage in ('extraction', 'proposal', 'cad', 'scene', 'visual_review'):
        if original['stages'].get(stage, {}).get('status') != 'completed':
            raise ValueError(f'Required source stage incomplete: {stage}')
    output = allocate_snapshot(root)
    document = copy.deepcopy(original)
    document.update(version=int(output.name[1:]), status='running', created_at=time.time(),
                    execution_mode='offline-media-lab-continuation', new_inference_calls=0,
                    parent={'version': original['version'], 'document_sha256': sha256(source)},
                    rerun_policy='reuse verified live stages; regenerate media and lab offline')
    document['source_runtime'] = document.pop('runtime', {})
    from protocol_pipeline.web import runtime_provenance
    document['runtime'] = runtime_provenance()
    for key in ('error', 'error_type', 'finished_at', 'files'):
        document.pop(key, None)
    for stage in document['stages'].values():
        stage['reused_from_version'] = original['version']
    atomic_json(output / 'snapshot.json', document)
    try:
        for row in original['files']:
            target = output / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source.parent / row['path'], target)
        run = output / document['run_path']
        scene = run / 'scene' / read_json(run / 'scene/job.json')['attempt_id']
        document['stages']['machine_video'] = {'status': 'running', 'started_at': time.time()}
        export_scene_video(scene)
        document['stages']['machine_video'].update(status='completed', finished_at=time.time())
        document['stages']['lab'] = {'status': 'running', 'started_at': time.time()}
        design = run / 'autonomy' / read_json(run / 'autonomy/job.json')['attempt_id'] / 'proposal.json'
        report, manifest = plan_lab(read_json(scene / 'scene.oi.json'), read_json(scene / 'preview.json'), read_json(design)['proposal'])
        report.update(source_scene_sha256=sha256(scene / 'scene.oi.json'), source_proposal_sha256=sha256(design))
        attempt = uuid.uuid4().hex
        lab = run / 'lab' / attempt
        atomic_json(lab / 'report.json', report)
        atomic_json(lab / 'scene.oi.json', manifest)
        atomic_json(run / 'lab/current.json', {'attempt_id': attempt})
        with native_capture() as capture:
            save_capture(lab / 'renders', capture(manifest))
        document['stages']['lab'].update(status='completed', finished_at=time.time())
        document['status'] = 'completed'
    except Exception as error:
        document.update(status='failed', error=str(error), error_type=type(error).__name__)
        for stage in document['stages'].values():
            if stage['status'] == 'running':
                stage.update(status='failed', error=str(error), finished_at=time.time())
        raise
    finally:
        document.update(files=file_index(output), finished_at=time.time())
        atomic_json(output / 'snapshot.json', document)
    verify_snapshot(output / 'snapshot.json')
    verify_snapshot(source)
    return output


if __name__ == '__main__':
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, default=Path('snapshots/e2e'))
    args = parser.parse_args()
    print(finish(args.source, args.output_root))
