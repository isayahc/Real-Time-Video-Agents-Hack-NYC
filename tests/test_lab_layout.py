from copy import deepcopy
import json
from fastapi.testclient import TestClient

from protocol_pipeline.lab_layout import plan_lab, TEMPLATE


def inputs():
    equipment = [{'id':'robot','name':'Robot','role':'Move workpieces','category':'actuator'},
                 {'id':'camera','name':'Camera','role':'Inspect workpieces','category':'sensor'},
                 {'id':'power','name':'Vacuum pump','role':'Supply vacuum','category':'other'},
                 {'id':'stock','name':'Containers','role':'Input stock','category':'consumable'}]
    manifest = {'room':[6,5,3], 'assets':[{'id': e['id'], 'dimensions':[.3,.4,.3]} for e in equipment],
                'instances':[{'id':str(i),'assetId':e['id'],'name':e['name'],'visible':True,'position':[0,0,0]} for i,e in enumerate(equipment)],
                'animation':{'tracks':[{'old':'motion'}]}, 'bundledAssets':[]}
    preview = {'instances':[{'id':str(i),'equipment_id':e['id']} for i,e in enumerate(equipment)]}
    proposal = {'equipment':equipment,'operation_designs':[{'source_operation_id':'transfer','equipment_ids':['robot','camera','power']}]}
    return manifest, preview, proposal


def test_semantic_zones_clearance_and_provenance():
    manifest, preview, proposal = inputs()
    original = deepcopy(manifest)
    report, scene = plan_lab(manifest, preview, proposal)
    assert report['placed_count'] == 4
    rows = {r['equipment_id']:r for r in report['placements']}
    assert rows['power']['zone'] == 'utilities'
    assert rows['stock']['zone'] == 'inventory'
    assert rows['camera']['zone'] == rows['robot']['zone'] == 'workbench'
    assert rows['robot']['position_m'][1] == .9
    assert rows['robot']['related_equipment_ids'] == ['camera','power']
    assert any('mount' in issue for issue in report['issues'])
    for row in rows.values():
        x,y,z = row['position_m']; w,d = row['footprint_m']
        assert z+d/2 <= -.6 or z-d/2 >= .6
        for other in rows.values():
            if other is row: continue
            assert abs(x-other['position_m'][0]) >= (w+other['footprint_m'][0])/2 or abs(z-other['position_m'][2]) >= (d+other['footprint_m'][1])/2
    assert manifest == original
    assert scene['animation']['tracks'] == []
    assert scene['room'] == TEMPLATE['room_m']
    assert len(scene['instances']) == 6


def test_oversized_machine_remains_unplaced_without_scaling():
    manifest, preview, proposal = inputs()
    manifest['assets'][0]['dimensions'] = [20,4,20]
    report, scene = plan_lab(manifest, preview, proposal)
    row = next(r for r in report['placements'] if r['equipment_id']=='robot')
    assert row['status'] == 'unplaced'
    assert report['status'] == 'needs_review'
    assert scene['assets'][0]['dimensions'] == [20,4,20]
    assert next(i for i in scene['instances'] if i['id']=='0')['visible'] is False


def test_lab_endpoint_persists_separate_plan_and_rejects_stale_source(tmp_path, monkeypatch):
    from protocol_pipeline.web import create_app
    run = 'a'*32
    folder = tmp_path / run
    scene_dir = folder / 'scene' / 'baseline'
    design_dir = folder / 'autonomy' / 'design'
    scene_dir.mkdir(parents=True)
    design_dir.mkdir(parents=True)
    (folder / 'job.json').write_text(json.dumps({'id':run, 'stage':'completed', 'created_at':0}))
    manifest, preview, proposal = inputs()
    (scene_dir / 'scene.oi.json').write_text(json.dumps(manifest))
    (scene_dir / 'preview.json').write_text(json.dumps(preview))
    (design_dir / 'proposal.json').write_text(json.dumps({'proposal':proposal}))
    app = create_app(tmp_path, lambda: None)
    monkeypatch.setattr(app.state.store, 'scene_state', lambda _: {'stage':'completed','attempt_id':'baseline'})
    monkeypatch.setattr(app.state.store, 'design_state', lambda _: {'stage':'completed','attempt_id':'design'})
    with TestClient(app) as client:
        assert client.get(f'/api/runs/{run}/lab').json()['status'] == 'not_started'
        response = client.post(f'/api/runs/{run}/lab', headers={'X-Workbench-Request':'1'})
        assert response.status_code == 200
        assert response.json()['placed_count'] == 4
        assert client.get(f'/api/runs/{run}/lab/artifacts/scene.oi.json').status_code == 200
        assert json.loads((scene_dir / 'scene.oi.json').read_text()) == manifest
        manifest['room'] = [10,10,3]
        (scene_dir / 'scene.oi.json').write_text(json.dumps(manifest))
        assert client.get(f'/api/runs/{run}/lab').json()['status'] == 'stale'
        assert client.get(f'/api/runs/{run}/lab/artifacts/scene.oi.json').status_code == 409
