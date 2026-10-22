// SPDX-License-Identifier: MPL-2.0
/** Mount the original OpenIndustries React/WebGL viewer, not a replacement renderer. */
import React from 'react';
import {createRoot} from 'react-dom/client';
import {WorkspaceViewer} from 'openindustries-viewer';
import {hydrateManifest, readManifest} from 'openindustries-workspace';
import {evaluateWorkspace} from 'openindustries-workspace';
import {createWorld,applyWorldPoses} from 'openindustries-world';
import * as THREE from 'three';
import {importForm} from 'openindustries-form';
import {renderGif} from 'openindustries-gif';

export function mount(host: HTMLElement, document: unknown) {
  const workspace = hydrateManifest(readManifest(document), []);
  if (workspace.items.some((item: any) => item.missing)) throw new Error('The native scene is missing generated machine geometry');
  let time: number | null = 0, selected = -1, selectedPart = -1, focus = 0;
  const fail = (error: unknown) => host.dispatchEvent(new CustomEvent('openindustries-error', {detail:String(error)}));
  const root = createRoot(host, {onUncaughtError:fail});
  const render = () => root.render(<WorkspaceViewer workspace={workspace} selected={selected} selectedPart={selectedPart}
    time={time} focus={focus} region={null} onSelect={(instance: number, part: number) => {selected=instance;selectedPart=part;render();}} />);
  render();
  host.dataset.renderer = 'OpenIndustries.WorkspaceViewer';
  return {
    kind:'OpenIndustries.WorkspaceViewer',
    seek(value: number) {time=value;render();},
    focusInstance(id: string | null) {selected=id===null?-1:workspace.items.findIndex((item:any)=>item.id===id);selectedPart=-1;focus++;render();},
    dispose() {root.unmount();delete host.dataset.renderer;},
  };
}

/** Capture canonical, labeled views with the same native world used by the viewport. */
export function captureViews(document: unknown, previousFrames?: any[]) {
  const workspace=hydrateManifest(readManifest(document),[]);
  const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
  renderer.setSize(960,640);renderer.setPixelRatio(1);
  const world=createWorld(workspace.items.map((item:any)=>item.asset),workspace.room);
  try {
    applyWorldPoses(world.groups,evaluateWorkspace(workspace.items,workspace.animation,0));
    const bounds=new THREE.Box3();world.groups.forEach((group:any)=>bounds.union(new THREE.Box3().setFromObject(group)));
    const center=bounds.getCenter(new THREE.Vector3()),distance=Math.max(1,bounds.getSize(new THREE.Vector3()).length()*1.35);
    const frames=previousFrames || [
      {id:'render-isometric',label:'Isometric, start',direction:[1,.9,1],time_s:0},
      {id:'render-reverse',label:'Reverse, mid-operation',direction:[-1,.8,1],time_s:workspace.animation.duration/2},
      {id:'render-top',label:'Top view, start',direction:[0,1,.001],time_s:0},
    ].map(frame=>({...frame,position:center.clone().add(new THREE.Vector3().fromArray(frame.direction).normalize().multiplyScalar(distance)).toArray(),target:center.toArray(),fov:45}));
    const images=frames.map((frame:any)=>{
      const camera=new THREE.PerspectiveCamera(frame.fov,1.5,.01,1000);camera.position.fromArray(frame.position);
      camera.lookAt(new THREE.Vector3().fromArray(frame.target));camera.updateProjectionMatrix();camera.updateMatrixWorld();
      applyWorldPoses(world.groups,evaluateWorkspace(workspace.items,workspace.animation,frame.time_s));
      renderer.render(world.scene,camera);
      const overlay=window.document.createElement('canvas');overlay.width=960;overlay.height=640;
      const ctx=overlay.getContext('2d')!;ctx.drawImage(renderer.domElement,0,0);
      ctx.font='bold 16px system-ui';ctx.textAlign='center';
      world.groups.forEach((group:any,index:number)=>{
        const box=new THREE.Box3().setFromObject(group),point=box.getCenter(new THREE.Vector3());point.y=box.max.y+.08;
        point.project(camera);const x=(point.x+1)*480,y=(1-point.y)*320;
        const label=workspace.items[index].id,width=ctx.measureText(label).width+12;
        ctx.fillStyle='rgba(255,255,255,.95)';ctx.fillRect(x-width/2,y-17,width,23);ctx.fillStyle='#16382c';ctx.fillText(label,x,y);
      });
      ctx.textAlign='left';ctx.fillStyle='rgba(255,255,255,.95)';ctx.fillRect(8,8,480,30);ctx.fillStyle='#16382c';
      ctx.fillText(`${frame.id} · ${frame.label} · ${frame.time_s.toFixed(1)}s`,16,29);
      return {id:frame.id,label:frame.label,png_data_url:overlay.toDataURL('image/png')};
    });
    return {frames,images,renderer:'OpenIndustries native createWorld/evaluateWorkspace; ID labels are annotations'};
  } finally {world.dispose();renderer.dispose();}
}

/** One transient renderer for a small cached card GIF, not a mounted viewer per machine. */
export async function renderMachineGif(document: unknown,digest: string,progress: (value:number)=>void,signal: AbortSignal) {
  const asset=importForm(document,'machine.forma.json',digest);
  if(asset.parts.some((part:any)=>part.metadata.representation!=='CAD mesh'))throw new Error('Machine preview requires generated CAD meshes');
  const result=await renderGif([asset],[6,5,3],{scope:'asset',assetIndex:0,motion:'turntable',
    region:{x:0,z:0,width:1,depth:1},size:320,duration:2,fps:10},signal,progress);
  return result.blob;
}
