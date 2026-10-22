// SPDX-License-Identifier: MPL-2.0
/* Step 7 mounts the original OpenIndustries WorkspaceViewer and its native WebGL scene. */
'use strict';
let sceneTimer=null,sceneEpoch=0,sceneData=null,sceneAttempt=null,sceneManifest=null,nativeRenderer=null,nativeViewerPromise=null,sceneSuggestedRoom=null;
let scenePlaying=false,sceneTime=0,sceneAnimation=null,sceneLastTick=0,sceneSegment=-1;

function loadNativeViewer(capability=null){
 if(window.OpenIndustriesNative && (!capability||typeof window.OpenIndustriesNative[capability]==='function'))return Promise.resolve(window.OpenIndustriesNative);
 if(capability && window.OpenIndustriesNative){nativeViewerPromise=null;window.OpenIndustriesNative=undefined;}
 if(nativeViewerPromise)return nativeViewerPromise;
 nativeViewerPromise=new Promise((resolve,reject)=>{
  const script=document.createElement('script');script.src='/assets/openindustries-viewer.js';
  script.onload=()=>resolve(window.OpenIndustriesNative);
  script.onerror=async()=>{nativeViewerPromise=null;let message='The native OpenIndustries viewer failed to load.';
   try{const response=await fetch(script.src);const body=await response.json();message=body.detail||message;}catch{/* Preserve browser-load error. */}
   reject(new Error(message));};
  document.head.append(script);
 });return nativeViewerPromise;
}
function pauseScene(){scenePlaying=false;cancelAnimationFrame(sceneAnimation);$('scene-play').textContent='Play ▶';}
function leaveScene(){pauseScene();if(nativeRenderer){nativeRenderer.dispose();nativeRenderer=null;}sceneAttempt=null;}
function resetScene(){if(typeof resetVisualReview==='function')resetVisualReview();clearTimeout(sceneTimer);sceneEpoch++;leaveScene();sceneData=null;sceneManifest=null;sceneTime=0;sceneSegment=-1;sceneSuggestedRoom=null;$('scene-fit-room').hidden=true;$('scene-content').hidden=true;$('scene-error').hidden=true;$('scene-setup').open=true;}

async function loadScene(runId,token){
 if(!runId || token!==generation)return;
 clearTimeout(sceneTimer);const epoch=++sceneEpoch;
 try{
  const state=await api(`/api/runs/${runId}/scene`);
  if(epoch!==sceneEpoch || token!==generation || runId!==activeRun)return;
  renderSceneState(state);
  if(state.stage==='completed' && sceneAttempt!==state.attempt_id){
   const [preview,manifest,viewer]=await Promise.all([
    api(`/api/runs/${runId}/scene/artifacts/preview.json`),api(`/api/runs/${runId}/scene/artifacts/scene.oi.json`),loadNativeViewer()]);
   if(epoch!==sceneEpoch || token!==generation || runId!==activeRun || wizardStep!=='scene')return;
    leaveScene();sceneData=preview;sceneManifest=manifest;sceneAttempt=state.attempt_id;sceneTime=0;sceneSegment=-1;
   $('scene-content').hidden=false;$('scene-setup').open=false;
   $('scene-width').value=String(preview.room[0]);$('scene-depth').value=String(preview.room[1]);$('scene-height').value=String(preview.room[2]);
   $('scene-auto-fit').checked=state.options.auto_fit_room!==false;$('scene-expand-stock').checked=Boolean(state.options.expand_stock_quantities);
   nativeRenderer=viewer.mount($('scene-viewer'),manifest);
   $('scene-scrub').max=String(preview.duration);$('scene-scrub').value='0';
   $('scene-download').href=`/api/runs/${runId}/scene/artifacts/scene.oi.json`;
   $('scene-report-download').href=`/api/runs/${runId}/scene/artifacts/scene-report.json`;
   const inventory=state.report.stock_inventory||[],stock=inventory.reduce((sum,item)=>sum+item.stock_quantity,0);
   $('scene-meta').textContent=`Native OpenIndustries WorkspaceViewer · ${state.report.instances} CAD objects · ${state.report.animation_tracks} animation tracks · ${state.report.duration_s}s storyboard · room ${preview.room.join(' × ')} m${stock?` · ${stock} stocked consumables represented by ${inventory.length} labeled samples`:''}${state.report.layout?.room_adjusted?' · planning room expanded to fit unscaled CAD':''}`;
   $('scene-limitations').replaceChildren(...state.report.limitations.map(text=>element('li',text)));
   $('scene-operations').replaceChildren(...preview.segments.map((segment,index)=>{
    const button=element('button',`${String(index+1).padStart(2,'0')} · ${segment.label}`);button.type='button';
    button.addEventListener('click',()=>{pauseScene();sceneTime=segment.start_s;nativeRenderer?.focusInstance(segment.instance_ids[0]||null);drawScene();});return button;
   }));drawScene();
   $('visual-review-panel').hidden=false;
   if(typeof loadVisualReview==='function')loadVisualReview(runId,token);
  }
  if(['queued','building'].includes(state.stage))sceneTimer=setTimeout(()=>loadScene(runId,token),1000);
 }catch(error){if(epoch!==sceneEpoch || token!==generation)return;$('scene-error').textContent=error.message;$('scene-error').hidden=false;}
}

function renderSceneState(state){
 const busy=['queued','building'].includes(state.stage);
 $('scene-runtime').textContent=state.runtime?.message||'';
 $('scene-build').disabled=busy||['needs_design','needs_machines'].includes(state.stage)||state.runtime?.available===false;
 $('scene-build').textContent=state.stage==='completed'?'Rebuild native scene ↗':'Render generated machines ↗';
 $('scene-error').hidden=state.stage!=='failed';if(state.stage==='failed')$('scene-error').textContent=state.error;
 sceneSuggestedRoom=state.layout?.suggested_room_m||null;$('scene-fit-room').hidden=!sceneSuggestedRoom;
 if(sceneSuggestedRoom)$('scene-setup').open=true;
 $('scene-status').textContent={needs_design:state.message,needs_machines:state.message,
  not_started:'Ready to assemble the generated Forma assets in the native OpenIndustries viewer.',
  queued:`Scene queued · ${state.elapsed_s||0}s.`,building:`Importing generated machine CAD into OpenIndustries · ${state.elapsed_s||0}s.`,
  completed:'Native OpenIndustries scene ready. Drag to orbit, scroll to zoom, or click a machine part to select it.',
  failed:'Scene creation failed. Generated machine assets are retained.',stale:state.message}[state.stage]||state.stage;
 if(state.stage!=='completed'){$('scene-content').hidden=true;leaveScene();}
}

function drawScene(){
 if(!sceneData||!nativeRenderer||$('wizard-scene').hidden)return;
 nativeRenderer.seek(sceneTime);
 $('scene-scrub').value=String(sceneTime);$('scene-time').textContent=`${sceneTime.toFixed(1)} / ${sceneData.duration.toFixed(1)}s`;
 const found=sceneData.segments.findIndex(segment=>sceneTime>=segment.start_s&&sceneTime<segment.end_s);
 const index=found<0?sceneData.segments.length-1:found,segment=sceneData.segments[index];
 if(index!==sceneSegment){sceneSegment=index;$('scene-current').textContent=`${index+1}/${sceneData.segments.length} · ${segment.label}. ${segment.implementation}`;
  [...$('scene-operations').children].forEach((button,i)=>button.setAttribute('aria-pressed',String(i===index)));}
}
function sceneTick(now){if(!scenePlaying||!sceneData)return;sceneTime=(sceneTime+Math.min(.2,(now-sceneLastTick)/1000))%sceneData.duration;sceneLastTick=now;drawScene();sceneAnimation=requestAnimationFrame(sceneTick);}
$('scene-play').addEventListener('click',()=>{if(!sceneData)return;if(scenePlaying){pauseScene();return;}scenePlaying=true;sceneLastTick=performance.now();$('scene-play').textContent='Pause Ⅱ';sceneAnimation=requestAnimationFrame(sceneTick);});
$('scene-rewind').addEventListener('click',()=>{pauseScene();sceneTime=0;drawScene();});
$('scene-fit').addEventListener('click',()=>nativeRenderer?.focusInstance(null));
$('scene-scrub').addEventListener('input',()=>{pauseScene();sceneTime=Number($('scene-scrub').value);drawScene();});
$('scene-viewer').addEventListener('openindustries-error',event=>{pauseScene();$('scene-error').textContent=`Native OpenIndustries viewer: ${event.detail}`;$('scene-error').hidden=false;});
$('scene-fit-room').addEventListener('click',()=>{if(!sceneSuggestedRoom)return;$('scene-width').value=String(sceneSuggestedRoom[0]);$('scene-depth').value=String(sceneSuggestedRoom[1]);$('scene-height').value=String(sceneSuggestedRoom[2]);$('scene-auto-fit').checked=true;$('scene-options').requestSubmit();});
$('scene-options').addEventListener('submit',async event=>{
 event.preventDefault();if(!activeRun||!resultsReady)return;const runId=activeRun,token=generation,epoch=++sceneEpoch;
 clearTimeout(sceneTimer);leaveScene();const options={room_width_m:Number($('scene-width').value),room_depth_m:Number($('scene-depth').value),room_height_m:Number($('scene-height').value),seconds_per_operation:Number($('scene-seconds').value),auto_fit_room:$('scene-auto-fit').checked,expand_stock_quantities:$('scene-expand-stock').checked};
 $('scene-build').disabled=true;$('scene-error').hidden=true;$('scene-status').textContent='Assembling generated Forma assets in OpenIndustries…';
 try{const state=await api(`/api/runs/${runId}/scene?rebuild=true`,{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Request':'1'},body:JSON.stringify(options)});
  if(epoch!==sceneEpoch||token!==generation||runId!==activeRun)return;renderSceneState(state);loadScene(runId,token);
 }catch(error){if(epoch!==sceneEpoch||token!==generation)return;$('scene-error').textContent=error.message;$('scene-error').hidden=false;$('scene-build').disabled=false;}
});
