# SPDX-License-Identifier: MPL-2.0
"""Rebuild the ten-trial recorded baseline offline from checksum-verified sources."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_pipeline.assembly_baseline import summarize_recording, summarize_sample
from protocol_pipeline.evaluation import ProcessEvaluationInput, evaluate_process
from scripts.sample_ha4m import FRAME_PATTERN, RECORDINGS, digest, entries


def evaluate(input_dir: Path, output: Path) -> dict:
    """Verify sources, reconstruct intervals, and preserve existing acceptance gates."""
    manifest_bytes = (input_dir / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    if [row['recording_id'] for row in manifest['recordings']] != list(RECORDINGS):
        raise ValueError('Expected the fixed ten distinct participant trials')
    recordings, evaluations = [], []
    for row in manifest['recordings']:
        folder = input_dir / row['recording_id']
        labels, listing = (folder / 'Labels.txt').read_bytes(), (folder / 'rgb-listing.xml').read_bytes()
        if digest(labels) != row['labels_sha256'] or digest(listing) != row['rgb_listing_sha256']:
            raise ValueError('Source checksum mismatch')
        frames = []
        for item in entries(listing):
            match = FRAME_PATTERN.fullmatch(item['href'].rsplit('/', 1)[-1])
            if match:
                frames.append({'frame_id': int(match[1]), 'timestamp_us': int(match[2])})
        result = summarize_recording(labels.decode('utf-8-sig'), sorted(frames, key=lambda f: f['frame_id']))
        result.update(recording_id=row['recording_id'], labels_sha256=digest(labels), rgb_listing_sha256=digest(listing))
        recordings.append(result)
        process = ProcessEvaluationInput.model_validate({
            'configuration_id': 'ha4m-' + row['recording_id'],
            'functional_unit': 'One accepted EGT; acceptance specification and accepted count unresolved',
            'boundary': 'Recorded RGB first-to-last device timestamp only; excludes unrecorded setup/cleanup',
            'inputs': {'elapsed_s': {'value': result['device_first_to_last_s'], 'unit': 's', 'basis': 'measured',
                'source': f'Publisher RGB timestamp filenames; listing SHA256 {digest(listing)}'}}})
        evaluations.append(evaluate_process(process).model_dump())
    baseline = summarize_sample(recordings)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in [('baseline.json', baseline), ('resource-evaluations.json', evaluations)]:
        (output / name).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    lines = ['# HA4M recorded baseline (offline)', '',
        f"Ten trials; {sum(r['frame_count'] for r in recordings):,} labeled frames; "
        f"{baseline['total_nominal_recording_s']:.2f} nominal seconds.", '',
        '| Action | Mean nominal seconds/trial | Share of recorded frames |', '| --- | ---: | ---: |']
    lines.extend(f"| {r['description']} | {r['mean_nominal_s_per_recording']:.2f} | {r['share_of_recorded_frames']:.2%} |"
                 for r in baseline['actions_by_total_time'])
    lines += ['', '## Evidence boundaries', ''] + ['- ' + text for text in baseline['limitations']]
    lines += ['', 'Existing resource evaluations retain unknown accepted-output metrics and costs.',
              'Largest time allocation is a candidate for investigation, not proof that a fixture will reduce it.']
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (output / 'manifest.json').write_text(json.dumps({'kind': 'offline-ha4m-baseline-audit',
        'source_manifest_sha256': digest(manifest_bytes), 'new_inference_calls': 0,
        'files': {p.name: digest(p.read_bytes()) for p in sorted(output.iterdir())}}, indent=2) + '\n', encoding='utf-8')
    return baseline


def main() -> None:
    """Analyze retained source annotations without requesting network or inference."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = evaluate(args.input, args.output)
    print(json.dumps({'recordings': result['recording_count'], 'nominal_seconds': result['total_nominal_recording_s']}))


if __name__ == '__main__':
    main()
