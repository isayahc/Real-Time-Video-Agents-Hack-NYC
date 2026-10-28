# SPDX-License-Identifier: MPL-2.0
"""Authenticated V2 transport for the existing CAD workflow, without model fallback."""
from __future__ import annotations

import atexit
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid

_passwords: dict[str, str] = {}
_managed_url: str | None = None
_lock = threading.Lock()


def is_v2(url: str) -> bool:
    """Identify endpoints verified by the V2 startup handshake."""
    return url in _passwords


def request(url: str, method: str, path: str, body: Any = None) -> Any:
    """Call a V2 endpoint without leaking credentials or response bodies in errors."""
    password = _passwords.get(url, '')
    headers = {'Content-Type': 'application/json'}
    if password:
        token = base64.b64encode(f'opencode:{password}'.encode()).decode()
        headers['Authorization'] = f'Basic {token}'
    req = Request(url + path, method=method, headers=headers,
                  data=None if body is None else json.dumps(body).encode())
    try:
        with urlopen(req, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f'OpenCode V2 HTTP {error.code} for {method} {path.split("?")[0]}') from None


def command(executable: str, *args: str) -> list[str]:
    """Invoke Windows command shims while preserving direct native executables."""
    result = [executable, *args]
    if os.name == 'nt' and Path(executable).suffix.lower() in ('.cmd', '.bat'):
        result = [os.getenv('COMSPEC', 'cmd.exe'), '/c', *result]
    return result


def ensure_server(executable: str, root: Path, explicit_url: str | None) -> str:
    """Use an explicit authenticated server or an owned ephemeral loopback server.

    The private server inherits project credentials/configuration. It never restarts
    the user's shared service. Its random password stays in process memory.
    """
    global _managed_url
    with _lock:
        if explicit_url:
            url = explicit_url.rstrip('/')
            _passwords[url] = os.getenv('OPENCODE_PASSWORD') or os.getenv('OPENCODE_SERVER_PASSWORD', '')
            info = request(url, 'GET', '/api/info')
            if not str(info.get('version', '')).startswith('2.'):
                raise RuntimeError('Configured OpenCode server is not V2')
            return url
        if _managed_url:
            request(_managed_url, 'GET', '/api/info')
            return _managed_url
        password = uuid.uuid4().hex
        environment = dict(os.environ)
        environment['OPENCODE_PASSWORD'] = password
        environment.setdefault('OPENCODE_CONFIG', str(root / 'opencode.json'))
        process = subprocess.Popen(command(executable, 'serve', '--hostname', '127.0.0.1', '--port', '0'),
                                   cwd=root, env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')

        def stop() -> None:
            """Stop only this invocation's owned server, never a shared service."""
            if process.poll() is None:
                if os.name == 'nt':
                    # npm's .cmd launcher owns a child process tree; terminating
                    # only cmd.exe leaves its authenticated server orphaned.
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   capture_output=True, timeout=10, check=False)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

        atexit.register(stop)
        ready = threading.Event()
        addresses: list[str] = []
        logs = root / 'runs'
        logs.mkdir(exist_ok=True)

        def read_output() -> None:
            """Discover the allocated port and redact the generated server password."""
            assert process.stdout is not None
            with (logs / 'opencode-v2.log').open('a', encoding='utf-8') as log:
                for line in process.stdout:
                    log.write(line.replace(password, '[REDACTED]'))
                    log.flush()
                    match = re.search(r'server listening on (http://127\.0\.0\.1:\d+)', line)
                    if match:
                        addresses.append(match.group(1))
                        ready.set()

        threading.Thread(target=read_output, daemon=True).start()
        deadline = time.monotonic() + 30
        while not ready.wait(.1):
            if process.poll() is not None:
                raise RuntimeError('OpenCode V2 exited before readiness; see runs/opencode-v2.log')
            if time.monotonic() >= deadline:
                stop()
                raise TimeoutError('OpenCode V2 startup exceeded 30 seconds; see runs/opencode-v2.log')
        url = addresses[0]
        _passwords[url] = password
        try:
            info = request(url, 'GET', '/api/info')
            if not str(info.get('version', '')).startswith('2.'):
                raise RuntimeError('OpenCode did not report a V2 server')
        except Exception:
            stop()
            raise
        _managed_url = url
        return url


def check_model(url: str, directory: Path, provider: str, model: str) -> None:
    """Check the exact enabled model in the selected project without inference."""
    query = urlencode({'location[directory]': str(directory.resolve())})
    rows = request(url, 'GET', '/api/model?' + query)['data']
    if not any(row.get('providerID') == provider and row.get('id') == model
               and row.get('enabled') for row in rows):
        raise ValueError(f'OpenCode V2 does not list enabled model {provider}/{model}; no fallback was selected')


def messages(url: str, session_id: str) -> list[dict[str, Any]]:
    """Read the full ordered timeline, including responses beyond the first page."""
    path = f'/api/session/{session_id}/message'
    query = 'order=asc'
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    while True:
        page = request(url, 'GET', path + '?' + query)
        rows.extend(page['data'])
        cursor = page.get('cursor', {}).get('next')
        if not cursor:
            return rows
        if cursor in seen:
            raise RuntimeError('OpenCode V2 repeated a message pagination cursor')
        seen.add(cursor)
        query = urlencode({'cursor': cursor})


def completed_response(rows: list[dict[str, Any]], message_id: str) -> dict[str, Any] | None:
    """Match a completed turn to its submitted user ID rather than an old reply."""
    start = next((i for i, row in enumerate(rows)
                  if row.get('type') == 'user' and row.get('id') == message_id), None)
    if start is None:
        return None
    turn: list[dict[str, Any]] = []
    for row in rows[start + 1:]:
        if row.get('type') == 'user':
            raise RuntimeError('OpenCode V2 CAD session received an intervening user message')
        turn.append(row)
        if row.get('type') == 'idle':
            if row.get('outcome') != 'succeeded':
                raise RuntimeError(f'OpenCode V2 turn {row.get("outcome")}: {row.get("error", {}).get("message", "no detail")}')
            answer = next((item for item in reversed(turn) if item.get('type') == 'assistant'), None)
            if not answer or not answer.get('time', {}).get('completed'):
                raise RuntimeError('OpenCode V2 completed without an assistant result')
            if answer.get('error') or answer.get('finish') != 'stop':
                raise RuntimeError(f'OpenCode V2 incomplete assistant result: {answer.get("finish")}')
            return answer
    return None
