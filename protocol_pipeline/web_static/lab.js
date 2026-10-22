// SPDX-License-Identifier: MPL-2.0
'use strict';
let labRenderer=null,labEpoch=0;
function drawLabMap(report){
 const map=$('lab-map');map.replaceChildren();
 function svg(tag,attributes,text){const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attributes))node.setAttribute(key,String(value));if(text)node.textContent=text;map.append(node);return node;}
 svg('rect',{x:0,y:0,width:800,height:600,fill:'#f5f7f0',stroke:'#183c36','stroke-width':3});
 const aisle=report.template.aisle;
 for(const zone of [aisle,...report.template.zones]){const [x0,z0,x1,z1]=zone.bounds_xz;
  svg('rect',{x:(x0+4)*100,y:(z0+3)*100,width:(x1-x0)*100,height:(z1-z0)*100,fill:zone===aisle?'#e8edc8':'#dce8ee',stroke:'#698580','stroke-dasharray':zone===aisle?'8 6':'0'});
  svg('text',{x:(x0+4)*100+6,y:(z0+3)*100+18,'font-size':12,fill:'#183c36'},zone.name);
 }
 report.placements.forEach((row,index)=>{
  if(row.status!=='placed')return;
  const [x,,z]=row.position_m,[w,d]=row.footprint_m;
  const box=svg('rect',{x:(x+4-w/2)*100,y:(z+3-d/2)*100,width:w*100,height:d*100,fill:'#8fae65',stroke:'#183c36'});
  const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=row.name;box.append(title);
  svg('text',{x:(x+4)*100,y:(z+3)*100,'font-size':12,'text-anchor':'middle',fill:'#102820'},String(index+1));
 });
}
function leaveLab(){labEpoch++;labRenderer?.dispose();labRenderer=null;$('lab-content').hidden=true;}
async function loadLab(build=false){
 const run=activeRun,token=generation;leaveLab();const epoch=labEpoch;
 if(!run)return;
 $('lab-build').disabled=true;$('lab-error').hidden=true;$('lab-status').textContent=build?'Mapping roles, operation relationships and CAD bounds…':'Loading lab layout…';
 const current=()=>epoch===labEpoch&&run===activeRun&&token===generation&&wizardStep==='lab';
 try{
  const report=await api(`/api/runs/${run}/lab`,build?{method:'POST',headers:{'X-Workbench-Request':'1'}}:undefined);
  if(!current())return;
  if(['not_started','stale'].includes(report.status)){$('lab-status').textContent=report.status==='stale'?'Source scene changed. Rebuild the lab layout.':'Ready to map the generated subsystems into the fixed lab.';return;}
  const [manifest,viewer]=await Promise.all([api(`/api/runs/${run}/lab/artifacts/scene.oi.json`),loadNativeViewer()]);
  if(!current())return;
  $('lab-content').hidden=false;labRenderer=viewer.mount($('lab-viewer'),manifest);
  drawLabMap(report);
  $('lab-status').textContent=`${report.placed_count}/${report.total_count} subsystem instances placed · ${report.template.name} · ${report.issues.length} unresolved requirements`;
  $('lab-placements').replaceChildren(...report.placements.map((row,index)=>{
   const card=element('article',undefined,'operation');card.append(element('h4',`${index+1}. ${row.name}`),element('p',`${row.status==='placed'?report.template.zones.find(z=>z.id===row.zone).name:'UNPLACED'} · ${row.dimensions_m.map(v=>v.toFixed(2)).join(' × ')} m`),element('p',row.role),element('p',row.rationale),element('p',`Operations: ${row.operation_ids.join(', ')||'None supplied'} · Related equipment: ${row.related_equipment_ids.join(', ')||'None supplied'}`,'hint'));
   if(row.status==='placed'){const button=element('button','Focus subsystem');button.type='button';button.addEventListener('click',()=>labRenderer?.focusInstance(row.instance_id));card.append(button);}return card;
  }));
  $('lab-issues').replaceChildren(...report.issues.map(text=>element('li',text)));
  $('lab-limitations').replaceChildren(...report.limitations.map(text=>element('li',text)));
  $('lab-download').href=`/api/runs/${run}/lab/artifacts/scene.oi.json`;$('lab-report-download').href=`/api/runs/${run}/lab/artifacts/report.json`;
 }catch(error){if(current()){$('lab-error').textContent=error.message;$('lab-error').hidden=false;$('lab-status').textContent='Lab layout is not ready.';}}
 finally{if(current())$('lab-build').disabled=false;}
}
$('lab-next').addEventListener('click',()=>showWizardStep('lab'));
$('lab-back').addEventListener('click',()=>showWizardStep('scene'));
$('lab-build').addEventListener('click',()=>loadLab(true));
$('lab-viewer').addEventListener('openindustries-error',event=>{$('lab-error').textContent=event.detail;$('lab-error').hidden=false;});
