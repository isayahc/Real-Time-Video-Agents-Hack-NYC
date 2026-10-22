// SPDX-License-Identifier: MPL-2.0
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const layout=import(pathToFileURL(path.join(__dirname,'../protocol_pipeline/scene_layout.mjs')).href);
const item=(id,width,depth,height=1,category='other')=>({id,name:id,category,asset:{dimensions:[width,height,depth]}});

test('stock quantities stay in inventory instead of becoming machine stations',async()=>{
 const {instancePlan}=await layout;
 assert.deepEqual(instancePlan({category:'consumable',quantity:100}),{count:1,inventory:true,representedQuantity:100});
 assert.equal(instancePlan({category:'consumable',quantity:100},true).count,100);
 assert.equal(instancePlan({category:'fixture',quantity:2}).count,2);
});

test('heterogeneous CAD fits without giving every item the largest footprint',async()=>{
 const {planLayout}=await layout;
 const items=[item('large',2.4,1.5),...Array.from({length:15},(_,i)=>item(`small-${i}`,.15,.1))];
 const before=JSON.stringify(items),result=planLayout(items,[6,5,3],false);
 assert.equal(result.fits,true);assert.equal(result.room_adjusted,false);assert.equal(JSON.stringify(items),before);
 for(const current of items){const [x,y,z]=result.positions[current.id],[w,h,d]=current.asset.dimensions;
  assert.ok(x-w/2>=-3 && x+w/2<=3);assert.ok(z-d/2>=-2.5 && z+d/2<=2.5);assert.equal(y,0);
  assert.ok(h<=3);
 }
 for(let a=0;a<items.length;a++)for(let b=a+1;b<items.length;b++){
  const pa=result.positions[items[a].id],pb=result.positions[items[b].id],da=items[a].asset.dimensions,db=items[b].asset.dimensions;
  assert.ok(Math.abs(pa[0]-pb[0])>=(da[0]+db[0])/2 || Math.abs(pa[2]-pb[2])>=(da[2]+db[2])/2,'CAD footprints overlap');
 }
});

test('the reported 100-tool case fits the requested planning room',async()=>{
 const {planLayout}=await layout;
 const machines=[item('stage',.9,.42,.505,'actuator'),item('gripper',.401,.6,.195,'end_effector'),
  item('fixture',.2,.152,.055,'fixture'),item('camera',.4,.31,.1925,'sensor'),item('controller',.405,.3,.375,'controller')];
 const stock=item('stock',.2,.15,.155,'consumable');
 assert.equal(planLayout([...machines,stock],[6,5,3],false).fits,true);
 const expanded=[...machines,...Array.from({length:100},(_,i)=>({...stock,id:`stock-${i}`}))];
 assert.equal(planLayout(expanded,[6,5,3],false).fits,true);
});

test('strict rooms get a suggestion; auto-fit expands the room, never the geometry',async()=>{
 const {planLayout}=await layout,items=[item('large',7,2,4)];
 const strict=planLayout(items,[6,5,3],false);
 assert.equal(strict.fits,false);assert.ok(strict.suggested_room_m[0]>7);assert.ok(strict.suggested_room_m[2]>4);
 const fitted=planLayout(items,[6,5,3],true);
 assert.equal(fitted.fits,true);assert.equal(fitted.room_adjusted,true);
 assert.deepEqual(items[0].asset.dimensions,[7,4,2]);
});
