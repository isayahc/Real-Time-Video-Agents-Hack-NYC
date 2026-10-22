# SPDX-License-Identifier: MPL-2.0
"""Persistent OpenCode/Nebius CAD authoring with inspectable sessions and tool feedback."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def server_url() -> str:
    return (os.getenv('MACHINE_OPENCODE_URL') or os.getenv('OPENCODE_URL') or 'http://127.0.0.1:4097').rstrip('/')


def server_available() -> bool:
    try:
        with urlopen(server_url() + '/global/health', timeout=2) as response:
            return bool(json.load(response).get('healthy'))
    except (OSError, ValueError):
        return False


def ensure_server() -> str:
    url = server_url()
    if server_available():
        return url
    if url != 'http://127.0.0.1:4097':
        raise RuntimeError(f'OpenCode is not responding at {url}. Start that server or unset MACHINE_OPENCODE_URL.')
    executable = shutil.which('opencode')
    if not executable:
        raise RuntimeError('OpenCode CLI is not installed on PATH')
    root = Path(__file__).resolve().parents[1]
    logs = root / 'runs'
    logs.mkdir(exist_ok=True)
    args = [executable, 'serve', '--hostname', '127.0.0.1', '--port', '4097']
    if os.name == 'nt' and Path(executable).suffix.lower() in ('.cmd', '.bat'):
        args = [os.getenv('COMSPEC', 'cmd.exe'), '/c', *args]
    with (logs / 'opencode-machines.log').open('ab') as log:
        process = subprocess.Popen(args, cwd=root, stdout=log, stderr=subprocess.STDOUT,
            **({'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == 'nt' else {'start_new_session': True}))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if server_available():
            return url
        if process.poll() is not None:
            raise RuntimeError(f'OpenCode server exited with {process.returncode}; see runs/opencode-machines.log')
        time.sleep(.2)
    raise TimeoutError('OpenCode server startup exceeded 20 seconds; see runs/opencode-machines.log')


class OpenCodeMachineSession:
    """Keep native CAD failures and corrected candidates in the same model conversation."""
    def __init__(self, output: Path, model: str, equipment: dict, resume: dict | None=None, provider: str | None=None):
        self.output, self.model, self.equipment = output, model, equipment
        self.url = ensure_server()
        self.provider = provider or os.getenv('OPENCODE_PROVIDER', 'nebius')
        can_resume=bool(resume and resume.get('url')==self.url and resume.get('model')==model and resume.get('provider')==self.provider)
        self.directory=resume.get('directory',str(output.resolve())) if can_resume else str(output.resolve())
        tools=self.request('GET','/experimental/tool/ids')
        self.tools={name:False for name in tools} if isinstance(tools,list) else {}
        self.session_id = resume['session_id'] if can_resume else self.request('POST', '/session', {'title':f"Machine CAD: {equipment['name']}"})['id']
        self.count = 0
        (output / 'opencode-session.json').write_text(json.dumps({
            'url':self.url,'session_id':self.session_id,'provider':self.provider,'model':model,'directory':self.directory,
        },indent=2),encoding='utf-8')

    def request(self, method: str, path: str, body=None):
        query = urlencode({'directory':self.directory})
        request = Request(self.url + path + '?' + query, method=method,
                          headers={'Content-Type':'application/json'},
                          data=None if body is None else json.dumps(body).encode())
        try:
            with urlopen(request, timeout=240) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(f'OpenCode HTTP {error.code} for session {getattr(self,"session_id","new")}: {error.read().decode("utf-8",errors="replace")}') from None
        except URLError as error:
            raise RuntimeError(f'OpenCode request failed: {error.reason}') from None

    def complete(self, contract, instruction: str, content: list[dict]):
        prompt = instruction + '\n\n' + '\n'.join(item['text'] for item in content)
        # Nebius rejected OpenCode's tool-based structured-output request in the live check.
        # OpenCode owns the conversation; native tools run locally and return actual errors.
        self.count += 1
        prompt += '\nReturn only valid JSON matching this schema, without markdown: ' + json.dumps(contract.model_json_schema())
        body = {'model':{'providerID':self.provider,'modelID':self.model},
                'parts':[{'type':'text','text':prompt}], 'tools':self.tools}
        started = time.monotonic()
        response = self.request('POST', f'/session/{self.session_id}/message', body)
        (self.output / f'opencode-response-{self.count}.json').write_text(json.dumps(response,indent=2),encoding='utf-8')
        info = response.get('info', {})
        if not isinstance(info,dict):
            raise RuntimeError(f'OpenCode session {self.session_id} returned an invalid message envelope')
        if info.get('error'):
            raise RuntimeError(f'OpenCode session {self.session_id}: {json.dumps(info["error"])}')
        candidate = info.get('structured_output')
        if candidate is None:
            text = '\n'.join(part.get('text','') for part in response.get('parts',[]) if part.get('type')=='text').strip()
            if text.startswith('```') and text.endswith('```'):
                text = '\n'.join(text.splitlines()[1:-1])
            try:
                candidate = json.loads(text)
            except ValueError as error:
                raise ValueError(f'OpenCode session {self.session_id} returned malformed JSON: {error}') from None
        parsed = contract.model_validate_json(candidate) if isinstance(candidate,str) else contract.model_validate(candidate)
        return parsed, {'authoring':'opencode','provider':self.provider,'session_id':self.session_id,
            'requested_model':self.model,'served_model':info.get('modelID'),'usage':info.get('tokens'),
            'latency_s':time.monotonic()-started,'output_mode':'json_text','request_count':self.count,
            'provenance':'OpenCode model-authored CAD; native Forma validation/export follows'}
