# SPDX-License-Identifier: MPL-2.0
"""Source-aligned scenario05 storyboard; authored motion, not robot simulation."""
from copy import deepcopy
import hashlib
import json


def stacking_storyboard(manifest: dict) -> tuple[dict, dict]:
    """User-directed copper/paper/copper stacking demo, separate from source inference."""
    scene=deepcopy(manifest)
    old_payload=set(scene.get('storyboard',{}).get('payload_instance_ids',[]))
    scene['instances']=[row for row in scene['instances'] if row['id'] not in old_payload]
    if len(scene['instances'])!=1:raise ValueError('Stacking demo needs one integrated machine')
    machine=scene['instances'][0]
    if machine['rotation']!=[0,0,0]:raise ValueError('Stacking demo requires the unrotated assembly')
    scene['assets']=[a for a in scene['assets'] if a['id']==machine['assetId']]
    scene['bundledAssets']=[a for a in scene['bundledAssets'] if a['id']==machine['assetId']]
    asset=scene['bundledAssets'][0]
    parts={p['metadata'].get('sourceId'):p for p in asset['parts']}
    if not {'x_carriage','z_slide','tweezer_tool'}<=parts.keys():raise ValueError('Named motion/tool bodies are missing')
    offset=asset['originOffset'];base=machine['position'];tracks=[]
    def world(x,y,z):return [base[0]+x/1000-offset[0],base[1]+z/1000-offset[1],base[2]-y/1000-offset[2]]
    def add_track(instance,positions,part=None):
        ident=instance+':'+(part or 'instance')
        row={'id':ident,'instanceId':instance,'keys':[{'id':f'{ident}-{i}','time':t,'position':p,'rotation':[0,0,0]} for i,(t,p) in enumerate(positions)]}
        if part:row['partId']=part
        tracks.append(row)
    # The receiving paper already modeled in the machine has its top at CAD Z=64 mm.
    # Demonstration thicknesses: copper 1 mm, paper 0.6 mm; not measurements.
    layers=[{'id':'copper-1','name':'Copper plate 1','start':(-220,-55,69.5),'target':(245,70,64),'thickness':1,'width':90,'color':[.78,.39,.23]},
            {'id':'paper-layer','name':'Paper separator sheet','start':(-220,50,70.7),'target':(245,70,65),'thickness':.6,'width':110,'color':[.98,.98,.94]},
            {'id':'copper-2','name':'Copper plate 2','start':(-80,-55,69.5),'target':(245,70,65.6),'thickness':1,'width':90,'color':[.78,.39,.23]}]
    poses=[]
    for index,layer in enumerate(layers):
        t=index*7;sx,sy,sz=layer['start'];tx,ty,tz=layer['target'];half=layer['thickness']/2
        layer.update(grip_at=t+1.4,release_at=t+5.8)
        poses.extend([(t,sx-27,sy,210),(t+1,sx-27,sy,sz+half),(t+1.4,sx-27,sy,sz+half),
                      (t+2.5,sx-27,sy,210),(t+4,tx-27,ty,210),(t+5.2,tx-27,ty,tz+half),
                      (t+5.8,tx-27,ty,tz+half),(t+6.5,tx-27,ty,210)])
    poses.extend([(21,218,70,210),(22,-190,-55,210),(24,-190,-55,210)])
    for name in ('x_carriage','z_slide','tweezer_tool'):
        add_track(machine['id'],[(t,[(x+190)/1000,0 if name=='x_carriage' else (z-126)/1000,
                                    0 if name=='x_carriage' else -(y+55)/1000]) for t,x,y,z in poses],parts[name]['id'])
    for name in ('x_carriage','z_slide'):parts[name]['color']=[.22,.43,.58]
    parts['tweezer_tool']['color']=[.18,.23,.25]
    if 'input_fixture' in parts:parts['input_fixture']['color']=[.72,.65,.47]
    if 'receiving_sheet' in parts:parts['receiving_sheet']['color']=[.98,.98,.94]
    def add_sheet(ident,name,width,thickness,color,start,count=1):
        w=width/1000;h=thickness/1000
        faces=[0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,3,7,6,3,6,2,0,4,7,0,7,3,1,2,6,1,6,5]
        meshes=[]
        for i in range(count):
            low=i*h;high=(i+1)*h
            vertices=[-w/2,low,-w/2,w/2,low,-w/2,w/2,high,-w/2,-w/2,high,-w/2,-w/2,low,w/2,w/2,low,w/2,w/2,high,w/2,-w/2,high,w/2]
            meshes.append({'id':ident+f'/sheet-{i}','name':name,'vertices':vertices,'indices':faces,'color':color,'metadata':{'representation':'User-directed storyboard material; assumed dimensions'}})
        actor={'id':ident,'name':name,'schemaVersion':1,'units':'m','upAxis':'Y','dimensions':[w,h*count,w],'originOffset':[0,0,0],
               'source':{'kind':'generated','generator':'form-industries','filename':ident+'.json','digest':hashlib.sha256(json.dumps(meshes).encode()).hexdigest()},
               'parts':meshes,'hierarchy':{'id':ident+'/root','name':name,'partIds':[p['id'] for p in meshes],'children':[]},
               'warnings':['User-directed demonstration material, not a measurement or physically validated simulation.']}
        scene['bundledAssets'].append(actor);scene['assets'].append({k:actor[k] for k in ('id','name','source','dimensions')})
        scene['instances'].append({'id':ident,'name':name,'assetId':ident,'visible':True,'position':world(*start),'rotation':[0,0,0]})
    for layer in layers:
        add_sheet(layer['id'],layer['name'],layer['width'],layer['thickness'],layer['color'],layer['start'])
        positions=[]
        for t,x,y,z in poses:
            if t<layer['grip_at']:point=layer['start']
            elif t<=layer['release_at']:point=(x+27,y,z-layer['thickness']/2)
            else:point=layer['target']
            positions.append((t,world(*point)))
        add_track(layer['id'],positions)
    add_sheet('paper-supply','Two spare paper sheets',110,.6,[.98,.98,.94],(-220,50,69.5),count=2)
    scene['animation']={'duration':24,'loop':False,'tracks':tracks}
    scene['storyboard']={'host_instance_id':machine['id'],'payload_instance_ids':[row['id'] for row in layers]+['paper-supply'],
        'basis':'User-requested copper/paper/copper stacking sequence','caption':'Requested stacking demo - illustrative CAD motion, not physical execution'}
    segments=[{'operation_id':'demo-stack-'+str(i+1),'label':label,'start_s':i*7,'end_s':(i+1)*7 if i<2 else 24,
               'implementation':label+' onto the stack in the container.','equipment_ids':['workcell'],'instance_ids':[machine['id']],
               'autonomy':'proposed_automated','basis':'user_requested_demo_sequence'}
              for i,label in enumerate(['1 / Place first copper plate on the receiving paper','2 / Pick a paper sheet and place it on the copper','3 / Place second copper plate on the paper'])]
    return scene,{'duration_s':24,'segments':segments,'method':'User-requested copper / paper / copper stacking demonstration',
        'timing_basis':'Authored demonstration timing; not measured source or machine timing',
        'final_stack_bottom_to_top':['existing receiving paper','copper plate 1','paper separator','copper plate 2'],
        'paper_supply':{'initial_sheets':3,'picked_sheets':1,'remaining_sheets':2},
        'limitations':['The earlier automatic video interpretation is retained separately; this sequence was explicitly directed by the user.',
                       'Material dimensions, grasp offsets and trajectories are assumed. No physical execution or collision-free travel is established.']}


def square_transfer_storyboard(manifest: dict, graph: dict, duration: float = 17.566667) -> tuple[dict, dict]:
    """Animate the known integrated fixture with two explicitly assumed foil actors."""
    scene=deepcopy(manifest)
    if len(scene['instances'])!=1:
        raise ValueError('This storyboard requires the single integrated workcell scene')
    machine=scene['instances'][0]
    if machine['rotation']!=[0,0,0]:
        raise ValueError('Storyboard expects the unrotated workcell coordinate frame')
    asset=next(a for a in scene['bundledAssets'] if a['id']==machine['assetId'])
    parts={p['metadata'].get('sourceId'):p for p in asset['parts']}
    if not {'x_carriage','z_slide','tweezer_tool'} <= parts.keys():
        raise ValueError('Storyboard requires named carriage, slide and attached tweezer CAD bodies')
    actions={a['id']:a for a in graph['actions']}
    if not {'action_1','action_2','action_3'}<=actions.keys():
        raise ValueError('Source action mapping is missing; review the storyboard mapping')
    # Positions are CAD millimeters, Z-up. Source video supplies ordering and phase windows;
    # geometric trajectories and workpiece dimensions are explicit storyboard assumptions.
    poses=[(0,-190,-55,160),(.5,-247,-55,160),(1.2,-247,-55,70),(1.5,-247,-55,70),
           (2.6,-247,-55,210),(4.8,208,60,210),(5.033333,208,60,210),(6.1,208,60,64.5),
           (6.3,208,60,64.5),(6.6,208,60,90),(7,208,60,64.5),(7.2,208,60,75),
           (7.7,218,70,75),(8,218,70,64.5),(8.3,218,70,64.5),(9.3,218,70,210),
           (10,-107,-55,210),(12.1,-107,-55,150),(12.533333,-107,-55,70),(13,-107,-55,70),
           (14,-107,-55,210),(15.033333,443,-35,210),(duration,443,-35,210)]
    tracks=[]
    def track(instance,positions,part=None):
        ident=instance+':'+(part or 'instance')
        value={'id':ident,'instanceId':instance,'keys':[{'id':f'{ident}-{i}','time':t,'position':position,'rotation':[0,0,0]} for i,(t,position) in enumerate(positions)]}
        if part:value['partId']=part
        tracks.append(value)
    for name in ('x_carriage','z_slide','tweezer_tool'):
        track(machine['id'],[(t,[(x+190)/1000,0 if name=='x_carriage' else (z-126)/1000,
                                0 if name=='x_carriage' else -(y+55)/1000]) for t,x,y,z in poses],parts[name]['id'])
    for name in ('x_carriage','z_slide'):parts[name]['color']=[.22,.43,.58]
    parts['tweezer_tool']['color']=[.18,.23,.25]
    if 'input_fixture' in parts:parts['input_fixture']['color']=[.72,.65,.47]
    if 'receiving_sheet' in parts:parts['receiving_sheet']['color']=[.95,.96,.94]
    # 90 x 90 x 1 mm visual reference sheets: not measured dimensions from the video.
    w,h,d=.09,.001,.09
    vertices=[-w/2,0,-d/2,w/2,0,-d/2,w/2,h,-d/2,-w/2,h,-d/2,-w/2,0,d/2,w/2,0,d/2,w/2,h,d/2,-w/2,h,d/2]
    faces=[0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,3,7,6,3,6,2,0,4,7,0,7,3,1,2,6,1,6,5]
    ident='source-square-sheet'
    actor={'id':ident,'name':'Copper-colored source workpiece (assumed dimensions)','schemaVersion':1,'units':'m','upAxis':'Y',
           'dimensions':[w,h,d],'originOffset':[0,0,0],
           'source':{'kind':'generated','generator':'form-industries','filename':'storyboard-workpiece.json',
                     'digest':hashlib.sha256(json.dumps(vertices).encode()).hexdigest()},
           'parts':[{'id':ident+'/foil','name':'Source workpiece','vertices':vertices,'indices':faces,'color':[.78,.39,.23],
                     'metadata':{'representation':'Storyboard source workpiece; assumed 90 x 90 x 1 mm'}}],
           'hierarchy':{'id':ident+'/root','name':'Source workpiece','partIds':[ident+'/foil'],'children':[]},
           'warnings':['Dimensions and grasp trajectory are illustrative, not source measurements.']}
    scene['bundledAssets'].append(actor)
    scene['assets'].append({key:actor[key] for key in ('id','name','source','dimensions')})
    offset=asset['originOffset'];base=machine['position']
    def world(x,y,z):return [base[0]+x/1000-offset[0],base[1]+z/1000-offset[1],base[2]-y/1000-offset[2]]
    for ident,start in [('sheet-A',(-220,-55,69.5)),('sheet-B',(-80,-55,69.5))]:
        scene['instances'].append({'id':ident,'name':ident,'assetId':actor['id'],'visible':True,'position':world(*start),'rotation':[0,0,0]})
        positions=[]
        for t,x,y,z in poses:
            if ident=='sheet-A':
                if t<1.5:point=start
                elif t<=6.3 or 7<=t<=8.3:point=(x+27,y,z-.5)
                elif t<7:point=(235,60,64)
                else:point=(245,70,64)
            else:
                point=start if t<13 else (x+27,y,z-.5)
            positions.append((t,world(*point)))
        track(ident,positions)
    scene['animation']={'duration':duration,'loop':False,'tracks':tracks}
    scene['storyboard']={'host_instance_id':machine['id'],'payload_instance_ids':['sheet-A','sheet-B'],
                         'basis':'Illustrative source workpieces, not additional machine assets'}
    segments=[{'operation_id':'op_lift','label':'Pick the first square from the mat','start_s':0,'end_s':5.033333,'source_action_id':'action_1'},
              {'operation_id':'op_place','label':'Place and adjust on the receiving sheet','start_s':5.033333,'end_s':10.033333,'source_action_id':'action_2'},
              {'operation_id':'op_clear_mat','label':'Remove the remaining square; hold clear of the mat','start_s':10.033333,'end_s':duration,'source_action_id':'action_3'}]
    for segment in segments:
        action=actions[segment['source_action_id']]
        segment.update(implementation=action['interpretation'],equipment_ids=['workcell'],instance_ids=[machine['id']],
                       autonomy='proposed_automated',source_interval_s=[action['start_s'],action['end_s']],
                       evidence_frame_ids=action['evidence_frame_ids'])
    return scene,{'duration_s':duration,'segments':segments,'method':'Authored source-aligned keyframes with native CAD parts; fixed machine base',
                  'timing_basis':'Source action windows; interpolated storyboard paths, not measured machine cycle time',
                  'limitations':['Workpiece size, grasp offset and trajectories are illustrative assumptions.',
                                 'No inverse kinematics, collision-free travel, grip force or physical execution is established.',
                                 'Second object remains held outside the mat; its downstream destination is not inferred.']}
