# SPDX-License-Identifier: MPL-2.0
"""Offline transport regression for the live integrated-workcell proposal failure."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from typing import Any

import pytest

from protocol_pipeline.autonomy import AutonomyProposal, generate_proposal, integrate_workcell
from protocol_pipeline.compiler import ProtocolSpecification
from protocol_pipeline.extraction import GMIProvider
from protocol_pipeline.pipeline import IncompleteCompletionError, StructuredResponseError
from test_autonomy import proposal_fixture

MODEL = 'openai/gpt-6-astra'


@pytest.fixture
def candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict, dict]:
    """Create synthetic valid and malformed proposals against a real protocol contract."""
    monkeypatch.setenv('GMI_API_KEY', 'SYNTHETIC_DO_NOT_PERSIST')
    root = Path(__file__).resolve().parents[1]
    raw = json.loads((root / 'examples/extraction/recorded-response.json').read_text())['responses'][0]['response']
    protocol = ProtocolSpecification.model_validate(raw)
    source = tmp_path / 'protocol.json'
    source.write_text(protocol.model_dump_json())
    original = AutonomyProposal.model_validate(proposal_fixture(protocol))
    good = integrate_workcell(original, protocol).model_dump()
    bad = original.model_dump()
    bad['design_scope'] = 'integrated_workcell'
    component = deepcopy(bad['equipment'][0])
    component.update(id='sensor', name='Synthetic sensor', quantity=1)
    bad['equipment'].append(component)
    assert bad['machine_requirements'] == []
    return source, bad, good


def envelope(candidate: dict, finish: str = 'stop') -> BytesIO:
    """Return synthetic GMI output, not a provider request or a live evidence fixture."""
    return BytesIO(json.dumps({'model': 'gpt-6-astra-synthetic', 'usage': {'total_tokens': 10},
                              'choices': [{'finish_reason': finish,
                                           'message': {'content': json.dumps(candidate)}}]}).encode())


@pytest.mark.parametrize('outcome', ['corrected', 'repeated_invalid', 'coverage_invalid'])
def test_proposal_schema_correction_is_bounded_and_preserves_rejected_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidates: tuple, outcome: str,
) -> None:
    """Correct only through a second validated response, never relabel invalid output."""
    source, bad, good = candidates
    second = deepcopy(good) if outcome != 'repeated_invalid' else bad
    if outcome == 'coverage_invalid':
        second['machine_requirements'] = [second['machine_requirements'][0]]
    calls: list[dict] = []

    def send(request: Any, **kwargs: Any) -> BytesIO:
        """Capture both real wire payloads and return deterministic candidates."""
        assert request.full_url == 'https://api.gmi-serving.com/v1/chat/completions'
        body = json.loads(request.data)
        assert body['model'] == MODEL
        calls.append(body)
        assert len(calls) <= 2
        return envelope(bad if len(calls) == 1 else second)

    monkeypatch.setattr('protocol_pipeline.pipeline.urlopen', send)
    output = tmp_path / 'proposal'
    if outcome == 'corrected':
        result = generate_proposal(GMIProvider(), MODEL, source, output)
        assert result['proposal'] == good
        assert result['physical_validation'] is False
        assert len(result['traces']) == 2
        assert result['traces'][0]['validation_errors']
        assert result['proposal']['component_bill_of_materials'] == good['component_bill_of_materials']
        assert result['proposal']['costs'] == good['costs']
    else:
        expected = StructuredResponseError if outcome == 'repeated_invalid' else ValueError
        with pytest.raises(expected):
            generate_proposal(GMIProvider(), MODEL, source, output)
        assert not (output / 'proposal.json').exists()
        assert (output / 'failure-2.json').exists()
    assert len(calls) == 2
    initial = calls[0]['messages'][0]['content']
    assert 'exactly ONE' in initial and 'component_bill_of_materials' in initial
    correction = calls[1]['messages'][1]['content']
    assert correction[0] == calls[0]['messages'][1]['content'][0]
    assert json.dumps(bad) in correction[-1]['text']
    failure = json.loads((output / 'failure-1.json').read_text())
    assert failure['provider_trace']['response_json_text'] == json.dumps(bad)
    assert failure['provider_trace']['requested_model'] == MODEL
    for file in output.glob('*.json'):
        assert 'SYNTHETIC_DO_NOT_PERSIST' not in file.read_text()


def test_truncation_is_not_retried_as_schema_correction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidates: tuple,
) -> None:
    """Keep incomplete completions outside the schema-only correction allowance."""
    source, _, good = candidates
    calls: list[Any] = []

    def send(request: Any, **kwargs: Any) -> BytesIO:
        """Return a truncated completion even though its text happens to parse."""
        calls.append(request)
        return envelope(good, finish='length')

    monkeypatch.setattr('protocol_pipeline.pipeline.urlopen', send)
    with pytest.raises(IncompleteCompletionError):
        generate_proposal(GMIProvider(), MODEL, source, tmp_path / 'failed')
    assert len(calls) == 1
    assert not (tmp_path / 'failed/proposal.json').exists()


def test_replay_provider_never_gets_a_live_correction(
    tmp_path: Path, candidates: tuple,
) -> None:
    """Offline replay stays deterministic and cannot silently expand to another call."""
    source, bad, _ = candidates

    class Replay:
        """A malformed recorded response, explicitly offline."""
        name = 'replay'
        live = False
        calls = 0

        def complete(self, *args: Any) -> Any:
            """Raise the same validation category without network access."""
            self.calls += 1
            raise StructuredResponseError('invalid integrated workcell', {'response_json_text': json.dumps(bad)})

    provider = Replay()
    with pytest.raises(StructuredResponseError):
        generate_proposal(provider, MODEL, source, tmp_path / 'replayed')
    assert provider.calls == 1
