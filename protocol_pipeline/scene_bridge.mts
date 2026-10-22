// SPDX-License-Identifier: MPL-2.0
/** Assemble generated Forma CAD with the actual OpenIndustries workspace/animation APIs. */
import {readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {instancePlan,planLayout} from './scene_layout.mjs';

async function main(){
  const root=resolve(process.argv[2]),output=resolve(process.argv[3]);
  const {importForm}=await import(pathToFileURL(resolve(root,'src/lib/form.ts')).href);
  const {makeManifest,readManifest,hydrateManifest,writeKeyframe,evaluateWorkspace}=
    await import(pathToFileURL(resolve(root,'src/lib/workspace.ts')).href);
  const input=JSON.parse(await readFile(resolve(output,'scene-input.json'),'utf8'));
  const plan=input.proposal,seconds=input.seconds_per_operation,items:any[]=[],assetHashes:Record<string,string>={},inventory:any[]=[];
  for(const equipment of plan.equipment){
    const file=input.machine_assets.find((item:any)=>item.equipment_id===equipment.id);
    if(!file)throw new Error(`Missing generated machine: ${equipment.name}`);
    const raw=await readFile(file.path),digest=createHash('sha256').update(raw).digest('hex');
    if(digest!==file.sha256)throw new Error(`Generated machine changed while importing: ${equipment.name}`);
    const asset=importForm(JSON.parse(raw.toString('utf8')),`${equipment.id}.forma.json`,digest);
    if(!asset.parts.length || asset.parts.some((part:any)=>part.metadata.representation!=='CAD mesh'))
      throw new Error(`Generated machine ${equipment.name} did not import as native CAD mesh geometry`);
    assetHashes[equipment.id]=digest;
    const display=instancePlan(equipment,input.expand_stock_quantities??false);
    if(display.inventory)inventory.push({equipment_id:equipment.id,name:equipment.name,stock_quantity:equipment.quantity,displayed_samples:1});
    for(let number=0;number<display.count;number++){
      if(items.length>=1000)throw new Error('OpenIndustries supports at most 1000 equipment instances');
      items.push({id:`equipment-${items.length}`,name:display.inventory?`${equipment.name} · ${equipment.quantity} stocked (1 sample)`:`${equipment.name} ${number+1}/${equipment.quantity}`,
        asset,visible:true,position:[0,0,0],rotation:[0,0,0],equipmentId:equipment.id,category:equipment.category});
    }
  }
  const requestedPlacements=input.placements??[];
  const placedIds=new Set(requestedPlacements.map((placement:any)=>placement.instance_id));
  const fullyPlaced=requestedPlacements.length===items.length && placedIds.size===items.length && items.every(item=>placedIds.has(item.id));
  const layout=fullyPlaced?{fits:true,requested_room_m:input.room_m,room_m:[...input.room_m],suggested_room_m:input.room_m,
    room_adjusted:false,positions:Object.fromEntries(requestedPlacements.map((placement:any)=>[placement.instance_id,placement.position_m])),
    method:'Explicit baseline/review placements; actual unscaled CAD bounds checked after placement'}:planLayout(items,input.room_m,input.auto_fit_room??true);
  if(!layout.fits){await writeFile(resolve(output,'layout-report.json'),JSON.stringify(layout,null,2)+'\n',{flag:'wx'});throw new Error(layout.message);}
  items.forEach(item=>{item.position=layout.positions[item.id];});
  const byId=new Map(items.map(item=>[item.id,item])),seen=new Set();
  for(const placement of input.placements??[]){
    const item=byId.get(placement.instance_id);
    if(!item||seen.has(item.id))throw new Error('Visual placement references an unknown or duplicate instance');
    seen.add(item.id);
    if(placement.anchor_instance_id && (!byId.has(placement.anchor_instance_id)||placement.anchor_instance_id===item.id))throw new Error('Invalid mounting anchor');
    if(placement.relation==='mounted'&&!placement.anchor_instance_id)throw new Error('Mounted equipment needs an anchor instance');
    if(!placement.position_m.every(Number.isFinite)||placement.position_m[1]<0)throw new Error('Invalid world-space asset-bottom placement');
    item.position=placement.position_m;item.rotation=[0,placement.rotation_y_deg,0];item.anchorId=placement.anchor_instance_id;item.relation=placement.relation;
  }
  for(const item of items){let current=item;const chain=new Set();while(current?.anchorId){if(chain.has(current.id))throw new Error('Mounting relationships contain a cycle');chain.add(current.id);current=byId.get(current.anchorId);}}
  const required=[...layout.room_m];
  for(const item of items){
    const rotated=item.rotation[1]%180!==0,w=item.asset.dimensions[rotated?2:0],d=item.asset.dimensions[rotated?0:2];
    required[0]=Math.max(required[0],2*(Math.abs(item.position[0])+w/2+.15));
    required[1]=Math.max(required[1],2*(Math.abs(item.position[2])+d/2+.15));
    required[2]=Math.max(required[2],item.position[1]+item.asset.dimensions[1]+.1);
    layout.positions[item.id]=item.position;
  }
  if(required.some((value,index)=>value>layout.room_m[index]+1e-6)){
    const suggested=required.map(value=>Math.ceil(value*10)/10);
    if(suggested.some(value=>value>100))throw new Error('Visual placements exceed supported room bounds');
    if(input.auto_fit_room===false){Object.assign(layout,{fits:false,suggested_room_m:suggested,message:'Proposed visual placements exceed the room. Suggested room: '+suggested.join(' × ')+' m.'});
      await writeFile(resolve(output,'layout-report.json'),JSON.stringify(layout,null,2)+'\n',{flag:'wx'});throw new Error(layout.message);}
    layout.room_m=suggested;layout.room_adjusted=true;
  }
  layout.placements=input.placements??[];
  await writeFile(resolve(output,'layout-report.json'),JSON.stringify(layout,null,2)+'\n',{flag:'wx'});
  const duration=plan.operation_designs.length*seconds;
  let animation={duration,loop:true,tracks:[]};
  const key=(item:any,time:number,position:number[])=>{animation=writeKeyframe(animation,item.id,undefined,{id:`${item.id}-${time}`,time,position,rotation:item.rotation});};
  const segments=plan.operation_designs.map((operation:any,index:number)=>{
    const start=index*seconds,end=(index+1)*seconds,active=items.filter(item=>operation.equipment_ids.includes(item.equipmentId));
    const movers=new Set(active.filter(item=>['actuator','end_effector'].includes(item.category)).map(item=>item.id));
    if(operation.autonomy==='proposed_automated')for(const item of items){
      let current=item,moving=false;while(current){if(movers.has(current.id)){moving=true;break;}current=current.anchorId?byId.get(current.anchorId):null;}
      if(!moving)continue;
      key(item,0,[...item.position]);key(item,start,[...item.position]);
      key(item,start+seconds/2,[item.position[0]+.1,item.position[1],item.position[2]]);
      key(item,end,[...item.position]);key(item,duration,[...item.position]);
    }
    const source=input.protocol_operations.find((op:any)=>op.id===operation.source_operation_id);
    return{operation_id:operation.source_operation_id,label:source?.intent??operation.source_operation_id,
      implementation:operation.implementation,start_s:start,end_s:end,autonomy:operation.autonomy,
      equipment_ids:operation.equipment_ids,instance_ids:active.map(item=>item.id)};
  });
  const manifest=makeManifest({room:layout.room_m,items,animation},true);
  const reopened=hydrateManifest(readManifest(manifest),[]);
  if(reopened.items.some((item:any)=>item.missing)||reopened.items.length!==items.length)throw new Error('Native portable scene lost machine geometry');
  if(reopened.animation.tracks.length!==animation.tracks.length)throw new Error('Native portable scene lost animation');
  const posed=evaluateWorkspace(reopened.items,reopened.animation,seconds/2);
  if(posed.length!==items.length)throw new Error('Native evaluator lost machine instances');
  const preview={room:layout.room_m,duration,segments,inventory,instances:items.map(item=>({id:item.id,name:item.name,equipment_id:item.equipmentId,anchor_instance_id:item.anchorId??null,relation:item.relation??'floor'}))};
  const report={status:'scene_created',engine:'OpenIndustries native WorkspaceViewer + importForm / writeKeyframe / evaluateWorkspace',
    renderer:'OpenIndustries.WorkspaceViewer',portable_roundtrip:true,instances:items.length,
    equipment_lines:plan.equipment.length,animation_tracks:animation.tracks.length,duration_s:duration,
    geometry_basis:'generated_forma_cad_meshes',machine_asset_sha256:assetHashes,physical_validation:false,
    layout,stock_inventory:inventory,
    timing_basis:input.timing_basis,source_proposal_sha256:input.source_proposal_sha256,source_protocol_sha256:input.source_protocol_sha256,
    limitations:['Machine geometry comes from the generated Forma CAD assets, not generic category boxes.',
      'Placement and clearance gaps are planning assumptions; no collision or robot-kinematics validation.',
      'Stocked consumables use a labeled sample by default; full quantities remain in the proposal and cost inputs.',
      'Animation is an illustrative sequence; storyboard timing is independent of the economic cycle-time assumptions.']};
  await writeFile(resolve(output,'scene.oi.json'),JSON.stringify(manifest),{flag:'wx'});
  await writeFile(resolve(output,'preview.json'),JSON.stringify(preview),{flag:'wx'});
  await writeFile(resolve(output,'scene-report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({instances:items.length,native_cad_assets:plan.equipment.length,tracks:animation.tracks.length}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
