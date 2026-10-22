# SPDX-License-Identifier: MPL-2.0
"""Native scene prerequisites, assumed timing, lineage and actual OpenIndustries interpolation."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from protocol_pipeline.autonomy import AutonomyProposal
from protocol_pipeline.compiler import ProtocolSpecification
from protocol_pipeline.pipeline import sha256
from protocol_pipeline.scenes import SceneOptions, ScenePlacement, build_rehearsal, openindustries_runtime
from test_autonomy import proposal_fixture

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which('node'),reason='Node.js is required for packing tests')
def test_size_aware_layout_and_inventory_regressions():
    subprocess.run(['node','--test',str(ROOT/'tests/test_scene_layout.cjs')],check=True,capture_output=True,text=True,timeout=30)


def scene_inputs(tmp_path: Path):
    raw = json.loads((ROOT / 'examples/extraction/recorded-response.json').read_text())['responses'][0]['response']
    protocol = ProtocolSpecification.model_validate(raw)
    protocol_path = tmp_path / 'protocol.json'
    protocol_path.write_text(protocol.model_dump_json(), encoding='utf-8')
    proposal_path = tmp_path / 'proposal.json'
    proposal_path.write_text(json.dumps({'source_protocol_sha256': sha256(protocol_path),
        'proposal': AutonomyProposal.model_validate(proposal_fixture(protocol)).model_dump()}), encoding='utf-8')
    return proposal_path, protocol_path


def test_missing_runtime_is_explicit_before_output(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENINDUSTRIES_ROOT', str(tmp_path / 'missing-runtime'))
    assert openindustries_runtime()['available'] is False
    proposal, protocol = scene_inputs(tmp_path)
    with pytest.raises(ValueError, match='OPENINDUSTRIES_ROOT'):
        build_rehearsal(proposal, protocol, tmp_path / 'output', SceneOptions())
    assert not (tmp_path / 'output').exists()


def test_layout_and_time_bounds():
    for invalid in ({'room_width_m': 0}, {'room_height_m': float('nan')}, {'seconds_per_operation': 0}, {'seconds_per_operation': 11}):
        with pytest.raises(ValueError):
            SceneOptions(**invalid)


@pytest.mark.skipif(not openindustries_runtime()['available'], reason='Optional native OpenIndustries checkout/dependencies are required')
def test_native_scene_has_geometry_motion_and_portable_lineage(tmp_path):
    proposal, protocol = scene_inputs(tmp_path)
    machine = tmp_path / 'machine.forma.json'
    machine.write_text(json.dumps({'hardware_ir_version':'0.2','overview':{'title':'Explicit synthetic CAD fixture'},
        'cad_model':{'meshes':[{'name':'Test tetrahedron','vertices':[0,0,0,200,0,0,0,200,0,0,0,200],
                               'faces':[0,2,1,0,1,3,0,3,2,1,2,3]}]}}))
    output = tmp_path / 'native'
    report = build_rehearsal(proposal, protocol, output, SceneOptions(), [{'equipment_id':'robot','path':str(machine)}])
    assert report['portable_roundtrip'] is True
    assert report['animation_tracks'] == 2
    assert report['physical_validation'] is False
    assert report['source_proposal_sha256'] == sha256(proposal)
    manifest = json.loads((output / 'scene.oi.json').read_text())
    assert manifest['format'] == 'astra.scene'
    assert manifest['bundledAssets']
    assert manifest['animation']['tracks'][0]['keys']
    preview = json.loads((output / 'preview.json').read_text())
    assert len(preview['segments']) == len(json.loads(protocol.read_text())['operations'])
    keys = manifest['animation']['tracks'][0]['keys']
    assert any(key['position'] != keys[0]['position'] for key in keys)
    assert len(preview['instances']) == 2  # both requested units, with no fabricated layout bench
    assert report['machine_asset_sha256']['robot'] == sha256(machine)
    mounted = SceneOptions(placements=[ScenePlacement(instance_id='equipment-1',position_m=(.05,.25,0),
        rotation_y_deg=90,relation='mounted',anchor_instance_id='equipment-0',rationale='Explicit synthetic mount')])
    build_rehearsal(proposal,protocol,tmp_path/'mounted',mounted,[{'equipment_id':'robot','path':str(machine)}])
    mounted_manifest=json.loads((tmp_path/'mounted/scene.oi.json').read_text())
    child=next(track for track in mounted_manifest['animation']['tracks'] if track['instanceId']=='equipment-1')
    assert all(key['rotation']==[0,90,0] for key in child['keys'])
    assert max(key['position'][0] for key in child['keys']) == pytest.approx(.15)
    protocol.write_text(protocol.read_text() + ' ', encoding='utf-8')
    with pytest.raises(ValueError, match='source protocol has changed'):
        build_rehearsal(proposal, protocol, tmp_path / 'tampered', SceneOptions())
    assert not (tmp_path / 'tampered').exists()
