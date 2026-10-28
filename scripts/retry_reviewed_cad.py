# SPDX-License-Identifier: MPL-2.0
"""Append CAD recovery with verbatim reviewed constraints, retaining the raw proposal."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_pipeline.autonomy import AutonomyProposal
from protocol_pipeline.e2e import PipelineRun, native_capture
from protocol_pipeline.environment import load_environment
from protocol_pipeline.pipeline import sha256
from protocol_pipeline.snapshots import E2EConfig, allocate_snapshot, atomic_json, file_index, read_json, verify_snapshot
from protocol_pipeline.web import runtime_provenance


def retain_cad_constraints(run: Path) -> None:
    """Carry reviewed requirements verbatim instead of relying on model summarization."""
    attempt = read_json(run/'autonomy/job.json')['attempt_id']
    path = run/'autonomy'/attempt/'proposal.json'
    raw = read_json(path)
    original = path.with_name('raw-proposal-before-cad-review.json')
    if original.exists():
        raise ValueError('CAD handoff review already exists; refusing to overwrite it')
    protocol_path = run/'task-review/protocol.json'
    protocol = read_json(protocol_path)
    constraints = list(dict.fromkeys(c for op in protocol['operations'] for c in op['constraints']))
    updated = copy.deepcopy(raw)
    for i, constraint in enumerate(constraints):
        updated['proposal']['machine_requirements'].append({
            'id': f'assistant-cad-constraint-{i}', 'description': constraint,
            'source_operation_ids': [op['id'] for op in protocol['operations']],
            'source_refs': ['hypothesis:verbatim reviewed protocol constraints'],
            'verification_needed': 'Validate native CAD coordinates and separate bodies against this constraint before presentation.',
            'unknowns': ['Reviewed task/design requirement, not observed machine or physical validation.']})
    AutonomyProposal.model_validate(updated['proposal'])
    atomic_json(original, raw)
    updated['cad_handoff_review'] = {'basis': 'reviewed protocol constraints appended verbatim; includes explicitly authored design brief',
                                    'protocol_sha256': sha256(protocol_path),
                                    'raw_proposal_sha256': sha256(original)}
    atomic_json(path, updated)


def retry(source: Path, root: Path) -> Path:
    """Reuse verified extraction/design; explicitly carry constraints through CAD handoff."""
    old = verify_snapshot(source)
    old_run = source.parent / old['run_path']
    for stage in ('extraction', 'proposal'):
        if old['stages'][stage]['status'] != 'completed':
            raise ValueError(f'Cannot reuse incomplete {stage}')
    output = allocate_snapshot(root.resolve())
    document = copy.deepcopy(old)
    for key in ('files', 'error', 'error_type', 'finished_at'):
        document.pop(key, None)
    document.update(version=int(output.name[1:]), status='running', created_at=time.time(),
                    parent={'version': old['version'], 'document_sha256': sha256(source)},
                    runtime=runtime_provenance(), execution_mode='reviewed-cad-recovery',
                    rerun_policy='Reuse extraction and raw proposal; append verbatim assistant-reviewed CAD constraints; fresh CAD')
    pipeline = PipelineRun(output, document, E2EConfig.model_validate(old['config']))
    try:
        shutil.copytree(source.parent/'input', output/'input')
        shutil.copytree(old_run, pipeline.run, dirs_exist_ok=True)
        job = read_json(pipeline.run/'job.json')
        job['id'] = pipeline.run_id
        atomic_json(pipeline.run/'job.json', job)
        retain_cad_constraints(pipeline.run)
        document['stages']['extraction']['reused_from_version'] = old['version']
        document['stages']['proposal']['reused_from_version'] = old['version']
        pipeline.stage('cad', pipeline.cad)
        pipeline.stage('scene', pipeline.scene)
        with native_capture() as capture:
            pipeline.stage('lab', lambda: pipeline.lab(capture))
        document['status'] = 'completed'
        document['presentation_pending'] = 'Add verified source CAD and authored fastening motion; no live visual critique of this recovery yet.'
    except BaseException as error:
        document.update(status='failed', error=str(error), error_type=type(error).__name__)
        raise
    finally:
        pipeline.store.executor.shutdown(wait=True)
        document.update(finished_at=time.time(), files=file_index(output))
        atomic_json(output/'snapshot.json', document)
    return output


if __name__ == '__main__':
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, default=Path('snapshots/e2e'))
    args = parser.parse_args()
    print(retry(args.source, args.output_root))
