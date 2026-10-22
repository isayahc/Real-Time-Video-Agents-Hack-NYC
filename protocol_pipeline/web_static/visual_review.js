// SPDX-License-Identifier: MPL-2.0
/* Vision judges native renders; corrections preserve previous CAD and scene versions. */
'use strict';
let reviewTimer=null,reviewEpoch=0,reviewState=null,reviewCaptureBusy=false,reviewCaptureFailed=false,reviewSeen=null;
const reviewProviderModels=new Map();let previousReviewProvider='nebius';
$('review-cad-provider').addEventListener('change',()=>{
 reviewProviderModels.set(previousReviewProvider,$('review-cad-model').value);const provider=$('review-cad-provider').value;
 $('review-cad-model').value=reviewProviderModels.get(provider)||(provider==='gmi'?'openai/gpt-6.1-sol':$('model').value);previousReviewProvider=provider;
});
const reviewActive=['reviewing_before','correcting_cad','building_candidate','awaiting_after_capture','reviewing_after'];
function resetVisualReview(){clearTimeout(reviewTimer);reviewEpoch++;reviewState=null;reviewCaptureBusy=false;reviewCaptureFailed=false;reviewSeen=null;$('visual-review-panel').hidden=true;$('review-result').hidden=true;$('review-error').hidden=true;}

async function loadVisualReview(runId,token){
 if(!runId||token!==generation)return;clearTimeout(reviewTimer);const epoch=++reviewEpoch;
 if(!$('review-vision-model').value)$('review-vision-model').value=$('vision-model').value;
 if(!$('review-cad-model').value){$('review-cad-provider').value=$('machine-provider').value;previousReviewProvider=$('machine-provider').value;$('review-cad-model').value=$('machine-model').value||$('model').value;}
 try{
  const state=await api(`/api/runs/${runId}/visual-review`);
  if(epoch!==reviewEpoch||token!==generation||runId!==activeRun)return;
  reviewState=state;renderVisualReview(state);
  if(state.stage==='awaiting_after_capture'&&!reviewCaptureBusy&&!reviewCaptureFailed){await captureReviewAfter(runId,token,state);return;}
  const version=`${state.id}:${state.stage}`;
  if(['applied','rolled_back'].includes(state.stage)&&reviewSeen!==version){
   reviewSeen=version;if(wizardStep==='scene'){leaveScene();loadScene(runId,token);}
  }
  if(reviewActive.includes(state.stage)&&!reviewCaptureFailed)reviewTimer=setTimeout(()=>loadVisualReview(runId,token),1000);
 }catch(error){if(epoch!==reviewEpoch||token!==generation)return;$('review-error').textContent=error.message;$('review-error').hidden=false;$('review-start').disabled=false;}
}

function renderVisualReview(state){
 $('visual-review-panel').dataset.stage=state.stage;
 const busy=reviewActive.includes(state.stage)||reviewCaptureBusy;
 $('review-start').disabled=busy;
 $('review-status').textContent=state.stage==='not_started'?'Ready to capture and review the actual native scene.':`${state.message||state.stage} · ${state.elapsed_s||0}s`;
 $('review-error').hidden=!state.error;
 if(state.error)$('review-error').textContent=state.error;
 $('review-rollback').hidden=state.stage!=='applied';
 $('review-resume-capture').hidden=!(state.stage==='awaiting_after_capture'&&reviewCaptureFailed);
 $('review-result').hidden=!state.before;
 if(!state.before)return;
 const before=state.before,after=state.after;
 $('review-scores').replaceChildren(...[[`${before.score}/100`,'Before · vision score'],[after?`${after.score}/100`:'Pending','After · vision score']].map(([value,label])=>{const card=element('article');card.append(element('strong',value),element('span',label));return card;}));
 $('review-summary').textContent=(after||before).summary;
 const original=new Map(before.issues.map(issue=>[issue.id,issue]));
 $('review-resolved').replaceChildren(...(after?.resolved_issue_ids||[]).map(id=>element('li',`Model-assessed resolution: ${original.get(id)?.description||id}`)));
 const critique=after||before,phase=after?'after':'before';
 $('review-issues').replaceChildren(...critique.issues.map(issue=>{
  const card=element('article',undefined,'review-issue');card.append(element('strong',`${issue.severity.toUpperCase()} · ${issue.kind}`),element('p',issue.description),element('p',`Proposed correction: ${issue.correction}`));
  for(const id of issue.evidence_view_ids){const link=element('a',`View ${id}`);link.target='_blank';link.rel='noopener';
   link.href=id.startsWith('source-')?`/api/runs/${activeRun}/frames/${id.slice(7)}`:`/api/runs/${activeRun}/visual-review/${state.id}/images/${id.startsWith('before-')?'before':phase}/${id.startsWith('before-')?id.slice(7):id}`;card.append(link);}
  return card;
 }));
 $('review-images').replaceChildren(...(state.before_images||[]).map(image=>{
  const pair=element('article');pair.append(element('h4',image.id));const row=element('div',undefined,'review-image-pair');
  for(const [label,item] of [['Before',image],['After',(state.after_images||[]).find(after=>after.id===image.id)]]){
   if(!item)continue;const figure=element('figure'),link=element('a'),img=element('img');img.src=item.url;img.alt=`${label} native render ${image.id}`;img.loading='lazy';link.href=item.url;link.target='_blank';link.rel='noopener';link.append(img);figure.append(link,element('figcaption',label));row.append(figure);
  }pair.append(row);return pair;
 }));
 $('review-scope').textContent=`One visual correction pass · up to ${state.options?.max_geometry_fixes??1} machine CAD revision · source procedure, inventory quantities and cost inputs unchanged · physical performance unverified`;
}

async function captureReviewAfter(runId,token,state){
 reviewCaptureBusy=true;$('review-status').textContent='Capturing matched after-views with the native OpenIndustries renderer…';
 try{
  const [manifest,viewer]=await Promise.all([api(state.candidate_manifest_url),loadNativeViewer()]);
  if(token!==generation||runId!==activeRun)return;
  if(typeof viewer.captureViews!=='function')throw new Error('Refresh this page to load the native screenshot-capture API.');
  const capture=viewer.captureViews(manifest,state.camera_frames);
  await api(`/api/runs/${runId}/visual-review/${state.id}/after`,{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Request':'1'},body:JSON.stringify(capture)});
  if(token===generation){reviewCaptureBusy=false;loadVisualReview(runId,token);}
 }catch(error){if(token!==generation)return;reviewCaptureBusy=false;reviewCaptureFailed=true;renderVisualReview(state);$('review-error').textContent=error.message;$('review-error').hidden=false;}
}

$('review-start').addEventListener('click',async()=>{
 if(!activeRun||!sceneManifest||!sceneAttempt||reviewCaptureBusy)return;
 const runId=activeRun,token=generation,attempt=sceneAttempt,epoch=++reviewEpoch;
 clearTimeout(reviewTimer);pauseScene();reviewCaptureBusy=true;reviewCaptureFailed=false;$('review-start').disabled=true;$('review-error').hidden=true;
 $('review-status').textContent='Capturing three labeled native render views…';
 try{
  const viewer=await loadNativeViewer();if(token!==generation||epoch!==reviewEpoch)return;
  if(typeof viewer.captureViews!=='function')throw new Error('Refresh the page to load native render capture.');
  const capture=viewer.captureViews(sceneManifest);
  const options={vision_model:$('review-vision-model').value.trim(),cad_model:$('review-cad-model').value.trim(),cad_provider:$('review-cad-provider').value,max_geometry_fixes:Number($('review-cad-limit').value)};
  await api(`/api/runs/${runId}/visual-review`,{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Request':'1'},body:JSON.stringify({scene_attempt_id:attempt,options,capture})});
  if(token!==generation||epoch!==reviewEpoch)return;reviewCaptureBusy=false;loadVisualReview(runId,token);
 }catch(error){if(token!==generation||epoch!==reviewEpoch)return;reviewCaptureBusy=false;$('review-error').textContent=error.message;$('review-error').hidden=false;$('review-start').disabled=false;}
});
$('review-resume-capture').addEventListener('click',()=>{reviewCaptureFailed=false;loadVisualReview(activeRun,generation);});
$('review-rollback').addEventListener('click',async()=>{
 if(!activeRun||reviewState?.stage!=='applied')return;const runId=activeRun,token=generation;
 try{await api(`/api/runs/${runId}/visual-review/${reviewState.id}/rollback`,{method:'POST',headers:{'X-Workbench-Request':'1'}});if(token===generation)loadVisualReview(runId,token);}
 catch(error){$('review-error').textContent=error.message;$('review-error').hidden=false;}
});
