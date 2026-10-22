// SPDX-License-Identifier: MPL-2.0
/* Render all model/source content as text, never executable HTML. */
'use strict';
const $ = id => document.getElementById(id);
// Keep only model IDs in browser storage; credentials stay on the server.
const modelFields = ['vision-model', 'model'];
const editedModels = new Set();
let recommendedModels = null;
let analysisProvider = 'nebius', catalogGeneration = 0;
const providerChoices = new Map();
function chooseModel(id, value) {
 if (!value) return;
 const select = $(id);
 if (![...select.options].some(option => option.value === value)) select.add(new Option(value, value));
 select.value = value;
}
function savedModel(id) {
 try { const value = localStorage.getItem(`workbench.${analysisProvider}.${id}`); return value && value.trim() && value.length <= 200 ? value : null; }
 catch { return null; }
}
for (const id of modelFields) {
 const saved = savedModel(id);
  if (saved) chooseModel(id, saved);
 $(id).addEventListener('input', () => {
  editedModels.add(id);
  try {
   const value = $(id).value.trim();
   if (value) localStorage.setItem(`workbench.${analysisProvider}.${id}`, value);
   else localStorage.removeItem(`workbench.${analysisProvider}.${id}`);
  } catch { /* Storage may be unavailable; the current form still works. */ }
 });
}
function applyModelDefaults(config) {
 recommendedModels = config.presets || config;
 $('reset-models').disabled = false;
 for (const id of modelFields) {
  if (!editedModels.has(id) && !savedModel(id)) {
    chooseModel(id, (id === 'model' ? config.model : config.vision_model) || $(id).value);
  }
 }
}
$('reset-models').addEventListener('click', () => {
 if (!recommendedModels) return;
 for (const id of modelFields) {
   chooseModel(id, id === 'model' ? recommendedModels.model : recommendedModels.vision_model);
  editedModels.add(id);
  try { localStorage.setItem(`workbench.nebius.${id}`, $(id).value); } catch { /* Current form still works. */ }
 }
 if (!$('design-model').disabled) $('design-model').value = $('model').value;
});
async function loadAnalysisCatalog() {
 const token = ++catalogGeneration, provider = analysisProvider;
 $('model-catalog-status').textContent = 'Loading account model catalog…';
 $('start').disabled = true;
 for (const id of modelFields) $(id).disabled = true;
 try {
  const catalog = await api(`/api/models/${provider}`);
  if (token !== catalogGeneration) return;
  for (const id of modelFields) {
   const selected = $(id).value;
   $(id).replaceChildren(...catalog.models.map(model => new Option(model, model)));
   chooseModel(id, selected || (catalog.models.includes('openai/gpt-6.1-sol') ? 'openai/gpt-6.1-sol' : catalog.models[0]));
  }
  $('model-catalog-status').textContent = `${catalog.models.length} account-visible models. Choose a vision-capable model for frames; catalog presence does not guarantee vision support.`;
 } catch (error) {
  if (token !== catalogGeneration) return;
  $('model-catalog-status').textContent = `Could not load model catalog: ${error.message}. Current selections are preserved. Switch providers to retry.`;
 } finally {
  if (token === catalogGeneration) {
   for (const id of modelFields) $(id).disabled = !$(id).value;
   $('start').disabled = modelFields.some(id => !$(id).value);
  }
 }
}
$('analysis-provider').addEventListener('change', () => {
 providerChoices.set(analysisProvider, modelFields.map(id => $(id).value));
 analysisProvider = $('analysis-provider').value;
 const choices = providerChoices.get(analysisProvider);
 for (const [index, id] of modelFields.entries()) {
  $(id).replaceChildren();
  chooseModel(id, choices?.[index] || savedModel(id));
 }
 $('reset-models').disabled = analysisProvider !== 'nebius';
 loadAnalysisCatalog();
});
const labels = {queued:'Queued',ingesting_frames:'Sampling frames',extracting_observations:'Extracting observations',extracting_protocol:'Extracting protocol',compiling:'Compiling artifacts',completed:'Completed',failed:'Failed'};
labels.correcting_protocol = 'Correcting protocol citations';
labels.correcting_observations = 'Correcting observation evidence';
let selectedFile = null, objectURL = null, activeRun = null, pollTimer = null, generation = 0;
let sampledRun = null;
let wizardStep = 'video', analysisStarted = false, resultsReady = false;
const wizardSteps = ['video', 'models', 'analysis', 'results', 'autonomy', 'machines', 'scene'];
const stepContext = {
 video:'Start with the human procedure you want to automate.',
 models:'Choose the models that interpret the video and compile its procedure.',
 analysis:'Extract what happened, with actions grounded in the sampled video frames.',
 results:'Review the human workflow and its evidence before proposing a machine.',
 autonomy:'Propose the machine workflow and compare planning costs. Next, generate the actual machine assets with Forma.',
 machines:'Generate and inspect each required machine through Forma before placing it into the scene.',
 scene:'Inspect the machine, play its workflow, and place the assembly in the lab—all in one view.',
};
function showWizardStep(step, focus = true) {
  const available = {video:true, models:Boolean(selectedFile || activeRun), analysis:analysisStarted || Boolean(activeRun), results:resultsReady, autonomy:resultsReady, machines:resultsReady, scene:resultsReady};
 if (!available[step]) return;
 wizardStep = step;
 $('step-context').textContent = stepContext[step];
  if (step !== 'scene' && typeof leaveScene === 'function') leaveScene();
  if (step !== 'scene' && typeof leaveLab === 'function') leaveLab();
 if (step !== 'machines' && typeof pauseMachinePreviews === 'function') pauseMachinePreviews();
 for (const name of wizardSteps) {
  $(`wizard-${name}`).hidden = name !== step;
  $(`step-${name}`).disabled = !available[name];
  $(`step-${name}`).setAttribute('aria-current', name === step ? 'step' : 'false');
 }
 const host = step === 'results' ? 'results-video-host' : step === 'analysis' ? 'analysis-video-host' : 'source-video-host';
 $(host).append($('video-player'));
 if (focus) $(`${step}-heading`).focus();
 if (step === 'autonomy' && typeof loadAutonomy === 'function') loadAutonomy(activeRun, generation);
 if (step === 'scene' && typeof loadScene === 'function') loadScene(activeRun, generation);
  if (step === 'machines' && typeof loadMachines === 'function') loadMachines(activeRun, generation);
  if (step === 'scene' && typeof loadLab === 'function' && $('lab-layout').open) loadLab();
}
function element(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
async function api(url, options) { const response = await fetch(url, options); if (!response.ok) { let detail; try { detail = (await response.json()).detail; } catch { detail = response.statusText; } throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail)); } return response.json(); }
function resetResults() { if(typeof resetAutonomy === 'function') resetAutonomy(); if(typeof resetScene === 'function') resetScene(); if(typeof resetMachines === 'function') resetMachines(); resultsReady = false; $('view-results').hidden = true; $('result-content').hidden = true; $('empty-results').hidden = false; $('evidence').hidden = true; $('run-activity').hidden = true; $('submission-status').hidden = true; $('sampled-preview').hidden = true; sampledRun = null; showError(''); }
function switchVideo(url, name) { $('video').src = url; $('video-empty').hidden = true; $('source-name').textContent = name; $('selected-source').textContent = `Source: ${name}`; $('playback-error').hidden = true; }
function stopPolling() { generation++; clearTimeout(pollTimer); activeRun = null; }
function showStage(job) {
 renderSampledFrames(job);
 const label = labels[job.stage] || job.stage;
 const timing = `${job.elapsed_s ?? 0}s total · ${job.stage_elapsed_s ?? 0}s in this stage`;
 $('stage').textContent = label;
 $('status').textContent = `${label} · ${timing} · ${job.id.slice(0,8)}`;
 $('submission-status').hidden = true;
 if (job.stage === 'queued') $('status').textContent += ` · Queue position ${job.queue_position ?? '?'}`;
 $('status').title = job.progress_message || '';
 $('run-activity').hidden = false;
 $('stage-detail').textContent = job.progress_message || label;
 $('run-models').textContent = `Vision: ${job.vision_model} · Compiler: ${job.model}`;
 $('run-events').replaceChildren(...(job.events || []).map(event => element('li', `+${Math.max(0,event.at-job.created_at).toFixed(1)}s — ${labels[event.stage] || event.stage}`)));
 $('empty-results').hidden = true;
 const stages = [...document.querySelectorAll('#stages li')];
  const current = stages.findIndex(node => node.dataset.stage === (job.stage === 'correcting_protocol' ? 'extracting_protocol' : job.stage === 'correcting_observations' ? 'extracting_observations' : job.stage));
 stages.forEach((node,index) => { node.classList.toggle('done',job.stage === 'completed' || (current >= 0 && index < current)); node.classList.toggle('active',index === current); });
}
function renderSampledFrames(job) {
 const frames = job.sampled_frames || [];
 if (!frames.length || sampledRun === job.id) return;
 sampledRun = job.id;
 $('sampled-preview').hidden = false;
 $('sampled-heading').textContent = `${frames.length} sampled frames · vision input`;
 function selectFrame(frame, index) {
  $('sampled-image').src = frame.url;
  $('sampled-caption').textContent = `Frame ${index+1} of ${frames.length} · ${frame.timestamp_s.toFixed(2)}s · ${frame.id}`;
  for (const button of $('sampled-thumbnails').children) button.setAttribute('aria-pressed', String(button.dataset.frame === frame.id));
 }
 $('sampled-thumbnails').replaceChildren(...frames.map((frame,index) => {
  const button = element('button'); button.type = 'button'; button.dataset.frame = frame.id;
  button.style.cssText = 'flex:0 0 104px;padding:5px;font-size:12px';
  button.setAttribute('aria-label', `Inspect frame ${index+1} at ${frame.timestamp_s.toFixed(2)} seconds`);
  const image = element('img'); image.src = frame.url; image.alt = ''; image.loading = 'lazy';
  image.style.cssText = 'display:block;width:100%;height:60px;object-fit:cover';
  button.append(image,element('span',`${frame.timestamp_s.toFixed(2)}s`));
  button.addEventListener('click',()=>selectFrame(frame,index)); return button;
 }));
 selectFrame(frames[0],0);
}
async function refreshHistory() { const jobs = await api('/api/runs'); const selected = activeRun || ''; $('history').replaceChildren(new Option('Select a previous run','')); jobs.forEach(job => $('history').add(new Option(`${job.filename} · ${labels[job.stage]} · ${job.id.slice(0,8)}`,job.id))); $('history').value = selected; }
function showEvidence(item) { $('results-video-details').open = true; $('video').currentTime = item.timestamp_s; $('video').pause(); $('frame-image').src = item.url; $('frame-caption').textContent = `${item.frame_id} · ${item.timestamp_s.toFixed(2)}s · action ${item.action_id}`; $('evidence').hidden = false; }
function renderResults(data) { const spec = data.protocol; $('empty-results').hidden = true; $('result-content').hidden = false; $('protocol-title').textContent = spec.title; $('boundary').textContent = `${spec.functional_unit} · ${spec.boundary}`; $('provenance').textContent = `${data.summary.live_inference ? 'Live model inference' : 'Recorded / synthetic replay — not live inference'} · Candidate requires semantic review · Not physically validated`;
 $('extraction-counts').textContent = `${spec.operations.length} extracted operations · ${spec.capabilities.length} capability mappings. These describe the source procedure; Step 5 proposes its autonomous implementation.`;
 if (!$('design-model').value) $('design-model').value = $('model').value || data.job.model;
 $('operations').replaceChildren(); spec.operations.forEach((op,index) => { const card = element('article',undefined,'operation'); card.append(element('span',op.basis.replaceAll('_',' '),'basis'),element('h4',`${String(index+1).padStart(2,'0')} / ${op.intent}`),element('p',op.physical_operation)); if(op.constraints.length) card.append(element('p',`Constraints: ${op.constraints.join('; ')}`)); op.evidence.forEach(item => { const button=element('button',`↗ ${item.timestamp_s.toFixed(2)}s · ${item.frame_id}`,'evidence-link'); button.type='button';button.addEventListener('click',()=>showEvidence(item));card.append(button); }); if(!op.evidence.length) card.append(element('p',`No observed frame evidence: ${op.source_refs.join('; ')}`)); $('operations').append(card); });
 $('apparatus').replaceChildren(element('p','Candidate equipment is a design hypothesis requiring engineering review.')); spec.capabilities.forEach(cap=>{const card=element('article',undefined,'capability');card.append(element('h4',cap.name),element('p',cap.candidate_equipment.join(' · ')),element('p',cap.rationale),element('p',`Operations: ${cap.operation_ids.join(', ')}`));$('apparatus').append(card);});
 const apparatusDetails=element('details');apparatusDetails.append(element('summary','Full apparatus requirements'),element('pre',JSON.stringify(data.apparatus,null,2)));$('apparatus').append(apparatusDetails);
 const graphDetails=element('details');graphDetails.append(element('summary','Compiled process graph'),element('pre',JSON.stringify(data.process_graph,null,2)));$('operations').append(graphDetails);
 $('resources').replaceChildren(element('p','Unknown values are not zero. Supply sourced measurements before estimating performance.'));const table=element('table'),head=element('tr');['Resource','Value','Unit','Basis'].forEach(text=>head.append(element('th',text)));table.append(head);Object.entries(spec.resource_inputs).forEach(([name,value])=>{const row=element('tr');[name,value.value===null?'Unknown':String(value.value),value.unit,value.basis].forEach(text=>row.append(element('td',text)));table.append(row);});$('resources').append(table);const template=element('details');template.append(element('summary','Resource-input template'),element('pre',JSON.stringify(data.resource_template,null,2)));$('resources').append(template);
 $('report-text').textContent=data.report;$('limitations').replaceChildren(...spec.limitations.map(text=>element('li',text)));$('downloads').replaceChildren();const bundle=element('a','Download evidence bundle (includes source video)','bundle');bundle.href=`/api/runs/${activeRun}/bundle`;$('downloads').append(bundle);data.downloads.forEach(name=>{const link=element('a',name);link.href=`/api/runs/${activeRun}/artifacts/${name}`;$('downloads').append(link);});
 resultsReady = true;
 $('view-results').hidden = false;
 showWizardStep(wizardStep === 'analysis' ? 'results' : wizardStep);
}
async function poll(runId, token) { if(token!==generation)return;try { const job=await api(`/api/runs/${runId}`);if(token!==generation)return;showStage(job);if(job.stage==='completed'){const data=await api(`/api/runs/${runId}/results`);if(token!==generation)return;renderResults(data);}else if(job.stage==='failed'){showError(`${job.error}${job.error_type ? ` (${job.error_type})` : ''}`);}await refreshHistory();if(token!==generation)return;if(!['completed','failed'].includes(job.stage)){pollTimer=setTimeout(()=>poll(runId,token),1000);}}catch(error){if(token!==generation)return;showError(`Could not refresh run: ${error.message}. Reopen it from saved runs to reconnect.`);}}
function restoreSnapshotChoices(job){
 analysisProvider=job.provider==='gmi'?'gmi':'nebius';$('analysis-provider').value=analysisProvider;
 for(const [id,value] of [['model',job.model],['vision-model',job.vision_model]]){chooseModel(id,value);editedModels.add(id);}
 $('frame-count').value=String(job.frame_count);$('design-model').value=job.model;
 $('reset-models').disabled=analysisProvider!=='nebius';
 $('model-catalog-status').textContent=`Restored run models · vision provider: ${job.vision_provider||job.provider}. Saved results loaded without inference.`;
}
async function openRun(runId) { stopPolling();activeRun=runId;const token=generation;resetResults();location.hash=runId;showWizardStep('analysis');try{const job=await api(`/api/runs/${runId}`);if(token!==generation)return;if(job.imported_snapshot)restoreSnapshotChoices(job);switchVideo(`/api/runs/${runId}/video`,job.filename);await poll(runId,token);}catch(error){if(token===generation)showError(error.message);}}
$('file').addEventListener('change',()=>{stopPolling();analysisStarted=false;resetResults();selectedFile=$('file').files[0]||null;location.hash='';if(objectURL)URL.revokeObjectURL(objectURL);if(selectedFile){objectURL=URL.createObjectURL(selectedFile);switchVideo(objectURL,selectedFile.name);$('stage').textContent='Ready';$('status').textContent='Ready to analyze selected video.';document.querySelectorAll('#stages li').forEach(n=>n.classList.remove('done','active'));}showWizardStep('video');});
$('video').addEventListener('error',()=>{$('playback-error').hidden=false;});
$('run-form').addEventListener('submit',async event=>{event.preventDefault();if(!selectedFile){showWizardStep('video');showError('Choose a video first.');return;}if(selectedFile.size>100*1024*1024){showError('Video exceeds the 100 MiB limit.');return;}stopPolling();resetResults();analysisStarted=true;showWizardStep('analysis');$('start').disabled=true;$('file').disabled=true;$('history').disabled=true;$('status').textContent='Uploading video…';$('submission-status').hidden=false;$('submission-status').textContent='Uploading video to the backend. Analysis will start after the upload finishes.';const query=new URLSearchParams({filename:selectedFile.name,provider:analysisProvider,model:$('model').value.trim(),vision_model:$('vision-model').value.trim(),frame_count:$('frame-count').value});try{const job=await api(`/api/runs?${query}`,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Workbench-Request':'1'},body:selectedFile});await openRun(job.id);await refreshHistory();}catch(error){showError(error.message);$('status').textContent='Run was not started.';$('submission-status').textContent=`Run was not started: ${error.message}`;}finally{$('start').disabled=false;$('file').disabled=false;$('history').disabled=false;}});
$('history').addEventListener('change',()=>{if($('history').value){selectedFile=null;$('file').value='';openRun($('history').value);}});
async function importSnapshot(file=null){
 $('snapshot-import').disabled=true;$('snapshot-file').disabled=true;$('snapshot-status').textContent='Verifying and restoring saved artifacts…';
 try{
  const result=await api(file?'/api/snapshots/upload':'/api/snapshots/import',{method:'POST',headers:{'X-Workbench-Request':'1','Content-Type':file?'application/zip':'application/json'},body:file||JSON.stringify({path:$('snapshot-path').value})});
  selectedFile=null;$('file').value='';await refreshHistory();await openRun(result.id);
  const job=await api(`/api/runs/${result.id}`);
  restoreSnapshotChoices(job);
  $('snapshot-status').textContent=`Imported ${result.imported_files} files. All available saved stages are loaded.`;
  showWizardStep(job.stage==='completed'?'results':'analysis');
 }catch(error){$('snapshot-status').textContent=`Import failed: ${error.message}`;}
 finally{$('snapshot-import').disabled=false;$('snapshot-file').disabled=false;}
}
$('snapshot-import').addEventListener('click',()=>importSnapshot());
$('snapshot-file').addEventListener('change',()=>{const file=$('snapshot-file').files[0];if(file)importSnapshot(file);});
for(const button of document.querySelectorAll('[data-view]'))button.addEventListener('click',()=>{document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));document.querySelectorAll('.view').forEach(view=>view.hidden=view.id!==button.dataset.view);});
for (const step of wizardSteps) $(`step-${step}`).addEventListener('click',()=>showWizardStep(step));
$('configure-next').addEventListener('click',()=>{
 if(activeRun&&!selectedFile){showWizardStep('models');return;}
 if (!selectedFile) { showError('Choose a video first.'); return; }
 if (selectedFile.size > 100*1024*1024) { showError('Video exceeds the 100 MiB limit.'); return; }
 showError(''); showWizardStep('models');
});
$('models-back').addEventListener('click',()=>showWizardStep('video'));
$('analysis-back').addEventListener('click',()=>showWizardStep('models'));
$('view-results').addEventListener('click',()=>showWizardStep('results'));
$('new-video').addEventListener('click',()=>showWizardStep('video'));
$('design-next').addEventListener('click',()=>showWizardStep('autonomy'));
$('design-back').addEventListener('click',()=>showWizardStep('results'));
$('scene-next').addEventListener('click',()=>showWizardStep('machines'));
$('scene-back').addEventListener('click',()=>showWizardStep('machines'));
showWizardStep('video',false);
(async()=>{try{const config=await api('/api/config');applyModelDefaults(config);loadAnalysisCatalog();$('readiness').textContent=!config.ffmpeg_available?'Server needs ffmpeg and ffprobe.':'Provider credentials stay on the server.';await refreshHistory();const id=location.hash.slice(1);if(/^[a-f0-9]{32}$/.test(id))await openRun(id);}catch(error){showError(error.message);}})();

