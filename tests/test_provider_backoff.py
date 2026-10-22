"""Provider rate limiting preserves bounded retry behavior."""
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from protocol_pipeline.pipeline import NebiusClient, retry_delay
from protocol_pipeline.models import ObservationGraph


def test_retry_after_and_fallback():
    assert retry_delay(HTTPError('test', 429, '', {'Retry-After': '25'}, None), 0, 10) == 25
    assert retry_delay(HTTPError('test', 429, '', {'Retry-After': 'invalid'}, None), 1, 10) == 20
    assert retry_delay(HTTPError('test', 429, '', {'Retry-After': '9999'}, None), 0, 10) == 120


def test_exhausted_rate_limit_waits_and_explains(monkeypatch):
    monkeypatch.setenv('MODEL_REQUEST_ATTEMPTS', '3')
    error = HTTPError('test', 429, '', {'Retry-After': '12'}, BytesIO())
    with patch('protocol_pipeline.pipeline.urlopen', side_effect=error) as request, patch('protocol_pipeline.pipeline.time.sleep') as sleep:
        with pytest.raises(RuntimeError, match='rate limit or capacity'):
            NebiusClient('test', provider='gmi').complete('test', ObservationGraph, '', [])
    assert request.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [12, 12]
