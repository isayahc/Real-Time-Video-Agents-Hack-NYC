# SPDX-License-Identifier: MPL-2.0
"""Summarize HA4M annotation intervals without inventing acceptance or labor."""
from __future__ import annotations

from collections import Counter
from statistics import mean, median

ACTIONS = {
    0: "Don't care / transition", 1: 'Pick up/place carrier',
    2: 'Pick up/place gear bearing', 3: 'Pick up/place planet gear',
    4: 'Pick up/place carrier shaft', 5: 'Pick up/place sun shaft',
    6: 'Pick up/place sun gear', 7: 'Pick up/place sun gear bearing',
    8: 'Pick up/place ring bear', 9: 'Place block 2 on block 1',
    10: 'Pick up/place cover', 11: 'Pick up/place screw',
    12: 'Pick up Allen key, turn screws, return key and EGT',
}


def summarize_recording(labels: str, frames: list[dict]) -> dict:
    """Validate complete label/index alignment and retain nominal vs device timing.

    Nominal durations count labeled frames at the publisher's 30 FPS. Device
    durations use the next segment's timestamp, with no invented terminal sample.
    Neither quantity is full-process attended labor or product quality evidence.
    """
    rows = []
    for line in labels.splitlines():
        values = line.split()
        if len(values) != 3:
            raise ValueError('Expected frame, action and repetition columns')
        frame, action, repetition = map(int, values)
        maximum = 2 if action in (2, 3) else 1 if action == 11 else 0
        if frame != len(rows) or action not in ACTIONS or not 0 <= repetition <= maximum:
            raise ValueError('Invalid frame sequence, action or repetition')
        rows.append((frame, action, repetition))
    if not rows or len(rows) != len(frames):
        raise ValueError('Labels and RGB index must cover the same nonempty sequence')
    if [item['frame_id'] for item in frames] != list(range(len(rows))):
        raise ValueError('RGB frame IDs must be contiguous and aligned with labels')
    times = [item['timestamp_us'] for item in frames]
    if any(t < 0 for t in times) or any(b < a for a, b in zip(times, times[1:])):
        raise ValueError('Device timestamps must be nonnegative and nondecreasing')
    segments = []
    start = 0
    for end in range(1, len(rows) + 1):
        if end < len(rows) and rows[end][1:] == rows[start][1:]:
            continue
        action, repetition = rows[start][1:]
        segments.append({'action_id': action, 'description': ACTIONS[action],
                         'repetition': repetition, 'start_frame': start,
                         'end_frame_exclusive': end, 'frame_count': end - start,
                         'nominal_duration_s': (end - start) / 30,
                         'device_duration_s': (times[end] - times[start]) / 1e6 if end < len(rows) else None})
        start = end
    counts = Counter((item['action_id'], item['repetition']) for item in segments if item['action_id'])
    expected = {(a, r) for a in range(1, 13) for r in range(3 if a in (2, 3) else 2 if a == 11 else 1)}
    return {'frame_count': len(rows), 'nominal_fps': 30,
            'nominal_recording_s': len(rows) / 30,
            'device_first_to_last_s': (times[-1] - times[0]) / 1e6,
            'duplicate_timestamp_intervals': sum(a == b for a, b in zip(times, times[1:])),
            'large_timestamp_gaps': sum(b - a > 50000 for a, b in zip(times, times[1:])),
            'label_rgb_index_alignment': True, 'visual_label_accuracy_verified': False,
            'missing_action_repetitions': sorted(expected - counts.keys()),
            'fragmented_action_repetitions': [list(key) for key, count in counts.items() if count > 1],
            'segments': segments, 'accepted_count': None, 'labor_s': None}


def summarize_sample(recordings: list[dict]) -> dict:
    """Rank observed time allocations, preserving whole-recording zero contributions."""
    if len(recordings) != 10 or len({row['recording_id'] for row in recordings}) != 10:
        raise ValueError('Expected exactly ten distinct recording summaries')
    actions = []
    total = sum(row['nominal_recording_s'] for row in recordings)
    for action, description in ACTIONS.items():
        per_recording = [sum(segment['nominal_duration_s'] for segment in row['segments']
                             if segment['action_id'] == action) for row in recordings]
        actions.append({'action_id': action, 'description': description,
                        'total_nominal_s': sum(per_recording),
                        'mean_nominal_s_per_recording': mean(per_recording),
                        'median_nominal_s_per_recording': median(per_recording),
                        'share_of_recorded_frames': sum(per_recording) / total})
    return {'dataset': 'HA4M', 'evidence_kind': 'publisher_annotations_offline_analysis',
            'recording_count': 10, 'total_nominal_recording_s': total,
            'mean_nominal_recording_s': total / 10,
            'actions_by_total_time': sorted(actions, key=lambda item: -item['total_nominal_s']),
            'recordings': recordings, 'accepted_count': None, 'physical_improvement_verified': False,
            'limitations': ['Convenience sample: first trial of participants 001 through 010; not held-out.',
                'Durations use label frame counts / publisher nominal 30 FPS; device timing retained separately.',
                'Action 0 includes transitions/unexpected events and is retained in the denominator.',
                'All action repetitions present does not establish accepted output or defect rate.',
                'No full-workflow labor, energy, costs, or intervention performance measured.',
                'Sparse RGB previews do not establish continuous tracking or independently validate every label.']}
