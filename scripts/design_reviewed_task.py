# SPDX-License-Identifier: MPL-2.0
"""Append a design/CAD snapshot from an explicitly reviewed saved extraction."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_pipeline.compiler import compile_protocol_file
from protocol_pipeline.e2e import PipelineRun, native_capture, preflight
from protocol_pipeline.environment import load_environment
from protocol_pipeline.pipeline import sha256, verify_manifest
from protocol_pipeline.snapshots import E2EConfig, allocate_snapshot, atomic_json, copy_source, file_index, read_json
from protocol_pipeline.web import runtime_provenance


def run(source: Path, reviewed: Path, root: Path) -> Path:
    """Keep raw inference, review edits and fresh design outputs separately indexed."""
    context = read_json(source / 'task-context.json')
    manifest, _ = verify_manifest(source / 'ingested')
    video = source / manifest['video_filename']
    review = read_json(reviewed / 'review.json')
    checks = {'raw_protocol_sha256': source / 'extracted/extracted-protocol.json',
              'raw_observations_sha256': source / 'extracted/observations.json',
              'reviewed_protocol_sha256': reviewed / 'protocol.json'}
    if any(review[key] != sha256(path) for key, path in checks.items()):
        raise ValueError('Reviewed extraction hash mismatch')
    if sha256(video) != context['video_sha256'] or sha256(video) != manifest['video_sha256']:
        raise ValueError('Source context/video mismatch')
    config = E2EConfig(machine_video=True, visual_passes=1)
    output = allocate_snapshot(root.resolve())
    document = {'schema_version': 1, 'kind': 'workbench-e2e', 'version': int(output.name[1:]),
                'status': 'running', 'created_at': time.time(), 'config': config.model_dump(mode='json'),
                'runtime': runtime_provenance(), 'stages': {}, 'physical_validation': False,
                'execution_mode': 'reviewed-extraction-live-design-continuation',
                'rerun_policy': 'reuse attributed extraction; apply separately recorded assistant review; fresh design/CAD/critique',
                'extraction_source': {'observations_sha256': sha256(checks['raw_observations_sha256']),
                                      'protocol_sha256': sha256(checks['raw_protocol_sha256'])}}
    pipeline = None
    try:
        document['source'] = copy_source(video, output / 'input')
        shutil.copy2(source / 'task-context.json', output / 'input/task-context.json')
        pipeline = PipelineRun(output, document, config)
        shutil.copy2(video, pipeline.run / 'source.mp4')
        shutil.copytree(source / 'ingested', pipeline.run / 'ingested')
        shutil.copytree(source / 'extracted', pipeline.run / 'raw-extraction')
        shutil.copytree(reviewed, pipeline.run / 'task-review')
        extracted = pipeline.run / 'extracted'
        extracted.mkdir()
        for item in (source / 'extracted').iterdir():
            if item.name in {'compiled', 'extracted-protocol.json'}:
                continue
            if item.is_dir():
                shutil.copytree(item, extracted / item.name)
            else:
                shutil.copy2(item, extracted / item.name)
        shutil.copy2(reviewed / 'protocol.json', extracted / 'extracted-protocol.json')
        compile_protocol_file(extracted / 'extracted-protocol.json', extracted / 'compiled')
        atomic_json(pipeline.run / 'job.json', {'id': pipeline.run_id, 'filename': 'HA4M human block joining — reviewed task',
                    'video_file': 'source.mp4', 'provider': 'gmi', 'vision_provider': 'nebius',
                    'model': config.text_model, 'vision_model': config.vision_model, 'frame_count': 8,
                    'stage': 'completed', 'created_at': time.time(), 'finished_at': time.time(), 'events': [],
                    'physical_validation': False, 'live_inference': True, 'reused_extraction': True,
                    'assistant_review_applied': True, 'runtime': document['runtime']})
        document['stages']['extraction'] = {'status': 'completed', 'reused': True,
                                            'review': 'task-review/review.json; assistant edits, not blind inference'}
        with native_capture() as capture:
            document['preflight'] = pipeline.stage('preflight', lambda: preflight(config, pipeline.run))
            pipeline.stage('proposal', pipeline.design)
            pipeline.stage('cad', pipeline.cad)
            pipeline.stage('scene', pipeline.scene)
            pipeline.stage('visual_review', lambda: pipeline.review(capture))
            pipeline.stage('machine_video', pipeline.machine_video)
            pipeline.stage('lab', lambda: pipeline.lab(capture))
        document['status'] = 'completed'
    except BaseException as error:
        document.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if pipeline:
            pipeline.store.executor.shutdown(wait=True)
        document.update(finished_at=time.time(), files=file_index(output))
        atomic_json(output / 'snapshot.json', document)
    return output


if __name__ == '__main__':
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--reviewed', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, default=Path('snapshots/e2e'))
    args = parser.parse_args()
    print(run(args.source, args.reviewed, args.output_root))
