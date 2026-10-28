# SPDX-License-Identifier: MPL-2.0
"""Create a measurement template or audit a batch against existing alternatives offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protocol_pipeline.alternatives import AlternativeSet, alternative_report
from protocol_pipeline.pipeline import sha256
from protocol_pipeline.snapshots import atomic_json, file_index, read_json
from protocol_pipeline.workflow_measurements import WorkflowBatch, compare_batch, reconcile_batch


def main() -> None:
    """Retain all inputs and hashes without inference or overwriting prior evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=Path('benchmarks/coil-winding/baseline.json'))
    parser.add_argument('--alternatives', type=Path, default=Path('examples/apparatus-alternatives/evidence-input.json'))
    parser.add_argument('--option', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--template', action='store_true')
    mode.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline = read_json(args.baseline)
    alternatives = AlternativeSet.model_validate(read_json(args.alternatives))
    selected = next((option for option in alternatives.options if option.id == args.option), None)
    if selected is None:
        raise ValueError('Unknown alternative ID')
    if args.template:
        process = selected.option.process.model_dump()
        process.update(acceptance_verified=False, acceptance_source=None, attendance=None, attendance_source=None)
        # A collection template never inherits performance measurements/assumptions.
        process['inputs'] = {key: {'unit': item['unit'], 'value': None, 'basis': 'unknown', 'source': None}
                             for key, item in process['inputs'].items() if key != 'labor_s'}
        batch = WorkflowBatch.model_validate({
            'baseline_id': baseline['baseline_id'], 'baseline_sha256': sha256(args.baseline),
            'evidence_kind': 'physical', 'conditions': 'Not collected: record batch size, operator, equipment and conditions.',
            'evidence_refs': ['Collection plan only; no observation has been collected.'],
            'process': process, 'steps': [{'step_id': step['id'], 'status': 'unobserved',
                'rationale': step['verification']} for step in baseline['steps']],
        })
    else:
        batch = WorkflowBatch.model_validate(read_json(args.input))
    audit = reconcile_batch(batch, baseline, args.baseline)
    comparison = compare_batch(alternatives, args.option, audit)
    args.output.mkdir(parents=True, exist_ok=False)
    atomic_json(args.output/'batch.json', batch.model_dump())
    atomic_json(args.output/'baseline.json', baseline)
    atomic_json(args.output/'alternatives.json', alternatives.model_dump())
    atomic_json(args.output/'coverage.json', audit)
    atomic_json(args.output/'comparison.json', comparison)
    atomic_json(args.output/'updated-alternatives.json', comparison['input_snapshot'])
    (args.output/'report.md').write_text(alternative_report(comparison), encoding='utf-8')
    atomic_json(args.output/'manifest.json', {
        'kind': 'offline-workflow-measurement-audit', 'mode': 'collection_template' if args.template else 'batch_audit',
        'status': audit['status'], 'baseline_sha256': sha256(args.baseline),
        'alternatives_sha256': sha256(args.alternatives),
        'batch_source_sha256': sha256(args.input) if args.input else None,
        'physical_validation': False, 'new_inference_calls': 0, 'files': file_index(args.output),
    })
    print(json.dumps({'output': str(args.output), 'status': audit['status'], 'blockers': audit['blockers'],
                      'recommendation': comparison['overall_recommendation']}))


if __name__ == '__main__':
    main()
