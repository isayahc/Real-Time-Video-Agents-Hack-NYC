# SPDX-License-Identifier: MPL-2.0
"""Check bounded application validation retries and explicit provider failures."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from protocol_pipeline.compiler import ProtocolSpecification
from protocol_pipeline.extraction import OpenCodeProvider


def test_local_correction_retains_session_and_reports_actual_model() -> None:
    """Correct cross-field errors not expressible in the structured-output schema."""
    candidate = json.loads((Path(__file__).resolve().parents[1] / 'examples/extraction/recorded-response.json').read_text())['responses'][0]['response']
    invalid = copy.deepcopy(candidate)
    invalid['capabilities'] = invalid['capabilities'][:1]
    responses = [{'id': 'session'}, {'info': {'structured_output': invalid}},
                 {'info': {'structured_output': candidate, 'modelID': 'actual-model'}}, None]
    with patch.object(OpenCodeProvider, '_request', side_effect=responses) as request:
        parsed, trace = OpenCodeProvider().complete('requested', ProtocolSpecification, 'Extract', [{'type': 'text', 'text': 'source'}])
    assert parsed.operations
    assert trace['attempt_count'] == 2
    assert trace['served_model'] == 'actual-model'
    assert 'validation errors' in request.call_args_list[2].args[2]['parts'][0]['text']
    assert request.call_args_list[-1].args == ('DELETE', '/session/session')


@pytest.mark.parametrize('envelope', [{'info': {}}, {'info': {'error': {'message': 'private'}}}])
def test_missing_output_or_provider_error_never_becomes_success(envelope: dict) -> None:
    """Fail explicitly rather than fabricate output or leak the raw error payload."""
    with patch.object(OpenCodeProvider, '_request', side_effect=[{'id': 'session'}, envelope, None]):
        with pytest.raises((ValueError, RuntimeError)) as error:
            OpenCodeProvider().complete('requested', ProtocolSpecification, 'Extract', [])
        assert 'private' not in str(error.value)
