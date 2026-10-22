# SPDX-License-Identifier: MPL-2.0
from protocol_pipeline.storyboard import square_transfer_storyboard, stacking_storyboard


def test_source_sequence_moves_tool_and_workpieces_not_whole_machine():
    names=['base','x_carriage','z_slide','tweezer_tool','input_fixture','receiving_sheet']
    asset={'id':'machine','originOffset':[0,0,0], 'parts':[{'id':name,'metadata':{'sourceId':name}} for name in names]}
    manifest={'instances':[{'id':'cell','assetId':'machine','position':[0,0,0],'rotation':[0,0,0]}],
              'bundledAssets':[asset],'assets':[]}
    graph={'actions':[{'id':f'action_{i}','start_s':i,'end_s':i+1,'interpretation':'Fixture action','evidence_frame_ids':['f1']} for i in range(1,4)]}
    scene,report=square_transfer_storyboard(manifest,graph)
    tracks=scene['animation']['tracks']
    assert len(tracks)==5
    assert {t.get('partId') for t in tracks if t['instanceId']=='cell'}=={'x_carriage','z_slide','tweezer_tool'}
    assert scene['instances'][0]['position']==[0,0,0]
    assert [s['source_action_id'] for s in report['segments']]==['action_1','action_2','action_3']
    a=next(t for t in tracks if t['instanceId']=='sheet-A')
    b=next(t for t in tracks if t['instanceId']=='sheet-B')
    assert a['keys'][0]['position']==[-.22,.0695,.055]
    assert a['keys'][-1]['position']==[.245,.064,-.07]
    assert b['keys'][-1]['position']==[.47,.2095,.035]
    assert scene['animation']['loop'] is False
    assert len(manifest['instances'])==1  # original static scene preserved
    stacked,stack_report=stacking_storyboard(scene)
    assert stack_report['final_stack_bottom_to_top']==['existing receiving paper','copper plate 1','paper separator','copper plate 2']
    assert stack_report['paper_supply']=={'initial_sheets':3,'picked_sheets':1,'remaining_sheets':2}
    paper=next(a for a in stacked['bundledAssets'] if a['id']=='paper-layer')
    supply=next(a for a in stacked['bundledAssets'] if a['id']=='paper-supply')
    assert paper['dimensions']==[.11,.0006,.11]
    assert len(supply['parts'])==2
    tracks={track['instanceId']:track for track in stacked['animation']['tracks'] if 'partId' not in track}
    assert set(tracks)=={'copper-1','paper-layer','copper-2'}
    assert all(abs(tracks[key]['keys'][-1]['position'][1]-height)<1e-9 for key,height in [('copper-1',.064),('paper-layer',.065),('copper-2',.0656)])
    assert all(track['keys'][-1]['position'][0]==.245 for track in tracks.values())
