// SPDX-License-Identifier: MPL-2.0
/* Lazy images on cards; one short-lived native GIF renderer, shared by the whole page. */
'use strict';
const machinePreviewEntries=new Map();
let machinePreviewQueue=[],machinePreviewWorking=false,machinePreviewAbort=null,machinePreviewCurrent=null;
const machinePreviewObserver=new IntersectionObserver(entries=>{
 for(const item of entries)if(item.isIntersecting){machinePreviewObserver.unobserve(item.target);queueMachinePreview(item.target.dataset.previewKey);}
},{rootMargin:'180px'});

function pauseMachinePreviews(){
 machinePreviewObserver.disconnect();machinePreviewQueue=[];
 if(machinePreviewAbort)machinePreviewAbort.abort();
 for(const entry of machinePreviewEntries.values())if(entry.status==='queued')entry.status='idle';
 for(const entry of machinePreviewEntries.values())for(const node of entry.nodes)node.dispatchEvent(new Event('preview-pause'));
}

function resetMachinePreviews(){pauseMachinePreviews();for(const entry of machinePreviewEntries.values())entry.nodes.clear();machinePreviewEntries.clear();}
function observeMachinePreview(card){const host=card.querySelector('[data-preview-key]');if(host && host.dataset.ready!=='true')machinePreviewObserver.observe(host);}

function showReadyMachinePreview(host,entry){
 if(host.dataset.ready==='true')return;
 host.dataset.ready='true';const image=element('img');image.width=320;image.height=320;image.loading='lazy';image.decoding='async';
 image.alt=`${entry.name} generated CAD turntable preview`;image.src=entry.info.poster_url;
 const link=element('a');link.href=entry.info.gif_url;link.target='_blank';link.rel='noopener';link.append(image);
 const caption=element('figcaption','Generated CAD · 2-second camera turntable');
 const play=element('button','Play turntable ▶');play.type='button';play.setAttribute('aria-pressed','false');
 let playing=false;
 function setPlaying(value){playing=value;image.src=playing?entry.info.gif_url:entry.info.poster_url;play.textContent=playing?'Pause turntable Ⅱ':'Play turntable ▶';play.setAttribute('aria-pressed',String(playing));}
 play.addEventListener('click',()=>setPlaying(!playing));host.addEventListener('preview-pause',()=>setPlaying(false));
 host.replaceChildren(link,caption,play);
}

function detachMachinePreview(card){
 const host=card.querySelector('[data-preview-key]');if(!host)return;machinePreviewObserver.unobserve(host);
 const entry=machinePreviewEntries.get(host.dataset.previewKey);entry?.nodes.delete(host);
 if(machinePreviewCurrent===host.dataset.previewKey && ![...(entry?.nodes||[])].some(node=>node.isConnected))machinePreviewAbort?.abort();
}

function updatePreviewNodes(entry){
 for(const host of entry.nodes){
  if(!host.isConnected){entry.nodes.delete(host);continue;}
  if(entry.status==='ready'){
   showReadyMachinePreview(host,entry);
  }else{
   host.dataset.ready='false';
   const message=entry.status==='error'?`Preview unavailable: ${entry.error}`:entry.message||'CAD preview will load when this card is visible.';
   const placeholder=element('div',message,'machine-preview-placeholder');host.replaceChildren(placeholder);
   if(entry.status==='error'){const retry=element('button','Retry preview');retry.type='button';retry.addEventListener('click',()=>{entry.status='idle';queueMachinePreview(entry.key);});host.append(retry);}
  }
 }
}

function machinePreviewCard(row){
 const host=element('figure',undefined,'machine-preview');
 if(!row.preview){host.append(element('div','CAD preview appears after generation.','machine-preview-placeholder'));return host;}
 const key=`${activeRun}:${row.key}:${row.preview.cache_key}`;host.dataset.previewKey=key;
 let entry=machinePreviewEntries.get(key);
 if(!entry){entry={key,name:row.name,info:row.preview,row,runId:activeRun,token:generation,status:row.preview.ready?'ready':'idle',nodes:new Set()};machinePreviewEntries.set(key,entry);}
 if(row.preview.ready){entry.info=row.preview;entry.status='ready';}
 entry.nodes.add(host);
 if(entry.status==='ready'){
  showReadyMachinePreview(host,entry);
 }else{host.append(element('div',entry.message||'Preview queued when visible…','machine-preview-placeholder'));machinePreviewObserver.observe(host);}
 return host;
}

function queueMachinePreview(key){
 const entry=machinePreviewEntries.get(key);
 if(!entry || ['ready','queued','rendering'].includes(entry.status))return;
 entry.status='queued';entry.message='Waiting for the shared preview renderer…';machinePreviewQueue.push(key);updatePreviewNodes(entry);processMachinePreviews();
}

async function processMachinePreviews(){
 if(machinePreviewWorking)return;machinePreviewWorking=true;
 try{
  while(machinePreviewQueue.length && wizardStep==='machines'){
   const key=machinePreviewQueue.shift(),entry=machinePreviewEntries.get(key);
   if(!entry || entry.runId!==activeRun || entry.token!==generation)continue;
   const controller=new AbortController();machinePreviewAbort=controller;machinePreviewCurrent=key;
   entry.status='rendering';entry.message='Loading the shared native preview renderer…';updatePreviewNodes(entry);
   try{
    const response=await fetch(entry.row.artifact_url,{signal:controller.signal});
    if(!response.ok)throw new Error(`CAD download failed (HTTP ${response.status})`);
    const document=await response.json(),viewer=await loadNativeViewer('renderMachineGif');
    if(controller.signal.aborted)throw new DOMException('Preview paused','AbortError');
    const blob=await viewer.renderMachineGif(document,entry.info.cad_sha256,value=>{
     entry.message=`Rendering turntable · ${Math.round(value*20)}/20 frames`;updatePreviewNodes(entry);
    },controller.signal);
    entry.message='Caching GIF and still poster…';updatePreviewNodes(entry);
    const info=await api(`/api/runs/${entry.runId}/machines/${entry.row.key}/previews/${entry.info.cache_key}`,{
     method:'POST',headers:{'Content-Type':'image/gif','X-Workbench-Request':'1'},body:blob,signal:controller.signal});
    entry.info=info;entry.status='ready';updatePreviewNodes(entry);
   }catch(error){
    if(error.name==='AbortError'){entry.status='idle';entry.message='Preview paused until this card is visible.';if(wizardStep==='machines')for(const node of entry.nodes)machinePreviewObserver.observe(node);}
    else{entry.status='error';entry.error=error.message;}
    updatePreviewNodes(entry);
   }finally{machinePreviewAbort=null;machinePreviewCurrent=null;}
  }
 }finally{machinePreviewWorking=false;}
}
