# SPDX-License-Identifier: MPL-2.0
"""Grounded visual critique, matched native captures, reversible correction and score gates."""
import base64
import copy
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import uuid
import zlib

import pytest

from protocol_pipeline.pipeline import save_json,sha256
from protocol_pipeline.visual_review import (CaptureBundle,VisualCritique,VisualReviewStart,VIEW_IDS,
    accept_after_capture,decode_capture,execute_review,review_state,rollback_review,start_review,
    validate_critique,visibly_improved)


def capture_fixture(changed=False):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',960,640,8,6,0,0,0))
    pixel=b'\x36\x60\x45\xff' if changed else b'\x35\x60\x45\xff'
    png+=chunk(b'IDAT',zlib.compress((b'\0'+pixel*960)*640))+chunk(b'IEND',b'')
    return CaptureBundle.model_validate({'renderer':'Explicit synthetic capture fixture',
        'frames':[{'id':view,'label':view,'position':[2,2,2],'target':[0,0,0],'time_s':0} for view in sorted(VIEW_IDS)],
        'images':[{'id':view,'label':view,'png_data_url':'data:image/png;base64,'+base64.b64encode(png).decode()} for view in sorted(VIEW_IDS)]})


def critique_fixture(after=False):
    return VisualCritique.model_validate({'status':'needs_improvement','score':65 if after else 30,
        'summary':'Synthetic AFTER fixture' if after else 'Synthetic BEFORE fixture',
        'issues':[] if after else [{'id':'geometry-1','kind':'geometry','severity':'high','equipment_ids':['robot'],
            'description':'Synthetic duplicated support','evidence_view_ids':['render-isometric'],'correction':'Remove duplicate support'}],
        'cad_changes':[] if after else [{'equipment_id':'robot','issue_ids':['geometry-1'],'instructions':'Synthetic CAD revision'}],
        'layout_changes':[],'resolved_issue_ids':['geometry-1'] if after else [],'limitations':['Synthetic test, not visual/model quality evidence']})


def test_capture_validation_and_grounded_criticism():
    capture=capture_fixture();assert set(decode_capture(capture))==VIEW_IDS
    context={'instances':[{'instance_id':'equipment-0','equipment_id':'robot'}]}
    validate_critique(critique_fixture(),context,VIEW_IDS)
    for change in ('equipment','image','resolved','cad_issue'):
        raw=critique_fixture().model_dump()
        if change=='equipment':raw['issues'][0]['equipment_ids']=['invented']
        elif change=='image':raw['issues'][0]['evidence_view_ids']=['imaginary-image']
        elif change=='resolved':raw['resolved_issue_ids']=['not-reviewed']
        else:raw['cad_changes'][0]['issue_ids']=['unknown']
        with pytest.raises(ValueError):validate_critique(VisualCritique.model_validate(raw),context,VIEW_IDS)
    raw=capture.model_dump();raw['images'][0]['png_data_url']='data:image/png;base64,invalid'
    with pytest.raises(ValueError):decode_capture(CaptureBundle.model_validate(raw))


def test_visual_score_is_conditional_and_does_not_force_a_worse_candidate():
    before=critique_fixture();after=critique_fixture(True)
    assert visibly_improved(before,after)
    after.score=32;assert not visibly_improved(before,after)
    after.score=99;after.status='insufficient_evidence';assert not visibly_improved(before,after)
    after.status='acceptable';after.issues=before.issues*2;assert not visibly_improved(before,after)
    after.issues=before.issues;assert not visibly_improved(before,after)


def test_cad_revision_does_not_move_an_unchanged_mounting_anchor():
    from protocol_pipeline.visual_review import correction_placements
    from protocol_pipeline.scenes import ScenePlacement
    context={'instances':[{'instance_id':'stage','position_m':[.375,0,-.42],'rotation_deg':[0,0,0]},
                          {'instance_id':'gripper','position_m':[-1,0,0],'rotation_deg':[0,0,0]}]}
    changed=ScenePlacement(instance_id='gripper',position_m=(.375,.3,-.42),relation='mounted',anchor_instance_id='stage',rationale='Mount the gripper')
    result={item.instance_id:item for item in correction_placements(context,[changed])}
    assert result['stage'].position_m==(.375,0,-.42)
    assert result['gripper'].position_m==(.375,.3,-.42)


def test_review_uses_simple_provider_json_and_validates_the_full_critique_locally(tmp_path,monkeypatch):
    from protocol_pipeline.visual_review import review_images,save_capture,VisualReviewOptions,VisionReviewData
    save_capture(tmp_path/'before',capture_fixture())
    class Client:
        def complete(self,model,contract,instruction,content,max_tokens,json_mode):
            assert contract is VisionReviewData
            assert '$defs' not in contract.model_json_schema()
            assert max_tokens==12000
            assert json_mode is True
            return contract.model_validate(critique_fixture().model_dump()),{'requested_model':model,'response_json_text':'fixture'}
    monkeypatch.setattr('protocol_pipeline.visual_review.NebiusClient',lambda key:Client())
    monkeypatch.setenv('NEBIUS_API_KEY','synthetic-secret')
    result=review_images(tmp_path,'before',VisualReviewOptions(vision_model='vision',cad_model='cad'),
                         {'instances':[{'instance_id':'equipment-0','equipment_id':'robot'}]},[])
    assert result.score==30
    assert (tmp_path/'before-candidate.json').exists()
    assert 'synthetic-secret' not in (tmp_path/'before-provider.json').read_text()


@pytest.mark.parametrize('improves',[True,False])
def test_visual_pass_preserves_sources_and_can_restore_active_versions(tmp_path,monkeypatch,improves):
    from test_autonomy import proposal_fixture
    from protocol_pipeline.compiler import ProtocolSpecification
    from test_scenes import ROOT

    run_id='a'*32;run=tmp_path/run_id;run.mkdir()
    raw=json.loads((ROOT/'examples/extraction/recorded-response.json').read_text())['responses'][0]['response']
    protocol=ProtocolSpecification.model_validate(raw);proposal=proposal_fixture(protocol)
    proposal['operation_designs']=proposal['operation_designs'][:1]
    (run/'autonomy'/'design').mkdir(parents=True);save_json(run/'autonomy/design/proposal.json',{'proposal':proposal})
    (run/'extracted').mkdir();save_json(run/'extracted/extracted-protocol.json',protocol.model_dump())
    (run/'ingested/frames').mkdir(parents=True);(run/'ingested/frames/frame_0000.jpg').write_bytes(b'fixture only')
    save_json(run/'ingested/manifest.json',{'frames':[{'id':'frame_0000','path':'frames/frame_0000.jpg'}]})
    machine_key='b'*24;attempt='c'*32;scene_attempt='d'*32
    machine=run/'machines'/machine_key/attempt;machine.mkdir(parents=True);save_json(machine/'machine.forma.json',{'fixture':'baseline'})
    machine_job={'stage':'completed','attempt_id':attempt,'equipment_id':'robot','model':'fixture'}
    save_json(machine.parent/'job.json',machine_job)
    scene=run/'scene'/scene_attempt;scene.mkdir(parents=True)
    manifest={'room':[6,5,3],'assets':[{'id':'asset','dimensions':[1,1,1]}],
        'instances':[{'id':'equipment-0','assetId':'asset','name':'Fixture','position':[0,0,0],'rotation':[0,0,0]}]}
    preview={'instances':[{'id':'equipment-0','equipment_id':'robot'}]}
    save_json(scene/'scene.oi.json',manifest);save_json(scene/'preview.json',preview)
    scene_job={'stage':'completed','attempt_id':scene_attempt,'options':{}}
    save_json(scene.parent/'job.json',scene_job)
    def machines():
        job=json.loads((machine.parent/'job.json').read_text())
        return {'stage':'ready','machines':[{'id':'robot','key':machine_key,'name':'Fixture','role':'Synthetic test',**job}]}
    store=SimpleNamespace(path=lambda _:run,scene_state=lambda _:json.loads((run/'scene/job.json').read_text()),
        machines_state=lambda _:machines(),design_state=lambda _:{'stage':'completed','attempt_id':'design','design':{'proposal':proposal}})
    launches=[];monkeypatch.setattr('protocol_pipeline.visual_review.launch_review',lambda *args:launches.append(args[-1]))
    def reviewer(path,phase,*args):
        result=critique_fixture(phase=='after')
        if phase=='after' and not improves:result.score=25
        save_json(path/f'{phase}-critique.json',result.model_dump());return result
    monkeypatch.setattr('protocol_pipeline.visual_review.review_images',reviewer)
    def generate(proposal,equipment,output,model,**kwargs):output.mkdir();save_json(output/'machine.forma.json',{'fixture':'candidate'})
    monkeypatch.setattr('protocol_pipeline.visual_review.generate_machine',generate)
    def build(proposal,protocol,output,options,assets):
        output.mkdir();save_json(output/'scene.oi.json',manifest);save_json(output/'preview.json',preview)
    monkeypatch.setattr('protocol_pipeline.visual_review.build_rehearsal',build)
    original_protocol=(run/'extracted/extracted-protocol.json').read_bytes()
    start=VisualReviewStart(scene_attempt_id=scene_attempt,options={'vision_model':'vision','cad_model':'cad'},capture=capture_fixture())
    state=start_review(store,run_id,start);review_id=state['id']
    execute_review(store,run_id,review_id,'before')
    assert review_state(store,run_id)['stage']=='awaiting_after_capture'
    assert store.scene_state(run_id)['attempt_id']==scene_attempt
    accept_after_capture(store,run_id,review_id,capture_fixture(changed=True))
    execute_review(store,run_id,review_id,'after')
    assert review_state(store,run_id)['stage']==('applied' if improves else 'kept_original')
    assert (run/'extracted/extracted-protocol.json').read_bytes()==original_protocol
    assert json.loads((machine/'machine.forma.json').read_text())['fixture']=='baseline'
    if improves:
        assert store.scene_state(run_id)['attempt_id']!=scene_attempt
        rollback_review(store,run_id,review_id)
        assert store.scene_state(run_id)['attempt_id']==scene_attempt
        assert json.loads((machine.parent/'job.json').read_text())['attempt_id']==attempt
