// SPDX-License-Identifier: MPL-2.0
/** Size-aware, unscaled planning layout. Inventory counts are not machine stations. */
export function instancePlan(equipment, expandStock = false) {
  const stock = equipment.category === 'consumable' && !expandStock;
  return {count:stock ? 1 : equipment.quantity, inventory:stock, representedQuantity:equipment.quantity};
}

function footprints(items) {
  return items.map(item => {
    const [width,height,depth] = item.asset.dimensions;
    if (![width,height,depth].every(value => Number.isFinite(value) && value > 0)) throw new Error(`Invalid CAD dimensions: ${item.name}`);
    const gap = item.category === 'consumable' ? .02 : .175;
    const motion = ['actuator','end_effector'].includes(item.category) ? .1 : 0;
    return {item,width,height,depth,gap,motion,w:width+2*gap+motion,d:depth+2*gap};
  });
}

function shelfPack(boxes, width, depth) {
  let best = null;
  for (const sort of [(a,b)=>b.d-a.d || b.w-a.w,(a,b)=>b.w*b.d-a.w*a.d]) {
    const rows=[];
    for (const box of [...boxes].sort(sort)) {
      if (box.w > width+1e-8) {rows.length=0;break;}
      let row = rows.filter(row=>box.d<=row.d+1e-8 && row.w+box.w<=width+1e-8)
        .sort((a,b)=>(width-a.w-box.w)-(width-b.w-box.w))[0];
      if(!row){row={w:0,d:box.d,boxes:[]};rows.push(row);}
      row.boxes.push({box,left:row.w});row.w+=box.w;
    }
    if(!rows.length)continue;
    const usedDepth=rows.reduce((sum,row)=>sum+row.d,0),usedWidth=Math.max(...rows.map(row=>row.w));
    if(usedDepth>depth+1e-8)continue;
    const score=usedWidth*usedDepth+.15*(usedWidth-usedDepth)**2;
    if(!best || score<best.score)best={rows,usedWidth,usedDepth,score};
  }
  return best;
}

function findPacking(boxes, width, depth) {
  let best=null;
  const min=Math.max(...boxes.map(box=>box.w));
  if(min>width+1e-8)return null;
  for(let index=0;index<=16;index++){
    const candidate=min+(width-min)*index/16,pack=shelfPack(boxes,candidate,depth);
    if(pack && (!best || pack.score<best.score))best=pack;
  }
  return best;
}

export function planLayout(items, requestedRoom, autoFit = true) {
  if(!items.length)throw new Error('There are no generated machines to place');
  const boxes=footprints(items),wall=.15;
  const height=Math.max(...boxes.map(box=>box.height))+.1;
  let room=[...requestedRoom],packing=findPacking(boxes,room[0]-2*wall,room[1]-2*wall);
  const fits=Boolean(packing) && height<=room[2];
  let suggested=[...room];
  if(!fits){
    const minWidth=Math.max(room[0],...boxes.map(box=>box.w+2*wall));
    let best=null;
    for(let index=0;index<=24;index++){
      const width=minWidth+(Math.min(100,Math.max(minWidth*3,room[0]))-minWidth)*index/24;
      const pack=findPacking(boxes,width-2*wall,100-2*wall);
      if(!pack)continue;
      const depth=Math.max(room[1],pack.usedDepth+2*wall);
      if(width>100 || depth>100 || height>100)continue;
      const score=width*depth;
      if(!best || score<best.score)best={width,depth,pack,score};
    }
    if(!best)throw new Error('The generated CAD cannot fit within the supported 100 m planning-room bounds');
    suggested=[Math.ceil(best.width*10)/10,Math.ceil(best.depth*10)/10,Math.max(room[2],Math.ceil(height*10)/10)];
    if(!autoFit)return {fits:false,requested_room_m:requestedRoom,suggested_room_m:suggested,
      message:`The selected room does not fit this CAD layout. Suggested planning room: ${suggested.join(' × ')} m.`};
    room=suggested;packing=findPacking(boxes,room[0]-2*wall,room[1]-2*wall);
  }
  const positions={};let z=(room[1]-packing.usedDepth)/2-room[1]/2;
  for(const row of packing.rows){
    const x=(room[0]-row.w)/2-room[0]/2;
    for(const entry of row.boxes){const box=entry.box;
      positions[box.item.id]=[x+entry.left+box.gap+box.width/2,0,z+box.gap+box.depth/2];}
    z+=row.d;
  }
  return {fits:true,requested_room_m:requestedRoom,room_m:room,suggested_room_m:suggested,
    room_adjusted:room.some((value,index)=>value!==requestedRoom[index]),positions,
    packed_footprint_m:[packing.usedWidth,packing.usedDepth],
    method:'actual CAD footprint shelf packing; unscaled geometry; assumed clearance and motion margins'};
}
