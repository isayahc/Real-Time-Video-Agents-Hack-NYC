# SPDX-License-Identifier: MPL-2.0
"""Ensure capped mirror retrieval cannot silently download a whole archive."""
from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from scripts.sample_industreal import BUDGET, CHUNK, SIZE, RangeReader


class Response(io.BytesIO):
    """Minimal HTTP response with a body-read audit."""

    def __init__(self, status: int, content_range: str, body: bytes) -> None:
        """Build an isolated HTTP fixture without network access."""
        super().__init__(body)
        self.status = status
        self.headers = {'Content-Range': content_range}
        self.body_read = False

    def read(self, size: int = -1) -> bytes:
        """Record whether a potentially oversized body was touched."""
        self.body_read = True
        return super().read(size)


@pytest.mark.parametrize('status,header', [(200, ''), (206, f'bytes 1-4/{SIZE}'),
                                          (206, 'bytes 0-3/999')])
def test_refuses_body_before_reading(status: int, header: str) -> None:
    """A missing/incorrect range must fail before any full-response body read."""
    response = Response(status, header, b'data')
    with patch('scripts.sample_industreal.urlopen', return_value=response):
        with pytest.raises(ValueError, match='Refusing'):
            RangeReader().read(4)
    assert not response.body_read


def test_exact_range_and_budget() -> None:
    """Correct ranges advance position; unbounded reads fail before networking."""
    reader = RangeReader()
    reader.seek(-4, 2)
    response = Response(206, f'bytes {SIZE-4}-{SIZE-1}/{SIZE}', b'data')
    with patch('scripts.sample_industreal.urlopen', return_value=response) as request:
        assert reader.read() == b'data'
        assert reader.tell() == SIZE
        assert reader.downloaded == 4
        assert reader.read(1) == b''
        assert request.call_count == 1
    reader.seek(0)
    with patch('scripts.sample_industreal.urlopen') as request:
        with pytest.raises(ValueError, match='budget'):
            reader.read(CHUNK + 1)
        reader.downloaded = BUDGET
        with pytest.raises(ValueError, match='budget'):
            reader.read(1)
        request.assert_not_called()


def test_short_response_cannot_advance_cursor() -> None:
    """Truncated HTTP bodies cannot be accepted as successful source evidence."""
    reader = RangeReader()
    with patch('scripts.sample_industreal.urlopen', return_value=Response(206, f'bytes 0-3/{SIZE}', b'bad')):
        with pytest.raises(ValueError, match='length mismatch'):
            reader.read(4)
    assert reader.tell() == 0
