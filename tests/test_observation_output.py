# SPDX-License-Identifier: MPL-2.0
"""Reproduce observed vision-output failures using synthetic HTTP, never inference."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from typing import Any

import pytest

from protocol_pipeline.extraction import GMIProvider, NebiusProvider, extract_protocol, observation_instruction
from protocol_pipeline.models import Action, Frame, StateChange, VisualObject
from protocol_pipeline.pipeline import StructuredResponseError

VISION = 'nvidia/Nemotron-3.5-Super-VL'
TEXT = 'openai/gpt-6-astra'


@pytest.fixture
def evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, list[Frame], dict]:
    """Isolate video decoding while keeping real HTTP/schema/graph/compiler handling."""
    run = tmp_path / 'ingested'
    (run / 'frames').mkdir(parents=True)
    frames = [Frame(id=f'frame_{i:04d}', path=f'frames/{i}.jpg', timestamp_s=i * .2,
                    source_pts_s=i * .2, source_frame_index=i, sha256='0' * 64) for i in range(2)]
    monkeypatch.setenv('NEBIUS_API_KEY', 'SYNTHETIC_SECRET')
    monkeypatch.setenv('GMI_API_KEY', 'SYNTHETIC_SECRET')
    monkeypatch.setattr('protocol_pipeline.extraction.verify_manifest', lambda _: ({'frames': []}, frames))
    monkeypatch.setattr('protocol_pipeline.extraction.vision_content', lambda *args: [
        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,synthetic'}}])
    claim = {'evidence_frame_ids': [frame.id for frame in frames], 'confidence': .5,
             'interpretation': 'Synthetic uncertain visual inference'}
    graph = {'objects': [{**claim, 'id': 'tube', 'description': 'Synthetic tube'}],
             'actions': [{**claim, 'id': 'transfer', 'action': 'Move tube', 'object_ids': ['tube'],
                          'start_s': 0, 'end_s': .2}],
             'state_changes': [{**claim, 'id': 'moved', 'object_id': 'tube', 'before': 'At source',
                                'after': 'At destination', 'action_ids': ['transfer']}],
             'limitations': ['Synthetic fixture; not dataset ground truth']}
    return run, frames, graph


def envelope(text: str, model: str = VISION) -> BytesIO:
    """Return a synthetic provider completion with an explicit served model."""
    return BytesIO(json.dumps({'model': model, 'usage': {'total_tokens': 12}, 'choices': [
        {'finish_reason': 'stop', 'message': {'content': text}}]}).encode())


def test_prompt_lists_required_fields_and_actual_timeline(evidence: tuple) -> None:
    """Inherited required fields and exact timestamps must be present in the request."""
    _, frames, _ = evidence
    prompt = observation_instruction(frames)
    for contract in (VisualObject, Action, StateChange):
        for name, field in contract.model_fields.items():
            if field.is_required():
                assert json.dumps(name) in prompt
    assert '"interpretation": "' in prompt
    assert '"timestamp_s": 0.2' in prompt
    assert 'frame_0001' in prompt and 'frame_0002' not in prompt


def test_missing_fields_then_unquoted_correction_stop_before_gmi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, evidence: tuple,
) -> None:
    """Reproduce the two live failure classes without repairing or accepting either."""
    run, _, graph = evidence
    missing = deepcopy(graph)
    del missing['objects'][0]['interpretation']
    del missing['state_changes'][0]['interpretation']
    malformed = json.dumps(graph).replace('"Synthetic uncertain visual inference"', 'Unquoted interpretation')
    payloads = [json.dumps(missing), malformed]
    calls = []

    def send(request: Any, **kwargs: Any) -> BytesIO:
        """Only the two authorized observation attempts may reach transport."""
        assert 'tokenfactory.nebius.com' in request.full_url
        body = json.loads(request.data)
        assert body['model'] == VISION
        calls.append(body)
        assert len(calls) <= 2
        return envelope(payloads[len(calls) - 1])

    monkeypatch.setattr('protocol_pipeline.pipeline.urlopen', send)
    out = tmp_path / 'failed'
    with pytest.raises(StructuredResponseError):
        extract_protocol(GMIProvider(), TEXT, out, run=run, vision_model=VISION,
                         vision_provider=NebiusProvider())
    assert len(calls) == 2
    assert any(part['type'] == 'image_url' for part in calls[1]['messages'][1]['content'])
    for index, raw in enumerate(payloads, 1):
        candidate = json.loads((out / f'observation-candidate-{index}.json').read_text())
        assert candidate['raw_response'] == raw
        assert candidate['trace']['requested_model'] == VISION
        assert candidate['trace']['validation_errors']
    failure = json.loads((out / 'extraction-failure.json').read_text())
    assert failure['provider'] == 'nebius'
    assert failure['orchestrator_provider'] == 'gmi'
    assert failure['failed_stage'] == 'correcting_observations'
    assert failure['requested_model'] == VISION
    assert len(failure['completed_stage_traces']) == 2
    assert 'SYNTHETIC_SECRET' not in json.dumps(failure)
    assert not (out / 'observations.json').exists()
    assert not (out / 'compiled').exists()


@pytest.mark.parametrize('correction', ['valid', 'invented_frame'])
def test_corrected_graph_must_pass_grounding_before_downstream_compilation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, evidence: tuple, correction: str,
) -> None:
    """A valid correction compiles; schema-valid fabricated evidence is rejected."""
    run, _, graph = evidence
    corrected = deepcopy(graph)
    if correction == 'invented_frame':
        corrected['objects'][0]['evidence_frame_ids'] = ['frame_9999']
    calls = []
    root = Path(__file__).resolve().parents[1]
    spec = json.loads((root / 'examples/extraction/recorded-response.json').read_text())['responses'][0]['response']
    operation = spec['operations'][3]
    operation.update(object_ids=['tube'], source_refs=['action:transfer'])
    spec['operations'] = [operation]
    spec['links'] = []
    capability = spec['capabilities'][3]
    capability['operation_ids'] = [operation['id']]
    spec['capabilities'] = [capability]
    criterion = spec['acceptance_criteria'][1]
    criterion.update(operation_ids=[operation['id']], source_refs=['hypothesis:handling requires inspection'])
    spec['acceptance_criteria'] = [criterion]

    def send(request: Any, **kwargs: Any) -> BytesIO:
        """The GMI request is reachable only after validated Nebius evidence."""
        body = json.loads(request.data)
        calls.append(body)
        if len(calls) <= 2:
            assert body['model'] == VISION
            return envelope('{"objects": invalid}' if len(calls) == 1 else json.dumps(corrected))
        assert body['model'] == TEXT and 'api.gmi-serving.com' in request.full_url
        assert json.loads(body['messages'][1]['content'][0]['text']) == graph
        return envelope(json.dumps(spec), TEXT)

    monkeypatch.setattr('protocol_pipeline.pipeline.urlopen', send)
    out = tmp_path / correction
    if correction == 'invented_frame':
        with pytest.raises(ValueError, match='nonexistent evidence frame'):
            extract_protocol(GMIProvider(), TEXT, out, run=run, vision_model=VISION,
                             vision_provider=NebiusProvider())
        assert len(calls) == 2 and not (out / 'compiled').exists()
        assert json.loads((out / 'extraction-failure.json').read_text())['provider'] == 'nebius'
    else:
        extract_protocol(GMIProvider(), TEXT, out, run=run, vision_model=VISION,
                         vision_provider=NebiusProvider())
        assert len(calls) == 3
        assert (out / 'compiled/report.md').exists()
