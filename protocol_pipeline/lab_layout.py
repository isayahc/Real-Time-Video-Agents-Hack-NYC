# SPDX-License-Identifier: MPL-2.0
"""Semantic subsystem zoning in a fixed lab; preserves original machine geometry."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math


TEMPLATE = {
    'id': 'compact-lab-v1', 'name': 'Compact automation lab', 'room_m': [8, 6, 3],
    'aisle': {'name': 'Reserved access / exit aisle', 'bounds_xz': [-3.8, -0.6, 3.8, 0.6]},
    'zones': [
        {'id': 'workbench', 'name': 'Shared process bench', 'bounds_xz': [-1.6, -2.7, 1.6, -1.0], 'surface_y': .9},
        {'id': 'robot_cell', 'name': 'Floor-mounted automation cell', 'bounds_xz': [-3.7, .9, -.3, 2.7], 'surface_y': 0},
        {'id': 'utilities', 'name': 'Controls and utilities', 'bounds_xz': [1.9, -2.7, 3.7, -1.0], 'surface_y': 0},
        {'id': 'inventory', 'name': 'Input / output staging bench', 'bounds_xz': [.3, 1.0, 3.7, 2.7], 'surface_y': .9},
    ],
}


def bench_asset(zone: dict) -> dict:
    """Explicit template furniture, never a replacement for generated machine CAD."""
    x0, z0, x1, z1 = zone['bounds_xz']
    w, d, h = x1-x0, z1-z0, zone['surface_y']
    vertices = [-w/2, 0, -d/2, w/2, 0, -d/2, w/2, h, -d/2, -w/2, h, -d/2,
                -w/2, 0, d/2, w/2, 0, d/2, w/2, h, d/2, -w/2, h, d/2]
    indices = [0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,3,7,6,3,6,2,0,4,7,0,7,3,1,2,6,1,6,5]
    ident = 'lab-' + zone['id']
    source = {'kind': 'generated', 'generator': 'form-industries', 'filename': ident+'.json',
              'digest': hashlib.sha256(json.dumps(zone, sort_keys=True).encode()).hexdigest()}
    return {'id': ident, 'name': zone['name']+' (template furniture)', 'source': source,
            'schemaVersion': 1, 'units': 'm', 'upAxis': 'Y', 'dimensions': [w,h,d], 'originOffset': [0,0,0],
            'parts': [{'id': ident+'/body', 'name': 'Template bench envelope', 'vertices': vertices, 'indices': indices,
                       'color': [.35,.48,.58], 'metadata': {'representation': 'Lab template furniture envelope'}}],
            'hierarchy': {'id': ident+'/root', 'name': zone['name'], 'partIds': [ident+'/body'], 'children': []},
            'warnings': ['Furniture envelope; internal cabinet/leg geometry is not modeled.']}


def plan_lab(manifest: dict, preview: dict, proposal: dict) -> tuple[dict, dict]:
    """Use categories, roles, operation co-use and CAD bounds; do not guess mounts."""
    scene = deepcopy(manifest)
    scene['room'] = TEMPLATE['room_m'][:]
    scene['animation'] = {'duration': 3, 'loop': False, 'tracks': []}
    equipment = {row['id']: row for row in proposal['equipment']}
    metadata = {row['id']: row for row in preview['instances']}
    assets = {row['id']: row for row in manifest['assets']}
    operations = proposal['operation_designs']
    records, placed, issues = [], [], []
    if proposal.get('design_scope') == 'integrated_workcell':
        issues.append('The integrated machine is placed as one assembly. Task performance, axis travel, grip force and camera coverage remain unverified; successful placement does not close its machine requirements.')
    zones = {zone['id']: zone for zone in TEMPLATE['zones']}

    def semantics(instance):
        eqid = metadata[instance['id']]['equipment_id']
        eq = equipment[eqid]
        ops = [op['source_operation_id'] for op in operations if eqid in op['equipment_ids']]
        peers = sorted({peer for op in operations if eqid in op['equipment_ids'] for peer in op['equipment_ids'] if peer != eqid})
        return eq, ops, peers

    # Large CAD first; fixtures before smaller dependent tools at equal size.
    payload_ids=set(scene.get('storyboard',{}).get('payload_instance_ids',[]))
    host_id=scene.get('storyboard',{}).get('host_instance_id')
    original_host=next((deepcopy(i) for i in scene['instances'] if i['id']==host_id),None)
    if payload_ids and original_host is None:
        raise ValueError('Storyboard workpieces require their machine host')
    instances = sorted([i for i in scene['instances'] if i['id'] not in payload_ids], key=lambda i: -math.prod(assets[i['assetId']]['dimensions']))
    for instance in instances:
        eq, ops, peers = semantics(instance)
        w,h,d = assets[instance['assetId']]['dimensions']
        if not all(math.isfinite(v) and v > 0 for v in (w,h,d)):
            raise ValueError(f"Invalid CAD bounds for {eq['name']}")
        category = eq['category']
        role = (eq['name']+' '+eq.get('role','')).lower()
        if category == 'consumable':
            candidates, reason = ['inventory'], 'Stocked material belongs in input/output staging.'
        elif category == 'controller' or any(word in role for word in ('pump', 'compressor', 'power supply')):
            candidates, reason = ['utilities'], 'Control/power/fluid support belongs in the utilities zone.'
        elif category in ('actuator','fixture','end_effector','sensor'):
            candidates, reason = ['workbench','robot_cell'], 'Process equipment is grouped on the shared work surface; oversized assemblies require floor space.'
        else:
            candidates, reason = ['workbench','robot_cell'], 'Unclassified subsystem staged with process equipment; review its functional role.'
        options = []
        for priority, zone_id in enumerate(candidates):
            zone = zones[zone_id]; x0,z0,x1,z1 = zone['bounds_xz']; y = zone['surface_y']
            if y+h > TEMPLATE['room_m'][2]-.1:
                continue
            for rotation, width, depth in [(0,w,d),(90,d,w)]:
                for xi in range(int((x1-x0)/.1)+1):
                    x = x0+.05+width/2+xi*.1
                    if x+width/2 > x1-.05: break
                    for zi in range(int((z1-z0)/.1)+1):
                        z = z0+.05+depth/2+zi*.1
                        if z+depth/2 > z1-.05: break
                        if any(abs(x-p['position_m'][0]) < (width+p['footprint_m'][0])/2+.05
                               and abs(z-p['position_m'][2]) < (depth+p['footprint_m'][1])/2+.05 for p in placed):
                            continue
                        related = [p for p in placed if p['equipment_id'] in peers]
                        distance = sum(math.hypot(x-p['position_m'][0],z-p['position_m'][2]) for p in related)
                        score = priority*1000+distance+ .01*(xi+zi)
                        options.append((score, zone_id, [x,y,z], rotation, [width,depth]))
        record = {'instance_id': instance['id'], 'equipment_id': eq['id'], 'name': instance['name'],
                  'category': category, 'role': eq.get('role',''), 'operation_ids': ops,
                  'related_equipment_ids': peers, 'dimensions_m': [w,h,d], 'rationale': reason}
        if options:
            _, zone_id, position, rotation, footprint = min(options, key=lambda row: row[0])
            record.update(status='placed', zone=zone_id, position_m=position, rotation_y_deg=rotation, footprint_m=footprint)
            instance.update(position=position, rotation=[0,rotation,0], visible=True)
            placed.append(record)
            if category in ('end_effector','sensor'):
                issues.append(f"{instance['name']}: staged near related equipment; mount frame, tool interface or camera target is missing. Mounting is unresolved.")
        else:
            record.update(status='unplaced', zone=None)
            instance['visible'] = False
            issues.append(f"{instance['name']}: no collision-free fit in its permitted zones. Change CAD or the lab template; not silently scaled or moved into the aisle.")
        records.append(record)
    if original_host:
        host=next(i for i in scene['instances'] if i['id']==host_id)
        theta=math.radians(host['rotation'][1]-original_host['rotation'][1])
        for payload in scene['instances']:
            if payload['id'] not in payload_ids:continue
            dx,dy,dz=[a-b for a,b in zip(payload['position'],original_host['position'])]
            payload['position']=[host['position'][0]+dx*math.cos(theta)+dz*math.sin(theta),host['position'][1]+dy,
                                 host['position'][2]-dx*math.sin(theta)+dz*math.cos(theta)]
            payload['rotation'][1]+=math.degrees(theta)
            payload['visible']=host['visible']
    for zone in TEMPLATE['zones']:
        if not zone['surface_y']: continue
        asset = bench_asset(zone)
        scene.setdefault('bundledAssets', []).append(asset)
        scene['assets'].append({key:asset[key] for key in ('id','name','source','dimensions')})
        x0,z0,x1,z1 = zone['bounds_xz']
        scene['instances'].append({'id': asset['id'], 'assetId':asset['id'], 'name':asset['name'],
                                   'visible':True, 'position':[(x0+x1)/2,0,(z0+z1)/2], 'rotation':[0,0,0]})
    report = {'template': TEMPLATE, 'placements': records, 'issues': issues,
              'status': 'planned' if len(placed)==len(records) else 'needs_review',
              'placed_count':len(placed), 'total_count':len(records),
              'method':'Semantic category/role zoning, operation co-use proximity, unscaled CAD bounding-box clearance',
              'limitations':['Mounting interfaces, robot reach, cable/hose routing and bench load limits are not established.',
                             'Clearance checks use bounding boxes, not mesh collisions. All placements are planning candidates.',
                             'Original machine CAD is retained. Template furniture is explicitly labeled envelope geometry.']}
    return report, scene
