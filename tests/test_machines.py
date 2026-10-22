# SPDX-License-Identifier: MPL-2.0
"""Machine identity, native generation handoff and strict CAD readiness."""
import json
import re
import os
from types import SimpleNamespace

import pytest

from protocol_pipeline.machines import generate_machine, machine_key, process_alive
from test_scenes import scene_inputs


def test_machine_keys_are_stable_safe_identifiers():
    key = machine_key('../a/b')
    assert re.fullmatch('[a-f0-9]{24}', key)
    assert key == machine_key('../a/b')
    assert key != machine_key('a/b')


def test_worker_liveness_checks_without_process_polling():
    assert process_alive(os.getpid())
    assert not process_alive(0)
    assert not process_alive(-1)


def test_machine_cad_requires_source_instead_of_legacy_primitive_data():
    """Old primitive candidates cannot silently satisfy the new authoring contract."""
    from protocol_pipeline.opencad_program import CadProgram
    with pytest.raises(ValueError):
        CadProgram.model_validate({'description':'Legacy primitive fixture',
            'parts':[{'name':'box','shape':'box','size_mm':[100,20,10],'center_mm':[0,0,0]}],
            'assumptions':['Synthetic dimensions']})


def test_forma_batch_is_independent_of_server_reload(tmp_path, monkeypatch):
    from protocol_pipeline.web import JobStore
    import subprocess
    calls = []
    monkeypatch.setattr('protocol_pipeline.web.subprocess.Popen', lambda args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(pid=12345))
    store = JobStore(tmp_path, lambda: None)
    run_id = 'a' * 32
    path = tmp_path / run_id
    path.mkdir()
    (path / 'job.json').write_text(json.dumps({'id':run_id,'stage':'completed'}))
    store.launch_machines(run_id, ['b'*24], 'c'*32)
    assert 'protocol_pipeline.machine_batch_worker' in calls[0][0]
    if os.name == 'nt':
        assert calls[0][1]['creationflags'] & subprocess.CREATE_NO_WINDOW
    else:
        assert calls[0][1]['start_new_session'] is True
    worker = json.loads((path / 'machines/batches' / ('c'*32) / 'worker.json').read_text())
    assert worker['pid'] == 12345
    assert worker['stage'] == 'running'
    store.executor.shutdown()


@pytest.mark.parametrize('has_mesh', [True, False])
def test_forma_worker_handoff_needs_actual_mesh(tmp_path, monkeypatch, has_mesh):
    proposal, _ = scene_inputs(tmp_path)
    monkeypatch.setenv('NEBIUS_API_KEY', 'fixture-secret-not-on-disk')
    monkeypatch.setattr('protocol_pipeline.machines.forma_runtime', lambda: {
        'available': True, 'cad_adapter': str(tmp_path / 'adapter.py'), 'source_root': str(tmp_path / 'incompatible-forma-checkout')})
    output = tmp_path / 'generated'
    def worker(command, **kwargs):
        assert 'fixture-secret-not-on-disk' not in ' '.join(command)
        assert kwargs['env']['NEBIUS_API_KEY'] == 'fixture-secret-not-on-disk'
        assert str(tmp_path / 'incompatible-forma-checkout') not in kwargs['env']['PYTHONPATH'].split(os.pathsep)
        assert kwargs['env']['FORMA_CAD_ADAPTER_PATH'] == str(tmp_path / 'adapter.py')
        (output / 'machine-report.json').write_text(json.dumps({'status':'fixture','physical_validation':False}))
        cad = {'meshes':[{'vertices':[0,0,0,1,0,0,0,1,0],'faces':[0,1,2]}]} if has_mesh else {}
        (output / 'machine.forma.json').write_text(json.dumps({'project_ir':{'cad_model':cad}}))
        return SimpleNamespace(returncode=0,stdout='fixture worker',stderr='')
    monkeypatch.setattr('protocol_pipeline.machines.subprocess.run', worker)
    if has_mesh:
        assert generate_machine(proposal, 'robot', output, 'fixture')['status'] == 'fixture'
    else:
        with pytest.raises(ValueError, match='no CAD mesh'):
            generate_machine(proposal, 'robot', output, 'fixture')
    assert 'fixture-secret-not-on-disk' not in (output / 'machine-input.json').read_text()
