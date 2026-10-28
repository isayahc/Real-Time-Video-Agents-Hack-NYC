# SPDX-License-Identifier: MPL-2.0
"""V2 API contracts with synthetic responses; never paid provider calls."""
from __future__ import annotations

import base64
from io import BytesIO, StringIO
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError

import pytest

from protocol_pipeline import opencode_v2 as api
from protocol_pipeline.opencode_machine import OpenCodeMachineSession
from protocol_pipeline.opencad_program import CadProgram
from test_opencad_program import program_data


def turn(message_id: str, *, model: str = 'openai/gpt-6-astra', finish: str = 'stop') -> list[dict]:
    """Construct the native V2 user/assistant/idle timeline, not a V1 envelope."""
    return [{'id': message_id, 'type': 'user', 'text': 'fixture'},
            {'id': 'msg_answer', 'type': 'assistant', 'time': {'created': 1, 'completed': 2},
             'model': {'providerID': 'gmi', 'id': model}, 'finish': finish,
             'tokens': {'output': 10},
             'content': [{'type': 'text', 'text': json.dumps(program_data())}]},
            {'id': 'msg_idle', 'type': 'idle', 'outcome': 'succeeded'}]


def test_transport_auth_and_redacted_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply Basic auth and avoid echoing an error body containing credentials."""
    monkeypatch.setitem(api._passwords, 'http://fixture', 'private-password')

    def send(request: Any, **kwargs: Any) -> BytesIO:
        """Check wire authentication without making a connection."""
        token = request.headers['Authorization'].split()[1]
        assert base64.b64decode(token) == b'opencode:private-password'
        raise HTTPError(request.full_url, 401, 'Unauthorized', {}, BytesIO(b'private-password'))

    monkeypatch.setattr(api, 'urlopen', send)
    with pytest.raises(RuntimeError, match='HTTP 401') as caught:
        api.request('http://fixture', 'GET', '/api/info')
    assert 'private-password' not in str(caught.value)


def test_owned_server_uses_ephemeral_port_and_redacts_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Start an owned V2 server without using or restarting the shared service."""
    monkeypatch.setattr(api, '_managed_url', None)
    stopped: list[bool] = []
    cleanup: list[Any] = []

    def spawn(args: list[str], **kwargs: Any) -> SimpleNamespace:
        """Simulate native server startup and its credential-bearing output."""
        assert args[-2:] == ['--port', '0']
        password = kwargs['env']['OPENCODE_PASSWORD']
        assert kwargs['env']['OPENCODE_CONFIG'] == str(tmp_path / 'opencode.json')
        return SimpleNamespace(pid=123, stdout=StringIO(f'server listening on http://127.0.0.1:12345\nserver password {password}\n'),
                               poll=lambda: None, terminate=lambda: stopped.append(True), wait=lambda timeout: None)

    monkeypatch.delenv('OPENCODE_CONFIG', raising=False)
    monkeypatch.setattr(api.subprocess, 'Popen', spawn)
    def kill(args: list[str], **kwargs: Any) -> None:
        """Verify Windows cleanup targets only the owned launcher process tree."""
        assert args == ['taskkill', '/PID', '123', '/T', '/F']
        stopped.append(True)

    monkeypatch.setattr(api.subprocess, 'run', kill)
    monkeypatch.setattr(api.atexit, 'register', cleanup.append)
    monkeypatch.setattr(api, 'request', lambda *args: {'version': '2.1.4'})
    # Run the output reader synchronously to make log assertions deterministic.
    monkeypatch.setattr(api.threading, 'Thread', lambda target, **kwargs: SimpleNamespace(start=target))
    assert api.ensure_server('opencode.exe', tmp_path, None) == 'http://127.0.0.1:12345'
    log = (tmp_path / 'runs/opencode-v2.log').read_text()
    assert '[REDACTED]' in log
    assert api._passwords['http://127.0.0.1:12345'] not in log
    cleanup[0]()
    assert stopped == [True]


def test_model_check_preserves_exact_routing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A different or disabled model never satisfies preflight."""
    monkeypatch.setattr(api, 'request', lambda *args: {'data': [
        {'providerID': 'gmi', 'id': 'openai/gpt-6-astra', 'enabled': True}]})
    api.check_model('http://fixture', tmp_path, 'gmi', 'openai/gpt-6-astra')
    with pytest.raises(ValueError, match='no fallback'):
        api.check_model('http://fixture', tmp_path, 'gmi', 'other-model')


def test_explicit_server_failure_does_not_spawn_or_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Respect explicit endpoints and surface authentication errors immediately."""
    monkeypatch.setenv('OPENCODE_PASSWORD', 'private-password')

    def fail(*args: Any, **kwargs: Any) -> None:
        """Simulate a rejected explicit server connection."""
        raise RuntimeError('OpenCode V2 HTTP 401')

    monkeypatch.setattr(api, 'request', fail)
    monkeypatch.setattr(api.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('Unexpected server spawn'))
    with pytest.raises(RuntimeError, match='401'):
        api.ensure_server('opencode.exe', tmp_path, 'http://explicit')


@pytest.mark.parametrize('change', ['model', 'permissions'])
def test_saved_session_changes_block_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    """Prevent a saved session from silently changing routing or enabling tools."""
    monkeypatch.setattr('protocol_pipeline.opencode_machine.ensure_server', lambda: 'http://fixture')
    monkeypatch.setitem(api._passwords, 'http://fixture', 'test-only')
    saved = {'model': {'providerID': 'gmi', 'id': 'openai/gpt-6-astra'},
             'permissions': [{'action': '*', 'resource': '*', 'effect': 'deny'}]}
    saved[change] = {} if change == 'model' else []
    monkeypatch.setattr(api, 'request', lambda *args: {'data': saved})
    with pytest.raises(RuntimeError, match='refusing to resume'):
        OpenCodeMachineSession(tmp_path, 'openai/gpt-6-astra', {'name': 'fixture'}, provider='gmi',
                               resume={'api_version': 2, 'url': 'http://old-port', 'model': 'openai/gpt-6-astra',
                                       'provider': 'gmi', 'session_id': 'ses_fixture', 'directory': str(tmp_path)})


def test_message_pagination_and_turn_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Old replies cannot satisfy a new request; later pages retain the new turn."""
    pages = iter([{'data': turn('msg_old'), 'cursor': {'next': 'page-two'}},
                  {'data': turn('msg_new'), 'cursor': {}}])
    monkeypatch.setattr(api, 'request', lambda *args: next(pages))
    rows = api.messages('http://fixture', 'ses_fixture')
    assert api.completed_response(rows, 'msg_new')['model']['id'] == 'openai/gpt-6-astra'
    assert api.completed_response(rows, 'msg_missing') is None


@pytest.mark.parametrize('finish', ['length', 'error', 'tool-calls'])
def test_incomplete_turn_rejected(finish: str) -> None:
    """A terminal marker cannot turn truncated or failed output into success."""
    with pytest.raises(RuntimeError, match='incomplete'):
        api.completed_response(turn('msg_fixture', finish=finish), 'msg_fixture')


@pytest.mark.parametrize('outcome', ['failed', 'interrupted'])
def test_failed_turn_without_assistant_is_terminal(outcome: str) -> None:
    """Provider failure before an assistant message must not poll forever."""
    rows = [{'type': 'user', 'id': 'msg_fixture'},
            {'type': 'idle', 'outcome': outcome, 'error': {'message': 'fixture failure'}}]
    with pytest.raises(RuntimeError, match='fixture failure'):
        api.completed_response(rows, 'msg_fixture')


def test_v2_session_model_permissions_poll_recovery_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the real adapter through V2 creation/admission/polling without inference."""
    monkeypatch.setattr('protocol_pipeline.opencode_machine.ensure_server', lambda: 'http://fixture')
    monkeypatch.setitem(api._passwords, 'http://fixture', 'test-only')
    monkeypatch.setattr('protocol_pipeline.opencode_machine.time.sleep', lambda _: None)
    calls: list[tuple] = []
    message_id = ''

    def send(url: str, method: str, path: str, body: Any = None) -> dict:
        """Capture exact native V2 request contracts."""
        nonlocal message_id
        calls.append((method, path, body))
        if path == '/api/session':
            assert body['model'] == {'providerID': 'gmi', 'id': 'openai/gpt-6-astra'}
            assert body['permissions'] == [{'action': '*', 'resource': '*', 'effect': 'deny'}]
            assert body['location']['directory'] == str(tmp_path.resolve())
            return {'data': {'id': 'ses_fixture'}}
        assert path.endswith('/prompt')
        assert set(body) == {'id', 'text'}
        message_id = body['id']
        return {'data': {'id': message_id}}

    count = 0

    def messages(*args: Any) -> list[dict]:
        """Simulate one lost status read, then completion of the original input."""
        nonlocal count
        count += 1
        if count == 1:
            raise TimeoutError('read timed out')
        return turn(message_id)

    monkeypatch.setattr(api, 'request', send)
    monkeypatch.setattr(api, 'messages', messages)
    session = OpenCodeMachineSession(tmp_path, 'openai/gpt-6-astra', {'name': 'fixture'}, provider='gmi')
    result, trace = session.complete(CadProgram, 'Author CAD', [])
    assert len(result.components) == 2
    assert trace['api_version'] == 2 and trace['served_model'] == 'openai/gpt-6-astra'
    assert trace['usage'] == {'output': 10}
    assert len([call for call in calls if call[1].endswith('/prompt')]) == 1
    # Reconciliation reads the retained reply, never starts another paid request.
    session.complete(CadProgram, 'Author CAD', [])
    assert len(calls) == 2
    record = json.loads(next(tmp_path.glob('opencode-request-*.json')).read_text())
    assert record['state'] == 'completed'
    assert record['message_id'] == message_id
