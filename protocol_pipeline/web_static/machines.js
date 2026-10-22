// SPDX-License-Identifier: MPL-2.0
/* Step 6 tracks each actual Forma generation and keeps failures visible. */
'use strict';
let machinesTimer=null,machinesEpoch=0,machinesState=null;
const machineProviderModels=new Map();let previousMachineProvider='nebius';
$('machine-provider').addEventListener('change',()=>{
 machineProviderModels.set(previousMachineProvider,$('machine-model').value);
 const provider=$('machine-provider').value;
 $('machine-model').value=machineProviderModels.get(provider)||(provider==='gmi'?'openai/gpt-6.1-sol':$('design-model').value||$('model').value);
 previousMachineProvider=provider;
});
function resetMachines(){if(typeof resetMachinePreviews==='function')resetMachinePreviews();clearTimeout(machinesTimer);machinesEpoch++;machinesState=null;$('machine-list').replaceChildren();$('machines-error').hidden=true;}
async function loadMachines(runId,token){
 if(!runId||token!==generation)return;clearTimeout(machinesTimer);const epoch=++machinesEpoch;
 try{const state=await api(`/api/runs/${runId}/machines`);if(epoch!==machinesEpoch||token!==generation||runId!==activeRun)return;
  $('machines-error').hidden=true;machinesState=state;renderMachines(state);if(state.stage==='generating')machinesTimer=setTimeout(()=>loadMachines(runId,token),1000);
 }catch(error){if(epoch!==machinesEpoch||token!==generation||runId!==activeRun)return;$('machines-error').textContent=`Could not refresh machine status: ${error.message}. Retrying in 3 seconds; generation may still be running.`;$('machines-error').hidden=false;machinesTimer=setTimeout(()=>loadMachines(runId,token),3000);}
}
function renderMachines(state){
 $('machines-runtime').textContent=state.runtime.message;
 if(!$('machine-model').value)$('machine-model').value=$('design-model').value||state.model||$('model').value;
 const ready=state.machines.filter(row=>row.stage==='completed').length;
 $('machines-status').textContent=state.stage==='needs_design'?state.message:`${ready}/${state.machines.length} Forma CAD assets ready. Each machine is generated independently; existing assets are reused.`;
 $('machines-generate-all').disabled=state.stage==='needs_design'||state.stage==='generating'||!state.runtime.available||state.stage==='ready';
 $('machines-to-scene').disabled=state.stage!=='ready';
 const list=$('machine-list'),existing=new Map([...list.children].map(card=>[card.dataset.machineKey,card]));
 const cards=state.machines.map(row=>{
  const signature=JSON.stringify([row.stage,row.attempt_id,row.name,row.role,row.quantity,row.error,row.report,row.preview?.cache_key,row.preview?.ready]);
  const old=existing.get(row.key);
  if(['completed','needs_refinement'].includes(row.stage)&&old?.dataset.signature===signature){observeMachinePreview(old);return old;}
  const card=element('article',undefined,'machine-card'),header=element('div',undefined,'overview-heading');
  card.dataset.machineKey=row.key;card.dataset.signature=signature;
  header.append(element('h3',row.name),element('span',`${row.quantity} required · ${row.category}`,'concept-badge'));
  const body=element('div',undefined,'machine-card-body'),details=element('div',undefined,'machine-card-details');
  body.append(machinePreviewCard(row),details);card.append(header,body);details.append(element('p',row.role));
  const providerName=row.provider==='gmi'?'GMI Cloud':'Nebius';
  const runtime=row.authoring==='opencode'?`OpenCode → ${providerName}`:`Forma → ${providerName}`;
  const status=row.progress?`${runtime} · ${row.progress.label} (${row.progress.status}) · ${row.elapsed_s}s${row.progress.session_id?` · ${row.progress.session_id}`:''}`:`${runtime} · ${row.stage.replaceAll('_',' ')}${row.elapsed_s!==undefined?` · ${row.elapsed_s}s`:''}`;
  details.append(element('p',status,'notice'));
  if(row.error)details.append(element('pre',row.error,'error'));
  if(row.report){details.append(element('p',row.report.authoring==='opencode'
   ? `OpenCode session ${row.report.opencode_session_id} · ${row.report.machine_specific_cad.parts} CAD parts · Forma schema and CAD export validated · electrical design not evaluated`
   : `Forma ${row.report.core_version} · ${row.report.machine_specific_cad?.parts || 0} machine CAD parts · ${row.report.components} hardware components · ${row.report.deterministic_is_valid?'deterministic checks passed':'validation findings require review'}`,'hint'));
    const link=element('a','Download generated Forma project →');link.href=row.artifact_url;details.append(link);
  }
  const button=element('button',row.stage==='completed'?'Regenerate machine':'Generate machine');button.type='button';
  button.disabled=['queued','generating'].includes(row.stage)||!state.runtime.available;
   button.addEventListener('click',()=>startMachines(row.key,row.stage==='completed'));details.append(button);return card;
  });
 const keep=new Set(cards);
 for(const old of [...list.children])if(!keep.has(old)){detachMachinePreview(old);old.remove();}
 cards.forEach((card,index)=>{if(list.children[index]!==card)list.insertBefore(card,list.children[index]||null);});
}
async function startMachines(key=null,regenerate=false){
 if(!activeRun)return;const runId=activeRun,token=generation,epoch=++machinesEpoch;clearTimeout(machinesTimer);
 const model=$('machine-model').value.trim();if(!model){$('machines-error').textContent='Choose a Forma model first.';$('machines-error').hidden=false;return;}
 $('machines-error').hidden=true;$('machines-generate-all').disabled=true;
 try{const state=await api(`/api/runs/${runId}/machines${key?`/${key}?regenerate=${regenerate}`:''}`,{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Request':'1'},body:JSON.stringify({model,authoring:$('machine-authoring').value,provider:$('machine-provider').value})});
  if(epoch!==machinesEpoch||token!==generation||runId!==activeRun)return;machinesState=state;renderMachines(state);loadMachines(runId,token);
 }catch(error){if(epoch!==machinesEpoch||token!==generation)return;$('machines-error').textContent=error.message;$('machines-error').hidden=false;$('machines-generate-all').disabled=false;}
}
$('machines-generate-all').addEventListener('click',()=>startMachines());
$('machines-back').addEventListener('click',()=>showWizardStep('autonomy'));
$('machines-to-scene').addEventListener('click',()=>showWizardStep('scene'));
