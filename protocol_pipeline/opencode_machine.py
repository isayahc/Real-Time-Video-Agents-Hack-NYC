# SPDX-License-Identifier: MPL-2.0
"""Persistent OpenCode CAD-program authoring with inspectable native build feedback."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import hashlib
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from . import opencode_v2


def server_url() -> str:
    return (os.getenv('MACHINE_OPENCODE_URL') or os.getenv('OPENCODE_URL') or 'http://127.0.0.1:4097').rstrip('/')


def server_available() -> bool:
    try:
        with urlopen(server_url() + '/global/health', timeout=2) as response:
            return bool(json.load(response).get('healthy'))
    except (OSError, ValueError):
        return False


def ensure_server() -> str:
    """Select the installed API version and start a compatible authenticated server."""
    executable = shutil.which('opencode')
    if executable:
        version = subprocess.run(opencode_v2.command(executable, '--version'), capture_output=True,
                                 text=True, timeout=10, check=True).stdout.strip()
        if version.removeprefix('opencode ').lstrip('v').startswith('2.'):
            return opencode_v2.ensure_server(executable, Path(__file__).resolve().parents[1],
                                            os.getenv('MACHINE_OPENCODE_URL') or os.getenv('OPENCODE_URL'))
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
        environment = dict(os.environ)
        environment.setdefault('OPENCODE_CONFIG', str(root / 'opencode.json'))
        process = subprocess.Popen(args, cwd=root, stdout=log, stderr=subprocess.STDOUT,
            env=environment,
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
        self.v2 = opencode_v2.is_v2(self.url)
        self.provider = provider or os.getenv('OPENCODE_PROVIDER', 'nebius')
        if resume is None and (output/'opencode-session.json').is_file():
            resume=json.loads((output/'opencode-session.json').read_text(encoding='utf-8'))
        can_resume=bool(resume and (resume.get('url')==self.url or
                       (self.v2 and resume.get('api_version') == 2)) and
                       resume.get('model')==model and resume.get('provider')==self.provider)
        self.directory=resume.get('directory',str(output.resolve())) if can_resume else str(output.resolve())
        if self.v2:
            self.tools = {}
            if can_resume:
                self.session_id = resume['session_id']
                saved = opencode_v2.request(self.url, 'GET', f'/api/session/{self.session_id}')['data']
                if (saved.get('model', {}).get('providerID') != self.provider
                        or saved.get('model', {}).get('id') != self.model
                        or saved.get('permissions') != [{'action': '*', 'resource': '*', 'effect': 'deny'}]):
                    raise RuntimeError('OpenCode V2 saved session model or tool permissions changed; refusing to resume')
            else:
                self.session_id = opencode_v2.request(self.url, 'POST', '/api/session', {
                    'title': f"Machine CAD: {equipment['name']}",
                    'location': {'directory': self.directory},
                    'model': {'providerID': self.provider, 'id': self.model},
                    'permissions': [{'action': '*', 'resource': '*', 'effect': 'deny'}],
                })['data']['id']
        else:
            tools=self.request('GET','/experimental/tool/ids')
            self.tools={name:False for name in tools} if isinstance(tools,list) else {}
            self.session_id = resume['session_id'] if can_resume else self.request('POST', '/session', {'title':f"Machine CAD: {equipment['name']}"})['id']
        self.count = 0
        (output / 'opencode-session.json').write_text(json.dumps({
            'url':self.url,'session_id':self.session_id,'provider':self.provider,'model':model,'directory':self.directory,
            'api_version': 2 if self.v2 else 1,
        },indent=2),encoding='utf-8')

    def request(self, method: str, path: str, body=None):
        query = urlencode({'directory':self.directory})
        request = Request(self.url + path + '?' + query, method=method,
                          headers={'Content-Type':'application/json'},
                          data=None if body is None else json.dumps(body).encode())
        try:
            with urlopen(request, timeout=30) as response:
                raw=response.read()
                return json.loads(raw) if raw else None
        except HTTPError as error:
            raise RuntimeError(f'OpenCode HTTP {error.code} for session {getattr(self,"session_id","new")}: {error.read().decode("utf-8",errors="replace")}') from None
        except URLError as error:
            raise RuntimeError(f'OpenCode request failed: {error.reason}') from None

    def complete(self, contract, instruction: str, content: list[dict]):
        if self.v2:
            return self.complete_v2(contract, instruction, content)
        prompt = instruction + '\n\n' + '\n'.join(item['text'] for item in content)
        # Nebius rejected OpenCode's tool-based structured-output request in the live check.
        # JSON carries complete Python source, not a geometry vocabulary. The CAD worker
        # executes it through Forma/OpenCAD and returns actual errors to this session.
        self.count += 1
        prompt += '\nReturn only valid JSON matching this schema, without markdown: ' + json.dumps(contract.model_json_schema())
        body = {'model':{'providerID':self.provider,'modelID':self.model},
                'parts':[{'type':'text','text':prompt}], 'tools':self.tools}
        started = time.monotonic()
        digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
        request_path=self.output/f'opencode-request-{digest[:16]}.json'
        pending=json.loads(request_path.read_text(encoding='utf-8')) if request_path.is_file() else None
        if pending is None:
            pending={'message_id':'msg_'+uuid.uuid4().hex,'session_id':self.session_id,'state':'submitting',
                     'submitted_at':time.time(),'deadline':time.time()+float(os.getenv('MACHINE_AUTHORING_TIMEOUT_SECONDS','900'))}
            request_path.write_text(json.dumps(pending,indent=2),encoding='utf-8')
            body['messageID']=pending['message_id']
            self.request('POST', f'/session/{self.session_id}/prompt_async', body)
            pending['state']='running';request_path.write_text(json.dumps(pending,indent=2),encoding='utf-8')
        # An HTTP request is only a status read; its lifetime does not own the job.
        while True:
            try:
                messages=self.request('GET',f'/session/{self.session_id}/message')
            except (RuntimeError,TimeoutError) as error:
                messages=[];pending['last_poll_error']=str(error)
            response=next((row for row in reversed(messages or [])
                if row.get('info',{}).get('role')=='assistant'
                and row['info'].get('parentID')==pending['message_id']
                and (row['info'].get('time',{}).get('completed') or row['info'].get('error'))),None)
            if response is not None:
                pending['state']='completed';pending['completed_at']=time.time()
                request_path.write_text(json.dumps(pending,indent=2),encoding='utf-8')
                break
            if time.time()>=pending['deadline']:
                pending['state']='awaiting_reconciliation'
                request_path.write_text(json.dumps(pending,indent=2),encoding='utf-8')
                raise TimeoutError(f'OpenCode authoring deadline reached; session {self.session_id}, message {pending["message_id"]} may still be running. Request identity is retained for recovery.')
            time.sleep(2)
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
            'provenance':'OpenCode-authored OpenCAD Python; native Forma/OCCT validation and export follows'}

    def complete_v2(self, contract: type, instruction: str,
                    content: list[dict]) -> tuple[object, dict]:
        """Persist a V2 input identity and poll its turn without resubmitting paid work."""
        self.count += 1
        prompt = instruction + '\n\n' + '\n'.join(item['text'] for item in content)
        prompt += '\nReturn only valid JSON matching this schema, without markdown: ' + json.dumps(contract.model_json_schema())
        digest = hashlib.sha256(json.dumps({'prompt': prompt, 'model': self.model,
                                          'provider': self.provider, 'session': self.session_id}, sort_keys=True).encode()).hexdigest()
        path = self.output / f'opencode-request-{digest[:16]}.json'
        pending = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
        started = time.monotonic()
        if pending is None:
            pending = {'message_id': 'msg_' + uuid.uuid4().hex, 'session_id': self.session_id,
                       'state': 'submitting', 'api_version': 2, 'submitted_at': time.time(),
                       'deadline': time.time() + float(os.getenv('MACHINE_AUTHORING_TIMEOUT_SECONDS', '900'))}
            path.write_text(json.dumps(pending, indent=2), encoding='utf-8')
            opencode_v2.request(self.url, 'POST', f'/api/session/{self.session_id}/prompt',
                                {'id': pending['message_id'], 'text': prompt})
            pending['state'] = 'running'
            path.write_text(json.dumps(pending, indent=2), encoding='utf-8')
        while True:
            try:
                rows = opencode_v2.messages(self.url, self.session_id)
            except (OSError, RuntimeError) as error:
                rows = []
                pending['last_poll_error'] = str(error)
            try:
                response = opencode_v2.completed_response(rows, pending['message_id'])
            except RuntimeError as error:
                pending.update(state='failed', error=str(error))
                path.write_text(json.dumps(pending, indent=2), encoding='utf-8')
                (self.output / f'opencode-response-{self.count}.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
                raise
            if response is not None:
                break
            if time.time() >= pending['deadline']:
                pending['state'] = 'awaiting_reconciliation'
                path.write_text(json.dumps(pending, indent=2), encoding='utf-8')
                raise TimeoutError(f'OpenCode V2 authoring deadline reached; session {self.session_id}, message {pending["message_id"]} retained for recovery')
            time.sleep(2)
        pending['state'] = 'completed'
        path.write_text(json.dumps(pending, indent=2), encoding='utf-8')
        (self.output / f'opencode-response-{self.count}.json').write_text(json.dumps(response, indent=2), encoding='utf-8')
        served = response['model']
        if served.get('providerID') != self.provider or served.get('id') != self.model:
            raise RuntimeError('OpenCode V2 returned a different provider/model than requested')
        text = '\n'.join(part['text'] for part in response['content'] if part['type'] == 'text').strip()
        if text.startswith('```') and text.endswith('```'):
            text = '\n'.join(text.splitlines()[1:-1])
        parsed = contract.model_validate_json(text)
        return parsed, {'authoring': 'opencode', 'api_version': 2, 'provider': self.provider,
                        'session_id': self.session_id, 'requested_model': self.model,
                        'served_model': served['id'], 'usage': response.get('tokens'),
                        'finish_reason': response.get('finish'), 'latency_s': time.monotonic() - started,
                        'output_mode': 'json_text', 'request_count': self.count,
                        'provenance': 'OpenCode-authored OpenCAD Python; native Forma/OCCT validation and export follows'}
