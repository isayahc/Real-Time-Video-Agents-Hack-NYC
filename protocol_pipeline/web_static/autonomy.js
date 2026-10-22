// SPDX-License-Identifier: MPL-2.0
/* Step 5 owns a separate proposal and assumed economics; extracted evidence stays intact. */
'use strict';
let designTimer = null, designRun = null, designEpoch = 0, designState = null;

function resetAutonomy() {
 clearTimeout(designTimer); designEpoch++; designRun = null; designState = null;
 $('design-content').hidden = true; $('design-error').hidden = true;
 $('design-start').disabled = false; $('design-start').textContent = 'Generate autonomous design ↗';
 $('design-model').disabled = false; $('save-design-costs').disabled = false;
 $('design-controls').hidden = false;
 $('design-status').textContent = 'Ready. Generation makes a separate model request using the saved extraction.';
}

async function loadAutonomy(runId, token) {
 if (!runId || token !== generation) return;
 if (designRun === runId && designState?.stage === 'completed') {loadSystemMetrics(runId,token);return;}
 clearTimeout(designTimer);
 designRun = runId;
 const epoch = ++designEpoch;
 try {
  const state = await api(`/api/runs/${runId}/autonomy`);
  if (epoch !== designEpoch || token !== generation || runId !== activeRun) return;
  renderDesignState(state);
  if(state.stage==='completed')loadSystemMetrics(runId,token);
  if (['queued','designing'].includes(state.stage)) designTimer = setTimeout(()=>loadAutonomy(runId,token),1000);
 } catch (error) {
  if (epoch !== designEpoch || token !== generation) return;
  $('design-error').textContent = error.message; $('design-error').hidden = false;
  $('design-start').disabled = false;
 }
}

function renderDesignState(state) {
 designState = state;
 const busy = ['queued','designing'].includes(state.stage);
 $('design-start').disabled = busy;
 $('design-model').disabled = busy;
 $('design-error').hidden = state.stage !== 'failed';
 $('design-controls').hidden = state.stage === 'completed';
 $('design-status').textContent = {
  not_started:'Ready. Generate a separate hardware proposal and model-estimated cost scenario from the saved procedure.',
  queued:`Queued for the model worker · ${state.elapsed_s || 0}s. The original extraction remains saved.`,
  designing:`Designing machine workflow and estimating planning costs with ${state.model} · ${state.elapsed_s || 0}s.`,
  completed:'Design proposal ready. All prices and performance figures below are editable planning assumptions.',
  failed:'Design generation failed. Your extraction results are still available in Step 4.',
 }[state.stage] || state.stage;
 if(state.stage === 'failed') {
  $('design-error').textContent=state.error;
  $('design-start').textContent='Retry autonomous design ↗';
 }
 if(state.stage === 'completed') renderDesign(state);
}

function renderDesign(state) {
 const proposal=state.design.proposal, equipment=new Map(proposal.equipment.map(item=>[item.id,item]));
 $('design-content').hidden=false;
 $('design-title').textContent=proposal.title; $('design-overview').textContent=proposal.overview;
 const integrated=proposal.design_scope==='integrated_workcell';
 $('machine-requirements-panel').hidden=!integrated;
 $('machine-requirements').replaceChildren(...(proposal.machine_requirements||[]).map(requirement=>{
  const row=element('article',undefined,'operation');row.append(element('h4',requirement.id),element('p',requirement.description),element('p',`Verify: ${requirement.verification_needed}`),element('small',`Source: ${requirement.source_refs.join(' · ')}`));
  if(requirement.unknowns.length)row.append(element('p',`Constraints / unknowns: ${requirement.unknowns.join(' · ')}`,'hint'));return row;
 }));
 $('component-bom').replaceChildren(...(proposal.component_bill_of_materials||[]).map(item=>element('p',`${item.quantity} × ${item.name}: ${item.unit_cost_usd.value===null?'Unknown':`$${item.unit_cost_usd.value}`} — ${item.unit_cost_usd.rationale}`)));
 const mapped=proposal.operation_designs.filter(op=>op.autonomy==='proposed_automated').length;
 const gaps=proposal.operation_designs.length-mapped;
 const humanInside=proposal.remaining_human_tasks.some(task=>task.within_process_boundary);
 $('autonomy-level').textContent=gaps || humanInside ? 'Partial-autonomy concept · human tasks remain' : 'Full-autonomy target · unverified';
 $('autonomy-stats').replaceChildren(...[
  [`${mapped}/${proposal.operation_designs.length}`,'Proposed automated operations'],
   [String(proposal.equipment.length),integrated?'Integrated machine':'Legacy equipment assets'],
  [String(proposal.remaining_human_tasks.length),'Remaining human tasks'],
 ].map(([value,label])=>{const node=element('article');node.append(element('strong',value),element('span',label));return node;}));
 $('autonomy-flow').replaceChildren(...proposal.operation_designs.map((op,index)=>{
  const node=element('article',undefined,'system-operation');
  node.append(element('span',String(index+1).padStart(2,'0'),'system-index'),element('h4',op.source_operation_id),
   element('p',op.implementation),element('p',op.equipment_ids.map(id=>equipment.get(id)?.name || id).join(' · ')),
   element('small',op.autonomy.replaceAll('_',' ')),element('p',`Verify: ${op.verification_needed}`));
  return node;
 }));
 $('autonomy-human-tasks').replaceChildren(...proposal.remaining_human_tasks.map(task=>element('li',`${task.task} · ${task.frequency.replaceAll('_',' ')} · ${task.within_process_boundary?'within':'outside'} process boundary`)));
 if(!proposal.remaining_human_tasks.length) $('autonomy-human-tasks').append(element('li','No human tasks proposed; completeness requires review.'));
 $('autonomy-assumptions').replaceChildren(...proposal.assumptions.map(text=>element('li',text)));
 $('design-limitations').replaceChildren(...proposal.limitations.map(text=>element('li',text)));
 $('design-provenance').textContent=`${state.design.provider} · ${state.design.live_inference?'Live model design proposal':'Recorded fixture / replay'} · Source protocol SHA-256: ${state.design.source_protocol_sha256}`;
 $('design-export').href=`/api/runs/${activeRun}/autonomy/export`;
 renderDesignEconomics(state.economics,proposal);
}

function renderDesignEconomics(economics,proposal) {
 const scoped=$('cost-view').value==='processing'&&economics.processing_only;
 const metrics=scoped?economics.processing_only.metrics:economics.comparison.base.metrics;
 $('cost-metrics').replaceChildren(...[
   ['Estimated deployment','candidate.upfront_total'],
   [scoped?'Manual processing / output':'Manual cost / accepted output','baseline.variable_unit_cost'],
   [scoped?'Machine processing / output':'Autonomous cost / accepted output','candidate.variable_unit_cost'],
   [scoped?'Annual processing saving':'Modeled annual savings','annual_operating_saving'],
   [scoped?'Conditional payback':'Simple payback','simple_payback_years'],
  ['Autonomous annual capacity','candidate.annual_capacity'],
 ].map(([label,key])=>{
  const metric=metrics[key],node=element('article',undefined,'cost-metric');
   const value=metric.value == null ? (metric.status==='undefined'?'No payback / undefined':'Unknown') : new Intl.NumberFormat(undefined,{maximumFractionDigits:key.includes('unit_cost')?4:2}).format(metric.value);
  node.append(element('h4',label),element('strong',value),element('span',metric.unit),element('p',metric.reason || 'Calculated from planning assumptions'));
  return node;
 }));
  $('cost-scope').textContent=scoped?economics.processing_only.scope:economics.scope;
  $('cost-issues').replaceChildren(...(scoped?economics.processing_only.warnings:economics.comparison.base.issues).map(text=>element('li',text)));
  const processing=economics.processing_only;
  if(processing){
   function table(headers,rows){const node=element('table'),head=element('tr');headers.forEach(v=>head.append(element('th',v)));node.append(head);rows.forEach(values=>{const row=element('tr');values.forEach(v=>row.append(element('td',v)));node.append(row);});return node;}
   const money=value=>value==null?'Unknown':`$${value.toFixed(4)}`;
   $('cost-breakdown').replaceChildren(table(['Per output · materials excluded','Manual','Machine'],[['Labor',money(processing.breakdown.manual.labor_usd),money(processing.breakdown.autonomous.labor_usd)],['Electricity',money(processing.breakdown.manual.electricity_usd),money(processing.breakdown.autonomous.electricity_usd)],['Consumables',money(processing.breakdown.manual.consumables_usd),money(processing.breakdown.autonomous.consumables_usd)]]));
   const value=key=>economics.fields[key]?.value??'Unknown';
   $('operating-assumptions-summary').textContent=`Saved assumptions: manual cycle ${value('manual.cycle_seconds_per_output')}s / labor ${value('manual.labor_seconds_per_output')}s; machine cycle ${value('autonomous.cycle_seconds_per_output')}s / labor ${value('autonomous.labor_seconds_per_output')}s. These are not the demo animation timing. Annual demand: ${value('annual_volume')}; labor rate: $${value('labor_rate_usd_per_hour')}/h.`;
   $('cost-sensitivity').replaceChildren(table(['Outputs / year','Annual saving','Payback','Capacity'],processing.sensitivity.map(row=>[row.annual_outputs.toLocaleString(),row.annual_saving_usd===null?'Unknown':`$${row.annual_saving_usd.toFixed(2)}`,row.payback_years===null?'No positive payback / unknown':`${row.payback_years.toFixed(1)} years`,row.within_modeled_capacity===null?'Unknown':row.within_modeled_capacity?'Within assumed capacity':'Exceeds assumed capacity'])));
   $('cost-missing-inputs').replaceChildren(...processing.missing_inputs.map(row=>element('li',`${row.label}: ${row.rationale}`)));
  }
 function input(path) {
  const field=economics.fields[path],node=element('input'); node.type='number'; node.min='0';node.step='any';
  node.dataset.costPath=path;node.dataset.original=field.original_value == null ? '' : String(field.original_value);
  node.value=field.value == null?'':String(field.value);node.placeholder='Unknown';
  node.setAttribute('aria-label',field.label); return node;
 }
 const table=element('table'),header=element('tr');
 ['Equipment / role','Qty','Unit estimate (USD)','Assumption'].forEach(text=>header.append(element('th',text)));table.append(header);
 for(const item of proposal.equipment) {
  const row=element('tr'),description=element('td'),price=element('td');
  description.append(element('strong',item.name),element('p',item.role));price.append(input(`equipment.${item.id}.unit_cost_usd`));
  row.append(description,element('td',String(item.quantity)),price,element('td',item.unit_cost_usd.rationale));table.append(row);
 }
 $('design-equipment').replaceChildren(table);
 $('design-cost-fields').replaceChildren(...Object.entries(economics.fields).filter(([path])=>!path.startsWith('equipment.')).map(([path,field])=>{
  const label=element('label',`${field.label} (${field.unit})`);label.append(input(path),element('small',`${field.basis.replaceAll('_',' ')} · ${field.rationale}`));return label;
 }));
}

async function loadSystemMetrics(runId,token){
 try{const data=await api(`/api/runs/${runId}/system-metrics`);if(runId!==activeRun||token!==generation)return;
  $('system-metrics-note').textContent=data.note;
  $('system-metrics').replaceChildren(...data.cards.map(metric=>{const node=element('article',undefined,'cost-metric');node.append(element('h4',metric.label),element('strong',String(metric.value)),element('span',`${metric.unit} · ${metric.basis}`),element('p',metric.detail));return node;}));
 }catch(error){if(runId===activeRun&&token===generation)$('system-metrics-note').textContent=`Could not load artifact facts: ${error.message}`;}
}
$('cost-view').addEventListener('change',()=>{if(designState?.economics)renderDesignEconomics(designState.economics,designState.design.proposal);});

$('design-start').addEventListener('click',async()=>{
 if(!activeRun || !resultsReady) return;
 const runId=activeRun,token=generation,epoch=++designEpoch;
 clearTimeout(designTimer);
 const model=$('design-model').value.trim();
 if(!model){$('design-error').textContent='Choose a design model first.';$('design-error').hidden=false;return;}
 $('design-start').disabled=true;$('design-error').hidden=true;
 $('design-status').textContent='Submitting autonomous-design request…';
 try{
  const state=await api(`/api/runs/${runId}/autonomy?${new URLSearchParams({model,retry:String(designState?.stage==='failed')})}`,{method:'POST',headers:{'X-Workbench-Request':'1'}});
  if(token!==generation || epoch!==designEpoch || runId!==activeRun)return;
  renderDesignState(state);loadAutonomy(runId,token);
 }catch(error){if(token!==generation || epoch!==designEpoch)return;$('design-error').textContent=error.message;$('design-error').hidden=false;$('design-start').disabled=false;}
});

$('design-cost-form').addEventListener('submit',async event=>{
 event.preventDefault();if(!activeRun || designState?.stage!=='completed')return;
 const values={};
 for(const input of document.querySelectorAll('[data-cost-path]')) {
  const value=input.value.trim()===''?null:Number(input.value);
  const original=input.dataset.original===''?null:Number(input.dataset.original);
  if(value!==null && (!Number.isFinite(value) || value<0))return;
  if(value!==original)values[input.dataset.costPath]=value;
 }
 const runId=activeRun,token=generation;
 $('save-design-costs').disabled=true;$('cost-save-status').textContent='Saving assumptions and recalculating…';
 try{
  const economics=await api(`/api/runs/${runId}/autonomy/costs`,{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Request':'1'},body:JSON.stringify({values})});
  if(token!==generation || runId!==activeRun)return;
  designState.economics=economics;renderDesignEconomics(economics,designState.design.proposal);
  $('cost-save-status').textContent='Saved. Costs recalculated from your assumptions.';
 }catch(error){if(token===generation)$('cost-save-status').textContent=`Could not save: ${error.message}`;}
 finally{if(token===generation)$('save-design-costs').disabled=false;}
});
