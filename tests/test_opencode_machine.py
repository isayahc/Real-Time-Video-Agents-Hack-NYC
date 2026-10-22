# SPDX-License-Identifier: MPL-2.0
"""Persistent OpenCode context, actual native-error feedback, and explicit runtime provenance."""
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from protocol_pipeline.machine_cad import author_machine_cad
from protocol_pipeline.opencad_program import CadProgram
from protocol_pipeline.opencode_machine import OpenCodeMachineSession
from test_opencad_program import program_data


@pytest.fixture(autouse=True)
def offline_api_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep transport/correction tests independent of a native OpenCAD installation."""
    monkeypatch.setattr('protocol_pipeline.machine_cad.cad_api_reference', lambda: 'Fixture OpenCAD API')


def test_opencode_session_accepts_schema_valid_json_text_without_fabricating_output(tmp_path):
    responses=[['bash','read','write'],{'id':'ses_test'},
               {'info':{'modelID':'served-model','tokens':{'output':10}},
                'parts':[{'type':'text','text':json.dumps(program_data())}]}]
    with patch('protocol_pipeline.opencode_machine.ensure_server',return_value='http://local'), \
         patch.object(OpenCodeMachineSession,'request',side_effect=responses) as request:
        session=OpenCodeMachineSession(tmp_path,'chosen-model',{'name':'fixture'})
        result,trace=session.complete(CadProgram,'Author CAD',[{'type':'text','text':'source'}])
    assert len(result.components)==2
    assert '.loft(' in result.python_source
    assert trace['session_id']=='ses_test'
    assert trace['served_model']=='served-model'
    assert trace['output_mode']=='json_text'
    assert 'format' not in request.call_args_list[2].args[2]
    assert request.call_args_list[2].args[2]['tools']=={'bash':False,'read':False,'write':False}
    assert (tmp_path/'opencode-session.json').exists()


def test_native_cad_error_returns_to_the_author_and_corrections_are_bounded(tmp_path,monkeypatch):
    class Author:
        session_id='persistent-session'
        def __init__(self): self.prompts=[]
        def complete(self,contract,instruction,content):
            self.prompts.append(content)
            return contract.model_validate(program_data()),{'session_id':self.session_id}
    author=Author();attempts=[]
    def export(project,assembly,output,attempt,event):
        attempts.append(attempt)
        if attempt==0: raise RuntimeError('OCCT: invalid profile on jaw')
        project.cad_model={'source_sha256':'fixture-hash'}
    monkeypatch.setattr('protocol_pipeline.machine_cad.export_machine_cad',export)
    result=author_machine_cad(SimpleNamespace(mechanical=None),
        {'model':'test','equipment':{'name':'fixture'},'operations':[]},tmp_path,lambda event:None,author=author)
    assert result['authoring']=='opencode'
    assert result['cad_attempts']==2
    assert attempts==[0,1]
    assert 'OCCT: invalid profile on jaw' in author.prompts[1][-1]['text']
    assert 'equipment' in author.prompts[1][0]['text']
    assert result['representation']=='opencad-python'
    assert (tmp_path/'cad-failure-1.json').exists()
    assert (tmp_path/'cad-candidate-2.json').exists()
    monkeypatch.setattr('protocol_pipeline.machine_cad.export_machine_cad',lambda *args: (_ for _ in ()).throw(RuntimeError('still invalid')))
    author=Author()
    with pytest.raises(RuntimeError,match='still invalid'):
        author_machine_cad(SimpleNamespace(mechanical=None),
            {'model':'test','equipment':{'name':'fixture'},'operations':[]},tmp_path,lambda event:None,author=author)
    assert len(author.prompts)==3


def test_provider_error_is_explicit_without_a_hidden_retry(tmp_path):
    responses=[[],{'id':'session'}, {'info':{'error':{'name':'APIError','data':{'statusCode':400,'message':'invalid request'}}}}]
    with patch('protocol_pipeline.opencode_machine.ensure_server',return_value='http://local'), \
         patch.object(OpenCodeMachineSession,'request',side_effect=responses) as request:
        session=OpenCodeMachineSession(tmp_path,'model',{'name':'fixture'})
        with pytest.raises(RuntimeError,match='invalid request'):
            session.complete(CadProgram,'Author',[])
    assert request.call_count==3


def test_gmi_is_explicit_and_does_not_replace_the_default_provider(tmp_path):
    from protocol_pipeline.machines import MachineOptions
    assert MachineOptions(model='existing').provider=='nebius'
    assert MachineOptions(model='openai/gpt-6.1-sol',provider='gmi').provider=='gmi'
    responses=[[],{'id':'gmi-session'},{'info':{'modelID':'openai/gpt-6.1-sol'},'parts':[{'type':'text','text':json.dumps(program_data())}]}]
    with patch('protocol_pipeline.opencode_machine.ensure_server',return_value='http://local'), \
         patch.object(OpenCodeMachineSession,'request',side_effect=responses) as request:
        session=OpenCodeMachineSession(tmp_path,'openai/gpt-6.1-sol',{'name':'fixture'},provider='gmi')
        session.complete(CadProgram,'Author',[])
    assert request.call_args.args[2]['model']=={'providerID':'gmi','modelID':'openai/gpt-6.1-sol'}


def test_forma_context_also_uses_opencode_and_preserves_previous_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Forma route and visual revisions must not revert to primitive generation."""
    prior = tmp_path / 'prior'
    prior.mkdir()
    (prior / 'machine-cad-program.json').write_text(json.dumps(program_data()))
    output = tmp_path / 'revision'
    output.mkdir()
    prompts = []

    class Author:
        """Capture the source and correction context sent to OpenCode."""

        session_id = 'native-program-session'

        def complete(self, contract: type[CadProgram], instruction: str,
                     content: list[dict[str, Any]]) -> tuple[CadProgram, dict[str, Any]]:
            """Return deterministic source as a transport fixture."""
            prompts.append(content)
            return contract.model_validate(program_data()), {'session_id': self.session_id}

    monkeypatch.setattr('protocol_pipeline.opencode_machine.OpenCodeMachineSession', lambda *args, **kwargs: Author())

    def export(project: Any, *args: Any) -> None:
        """Stand in for the separately tested native exporter."""
        project.cad_model = {'source_sha256': 'fixture-hash'}

    monkeypatch.setattr('protocol_pipeline.machine_cad.export_machine_cad', export)
    result = author_machine_cad(SimpleNamespace(mechanical=None), {
        'model': 'fixture', 'equipment': {'name': 'mount'}, 'operations': [],
        'resume_from': str(prior), 'visual_feedback': {'instructions': 'Enlarge the mounting holes'},
    }, output, lambda _: None)
    context = json.loads(prompts[0][0]['text'])
    assert context['previous_design']['python_source'] == program_data()['python_source']
    assert context['visual_feedback']['instructions'] == 'Enlarge the mounting holes'
    assert result['authoring'] == 'opencode'
    assert (output / 'machine-cad-program.json').is_file()
