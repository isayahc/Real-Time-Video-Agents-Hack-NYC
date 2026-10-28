# SPDX-License-Identifier: MPL-2.0
"""Rendered-image critique and one bounded, reversible visual correction pass."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import struct
import time
from typing import Literal
import uuid
import os
import subprocess
import sys

from pydantic import Field, RootModel

from .machines import generate_machine, process_alive
from .models import StrictModel
from .pipeline import NebiusClient, save_json, sha256
from .scenes import SceneOptions, ScenePlacement, build_rehearsal

VIEW_IDS={'render-isometric','render-reverse','render-top'}


class VisionReviewData(RootModel[dict]):
    """Keep the provider-facing schema simple; the full critique is validated locally."""


class CameraFrame(StrictModel):
    id: str
    label: str
    position: tuple[float,float,float]
    target: tuple[float,float,float]
    direction: tuple[float,float,float] | None = None
    fov: float = Field(default=45,ge=10,le=100)
    time_s: float = Field(ge=0,le=120)


class CapturedImage(StrictModel):
    id: str
    label: str
    png_data_url: str = Field(max_length=4500000)


class CaptureBundle(StrictModel):
    frames: list[CameraFrame] = Field(min_length=3,max_length=3)
    images: list[CapturedImage] = Field(min_length=3,max_length=3)
    renderer: str


class VisualReviewOptions(StrictModel):
    vision_model: str = Field(min_length=1,max_length=200)
    cad_model: str = Field(min_length=1,max_length=200)
    cad_provider: Literal['nebius','gmi'] = 'nebius'
    max_geometry_fixes: int = Field(default=1,ge=0,le=1)


class VisualReviewStart(StrictModel):
    scene_attempt_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    options: VisualReviewOptions
    capture: CaptureBundle


class VisualIssue(StrictModel):
    id: str = Field(min_length=1)
    kind: Literal['layout','geometry','context','animation','camera']
    severity: Literal['low','medium','high']
    equipment_ids: list[str]
    description: str = Field(min_length=1)
    evidence_view_ids: list[str] = Field(min_length=1)
    correction: str = Field(min_length=1)


class CadRevision(StrictModel):
    equipment_id: str
    issue_ids: list[str] = Field(min_length=1)
    instructions: str = Field(min_length=1)


class VisualCritique(StrictModel):
    status: Literal['needs_improvement','acceptable','insufficient_evidence']
    score: int = Field(ge=0,le=100)
    summary: str
    issues: list[VisualIssue] = Field(max_length=12)
    layout_changes: list[ScenePlacement] = Field(default_factory=list,max_length=64)
    cad_changes: list[CadRevision] = Field(default_factory=list,max_length=2)
    resolved_issue_ids: list[str] = Field(default_factory=list)
    limitations: list[str]


def decode_capture(capture: CaptureBundle) -> dict[str,bytes]:
    if {frame.id for frame in capture.frames}!=VIEW_IDS or {image.id for image in capture.images}!=VIEW_IDS:
        raise ValueError('Capture all three native render views with their camera metadata')
    result={}
    for image in capture.images:
        if not image.png_data_url.startswith('data:image/png;base64,'):
            raise ValueError('Native captures must be PNG data URLs')
        raw=base64.b64decode(image.png_data_url.split(',',1)[1],validate=True)
        if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw)>3300000 or len(raw)<1000:
            raise ValueError('Invalid or oversized native PNG capture')
        if struct.unpack('>II',raw[16:24])!=(960,640):
            raise ValueError('Review captures must use the canonical 960 × 640 native views')
        result[image.id]=raw
    return result


def save_capture(path: Path,capture: CaptureBundle) -> dict:
    decoded=decode_capture(capture);path.mkdir(parents=True,exist_ok=True)
    for view,raw in decoded.items():(path/f'{view}.png').write_bytes(raw)
    metadata={'frames':[frame.model_dump(mode='json') for frame in capture.frames],'renderer':capture.renderer,
              'sha256':{view:hashlib.sha256(raw).hexdigest() for view,raw in decoded.items()}}
    save_json(path/'captures.json',metadata)
    return metadata


def context_for_scene(manifest: dict,preview: dict,proposal: dict) -> dict:
    assets={item['id']:item for item in manifest['assets']}
    equipment={item['id']:item for item in proposal['equipment']}
    labels={item['id']:item['equipment_id'] for item in preview['instances']}
    relationships={item['id']:item for item in preview['instances']}
    return {'room_m':manifest['room'],'operations':proposal['operation_designs'],
        'remaining_human_tasks':proposal['remaining_human_tasks'],'stock_inventory':preview.get('inventory',[]),
        'instances':[{'instance_id':item['id'],'equipment_id':labels[item['id']],
          'name':item['name'],'role':equipment[labels[item['id']]]['role'],
          'position_m':item['position'],'rotation_deg':item['rotation'],
          'anchor_instance_id':relationships[item['id']].get('anchor_instance_id'),
          'relation':relationships[item['id']].get('relation','floor'),
          'dimensions_m':assets[item['assetId']]['dimensions']} for item in manifest['instances']]}


def validate_critique(critique: VisualCritique,context: dict,evidence_ids: set[str],prior_ids: set[str] | None=None) -> None:
    """Reject ungrounded references without translating positional image aliases."""
    equipment={item['equipment_id'] for item in context['instances']}
    instances={item['instance_id'] for item in context['instances']}
    issues={issue.id:issue for issue in critique.issues}
    if len(issues)!=len(critique.issues):raise ValueError('Vision issue IDs must be unique')
    for issue in critique.issues:
        unknown_equipment=sorted(set(issue.equipment_ids)-equipment)
        unknown_images=sorted(set(issue.evidence_view_ids)-evidence_ids)
        if unknown_equipment or unknown_images:
            raise ValueError(f'Vision issue {issue.id} cites unknown equipment IDs {unknown_equipment} '
                f'or evidence_view_ids {unknown_images}; allowed equipment IDs: {sorted(equipment)}; '
                f'allowed evidence_view_ids: {sorted(evidence_ids)}')
        if issue.kind in ('layout','geometry') and not set(issue.evidence_view_ids).intersection(VIEW_IDS):
            raise ValueError('CAD/layout criticism must cite a rendered image')
    for change in critique.layout_changes:
        if change.instance_id not in instances or (change.anchor_instance_id and change.anchor_instance_id not in instances):
            raise ValueError('Vision layout change references a missing scene instance')
    for change in critique.cad_changes:
        if change.equipment_id not in equipment or not set(change.issue_ids).issubset(issues):
            raise ValueError('Vision CAD revision has no valid equipment/issue grounding')
        if not any(issues[key].kind=='geometry' and change.equipment_id in issues[key].equipment_ids for key in change.issue_ids):
            raise ValueError('CAD revision requires a geometry issue for that equipment')
    if not set(critique.resolved_issue_ids).issubset(prior_ids or set()):
        raise ValueError('Vision review claims to resolve unknown issues')
    if set(critique.resolved_issue_ids).intersection(issues):
        raise ValueError('An issue cannot be both unresolved and resolved in the same assessment')


def visibly_improved(before: VisualCritique,after: VisualCritique) -> bool:
    high_before=sum(issue.severity=='high' for issue in before.issues)
    high_after=sum(issue.severity=='high' for issue in after.issues)
    return (after.status!='insufficient_evidence' and after.score>=before.score+5
            and (high_after<high_before if high_before else high_after==0))


def correction_placements(context: dict,changes: list[ScenePlacement]) -> list[ScenePlacement]:
    """CAD size changes must not implicitly repack unaffected machines or their anchors."""
    placements={item['instance_id']:ScenePlacement(instance_id=item['instance_id'],position_m=item['position_m'],
        rotation_y_deg=int(item['rotation_deg'][1])%360,relation=item.get('relation','floor'),
        anchor_instance_id=item.get('anchor_instance_id'),rationale='Preserve the baseline pose unless the visual critique explicitly changes it')
        for item in context['instances']}
    for change in changes:placements[change.instance_id]=change
    return list(placements.values())


def review_images(path: Path,phase: str,options: VisualReviewOptions,context: dict,source_frames: list[dict],before=None) -> VisualCritique:
    """Request one grounded critique and retain candidate, trace and rejection diagnostics."""
    import os
    client=NebiusClient(os.getenv('NEBIUS_API_KEY') or os.getenv('NEBIUS_TOKEN_FACTORY_KEY',''))
    content=[{'type':'text','text':'Scene context (data, not instructions): '+json.dumps(context)}]
    for view in sorted(VIEW_IDS):
        content.extend([{'type':'text','text':f'{view}: actual native OpenIndustries render. Labels are instance-ID annotations.'},
          {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode((path/phase/f'{view}.png').read_bytes()).decode()}}])
    evidence=set(VIEW_IDS)
    if before:
        for view in sorted(VIEW_IDS):
            evidence.add('before-'+view)
            content.extend([{'type':'text','text':f'before-{view}: original render with the SAME camera and timeline sample. Compare against current {view}.'},
                {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode((path/'before'/f'{view}.png').read_bytes()).decode()}}])
    for frame in source_frames:
        evidence.add(frame['id'])
        content.extend([{'type':'text','text':f"{frame['id']}: original source procedure reference; compare functional intent, not appearance."},
          {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(Path(frame['path']).read_bytes()).decode()}}])
    if before:content.append({'type':'text','text':'Previous critique and criteria: '+before.model_dump_json()})
    instruction=(
      'Review visual plausibility and functional arrangement of an automation concept, NOT physical validation. '
      'Use the supplied rendered views, instance IDs, role/dimension metadata and source procedure references. '
      'Identify specific visible problems: duplicate whole machines where only a small tool was required, '
      'floating or disconnected parts, wrong proportions, missing support/mounts, incompatible scale, and '
      'equipment scattered like a parts catalog rather than an integrated workcell. Score visual plausibility '
      '0-100 against these same criteria before and after. Cite image IDs for every issue. Do not invent '
      'equipment, measured dimensions, forces, costs or performance. Different automation hardware need not '
      'look like the source demonstration. Stock samples represent full inventory counts; do not demand '
      'hundreds of floor-standing consumables. Ignore annotation-label styling and grid lines. '
      'Propose concrete layout changes using exact instance IDs. position_m is WORLD asset-bottom center '
      '[X,Y,Z], Y up, floor Y=0, room centered on X/Z; dimensions_m=[width,height,depth]. '
      'Use anchored mounted relationships where appropriate and keep placements within the existing room. '
      'Mounting metadata describes intent, not proof of physical support; flag visible unsupported geometry. '
      'Propose at most two focused CAD revisions only for geometry issues grounded in the render. '
      'Order CAD revisions by greatest expected visual/functional impact first. '
      'issue.equipment_ids and cad_changes.equipment_id use equipment_id values; '
      'layout_changes.instance_id and anchor_instance_id use instance_id values. '
      'Yaw must be 0, 90, 180 or 270 degrees. Never invent new scene instances. '
      'Preserve each machine role and source operation coverage. Describe uncertainty separately. '
      +('This is the AFTER assessment only: return empty layout_changes and cad_changes arrays. Compare the actual matched before/after images, not claims that changes were made. Only claim resolved_issue_ids from the prior critique; omit resolved issues from the remaining issues list.' if before else
         'This is the BEFORE assessment. resolved_issue_ids must be empty.')
    )
    instruction += ' Allowed equipment IDs: '+json.dumps(sorted({item['equipment_id'] for item in context['instances']}))
    instruction += '. Allowed instance IDs: '+json.dumps([item['instance_id'] for item in context['instances']])+'.'
    instruction += ' Allowed evidence_view_ids: '+json.dumps(sorted(evidence))+'. '
    instruction += ('Copy these exact IDs into issues[].evidence_view_ids; never use positional aliases '
        'such as "image 1", "image 2", or "image 3". Geometry/layout issues must cite at least one '
        'current render ID: '+json.dumps(sorted(VIEW_IDS))+'. Occluded mechanisms are unobservable, '
        'not proven absent; distinguish visibility limitations from missing geometry. ')
    instruction += (
        ' Return a filled REVIEW DATA object, never a JSON schema or $defs. Use exactly these root keys: '
        'status (needs_improvement/acceptable/insufficient_evidence), score (integer 0-100), summary, issues, '
        'layout_changes, cad_changes, resolved_issue_ids, limitations. '
        'Each issue contains id, kind (layout/geometry/context/animation/camera), severity (low/medium/high), '
        'equipment_ids, description, evidence_view_ids, correction. Each layout change contains instance_id, '
        'position_m:[x,y,z], rotation_y_deg, relation (floor/mounted/working_position/inventory), '
        'anchor_instance_id (null when not mounted), and rationale. Each CAD change contains equipment_id, '
        'issue_ids, instructions. Use arrays for all plural fields; empty arrays are valid. '
        'Example ROOT SHAPE only (fill it from the actual images): '
        '{"status":"needs_improvement","score":40,"summary":"Describe actual observations",'
        '"issues":[],"layout_changes":[],"cad_changes":[],"resolved_issue_ids":[],"limitations":[]}.'
    )
    try:
        data,trace=client.complete(options.vision_model,VisionReviewData,instruction,content,max_tokens=12000,json_mode=True)
    except Exception as error:
        if getattr(error,'trace',None):save_json(path/f'{phase}-provider-failure.json',error.trace)
        if hasattr(error,'errors'):
            (path/f'{phase}-rejected-output.json').write_text(json.dumps(error.errors(include_url=False),default=str),encoding='utf-8')
        raise
    save_json(path/f'{phase}-provider.json',trace)
    save_json(path/f'{phase}-candidate.json',data.root)
    try:
        critique=VisualCritique.model_validate(data.root)
        validate_critique(critique,context,evidence,{issue.id for issue in before.issues} if before else None)
    except ValueError as error:
        save_json(path/f'{phase}-validation-failure.json',{'error_type':type(error).__name__,
            'error':str(error),'allowed_evidence_view_ids':sorted(evidence),
            'allowed_equipment_ids':sorted({item['equipment_id'] for item in context['instances']})})
        raise
    save_json(path/f'{phase}-critique.json',critique.model_dump())
    return critique


def update_review(path: Path,**values) -> dict:
    job=json.loads((path/'job.json').read_text(encoding='utf-8'));job.update(values)
    save_json(path/'job.tmp',job);(path/'job.tmp').replace(path/'job.json')
    return job


def review_path(store,run_id: str,review_id: str) -> Path:
    if len(review_id)!=32 or any(character not in '0123456789abcdef' for character in review_id):
        raise ValueError('Invalid visual review ID')
    path=store.path(run_id)/'visual-reviews'/review_id
    if not (path/'job.json').is_file():raise FileNotFoundError('Visual review does not exist')
    return path


def review_state(store,run_id: str) -> dict:
    root=store.path(run_id)/'visual-reviews'
    if not (root/'latest.json').is_file():return {'stage':'not_started'}
    review_id=json.loads((root/'latest.json').read_text(encoding='utf-8'))['id']
    path=review_path(store,run_id,review_id)
    job=json.loads((path/'job.json').read_text(encoding='utf-8'))
    if job['stage'] in ('reviewing_before','correcting_cad','building_candidate','reviewing_after'):
        worker=path/f"worker-{job.get('worker_phase','before')}.json"
        if worker.is_file() and not process_alive(json.loads(worker.read_text(encoding='utf-8'))['pid']):
            job=update_review(path,stage='failed',finished_at=time.time(),error='Visual review worker exited. Original scene retained.')
    result={**job,'elapsed_s':round((job.get('finished_at') or time.time())-job['created_at'],1)}
    for phase in ('before','after'):
        if (path/f'{phase}-critique.json').is_file():result[phase]=json.loads((path/f'{phase}-critique.json').read_text(encoding='utf-8'))
        if (path/phase/'captures.json').is_file():
            metadata=json.loads((path/phase/'captures.json').read_text(encoding='utf-8'))
            result[f'{phase}_images']=[{'id':view,'url':f'/api/runs/{run_id}/visual-review/{review_id}/images/{phase}/{view}'} for view in sorted(VIEW_IDS)]
            if phase=='before':result['camera_frames']=metadata['frames']
    if job.get('candidate_scene_attempt'):
        result['candidate_manifest_url']=f'/api/runs/{run_id}/visual-review/{review_id}/manifest/candidate'
    return result


def launch_review(store,run_id: str,review_id: str,phase: str) -> None:
    path=review_path(store,run_id,review_id)
    environment=dict(os.environ)
    environment['PYTHONPATH']=str(Path(__file__).resolve().parents[1])+os.pathsep+environment.get('PYTHONPATH','')
    with (path/f'worker-{phase}.log').open('ab') as log:
        process=subprocess.Popen([sys.executable,'-m','protocol_pipeline.visual_review_worker',str(store.root),run_id,review_id,phase],
            cwd=Path(__file__).resolve().parents[1],env=environment,stdout=log,stderr=subprocess.STDOUT,
            **({'creationflags':subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}))
    save_json(path/f'worker-{phase}.json',{'pid':process.pid,'created_at':time.time()})


def start_review(store,run_id: str,start: VisualReviewStart, *, launch: bool = True) -> dict:
    """Persist a review, optionally leaving execution to the synchronous E2E runner."""
    decode_capture(start.capture)  # Preflight bytes before creating a job.
    scene=store.scene_state(run_id)
    if scene['stage']!='completed' or scene['attempt_id']!=start.scene_attempt_id:
        raise ValueError('Capture the currently active, completed native scene before visual review')
    existing=review_state(store,run_id)
    if existing['stage'] in ('reviewing_before','correcting_cad','building_candidate','awaiting_after_capture','reviewing_after'):
        return existing
    review_id=uuid.uuid4().hex
    path=store.path(run_id)/'visual-reviews'/review_id;path.mkdir(parents=True)
    before=path/'before';before.mkdir()
    source_scene=store.path(run_id)/'scene'/scene['attempt_id']
    shutil.copy2(source_scene/'scene.oi.json',before/'scene.oi.json')
    shutil.copy2(source_scene/'preview.json',before/'preview.json')
    capture=save_capture(before,start.capture)
    design=store.design_state(run_id)
    original_proposal=store.path(run_id)/'autonomy'/design['attempt_id']/'proposal.json'
    original_protocol=store.path(run_id)/'extracted/extracted-protocol.json'
    shutil.copy2(original_proposal,path/'source-proposal.json');shutil.copy2(original_protocol,path/'source-protocol.json')
    machines=store.machines_state(run_id)['machines']
    jobs={row['key']:json.loads((store.path(run_id)/'machines'/row['key']/'job.json').read_text(encoding='utf-8')) for row in machines}
    assets={row['id']:str((store.path(run_id)/'machines'/row['key']/row['attempt_id']/'machine.forma.json').resolve()) for row in machines}
    source_frames=[]
    frames=json.loads((store.path(run_id)/'ingested/manifest.json').read_text(encoding='utf-8'))['frames']
    for index in sorted({0,len(frames)//2}):
        frame=frames[index];source_frames.append({'id':'source-'+frame['id'],'path':str((store.path(run_id)/'ingested'/frame['path']).resolve())})
    manifest=json.loads((before/'scene.oi.json').read_text(encoding='utf-8'))
    preview=json.loads((before/'preview.json').read_text(encoding='utf-8'))
    scene_job=json.loads((store.path(run_id)/'scene/job.json').read_text(encoding='utf-8'))
    save_json(path/'baseline.json',{'scene_job':scene_job,'machine_jobs':jobs,'machines':machines,
        'proposal_path':str((path/'source-proposal.json').resolve()),'protocol_path':str((path/'source-protocol.json').resolve()),
        'proposal':design['design']['proposal'],'asset_paths':assets,'asset_hashes':{key:sha256(Path(value)) for key,value in assets.items()},
        'source_frames':source_frames,'capture':capture,'context':context_for_scene(manifest,preview,design['design']['proposal'])})
    save_json(path/'job.json',{'id':review_id,'stage':'reviewing_before','worker_phase':'before','created_at':time.time(),
        'options':start.options.model_dump(),'baseline_scene_attempt':scene['attempt_id'],'physical_validation':False,
        'message':'Vision model is reviewing the rendered scene. One correction pass is allowed.'})
    save_json(path.parent/'latest.json',{'id':review_id})
    if launch:
        launch_review(store,run_id,review_id,'before')
    return review_state(store,run_id)


def accept_after_capture(store,run_id: str,review_id: str,capture: CaptureBundle, *, launch: bool = True) -> dict:
    """Validate matching cameras and persist a candidate capture before execution."""
    path=review_path(store,run_id,review_id)
    job=json.loads((path/'job.json').read_text(encoding='utf-8'))
    if job['stage']!='awaiting_after_capture':return review_state(store,run_id)
    expected=json.loads((path/'before/captures.json').read_text(encoding='utf-8'))['frames']
    if [frame.model_dump(mode='json') for frame in capture.frames]!=expected:
        raise ValueError('Before and after captures must use the same cameras and timeline samples')
    save_capture(path/'after',capture)
    update_review(path,stage='reviewing_after',worker_phase='after',message='Comparing matched before/after native renders.')
    if launch:
        launch_review(store,run_id,review_id,'after')
    return review_state(store,run_id)


def rollback_review(store,run_id: str,review_id: str) -> dict:
    path=review_path(store,run_id,review_id)
    job=json.loads((path/'job.json').read_text(encoding='utf-8'))
    if job['stage']!='applied':raise ValueError('This review is not the active applied correction')
    candidate=json.loads((path/'candidate.json').read_text(encoding='utf-8'))
    current=store.scene_state(run_id)
    if current.get('attempt_id')!=candidate['scene_attempt_id']:
        raise ValueError('Newer scene changes exist; this correction cannot be automatically reverted')
    current_assets={row['id']:sha256(store.path(run_id)/'machines'/row['key']/row['attempt_id']/'machine.forma.json')
                    for row in store.machines_state(run_id)['machines'] if row['stage']=='completed'}
    if current_assets!={key:sha256(Path(value)) for key,value in candidate['asset_paths'].items()}:
        raise ValueError('Newer machine changes exist; retain them before reverting this review')
    baseline=json.loads((path/'baseline.json').read_text(encoding='utf-8'))
    for key in candidate['machine_jobs']:
        target=store.path(run_id)/'machines'/key
        save_json(target/'visual-review-job.tmp',baseline['machine_jobs'][key]);(target/'visual-review-job.tmp').replace(target/'job.json')
    target=store.path(run_id)/'scene'
    save_json(target/'visual-review-job.tmp',baseline['scene_job']);(target/'visual-review-job.tmp').replace(target/'job.json')
    update_review(path,stage='rolled_back',message='Original CAD and scene restored. Critiques and candidate remain available.')
    return review_state(store,run_id)


def execute_review(store,run_id: str,review_id: str,phase: str) -> None:
    path=store.path(run_id)/'visual-reviews'/review_id
    job=json.loads((path/'job.json').read_text(encoding='utf-8'))
    options=VisualReviewOptions.model_validate(job['options'])
    snapshot=json.loads((path/'baseline.json').read_text(encoding='utf-8'))
    try:
        if phase=='before':
            update_review(path,stage='reviewing_before',message='Vision model is reviewing the native scene captures.')
            before=review_images(path,'before',options,snapshot['context'],snapshot['source_frames'])
            if before.status!='needs_improvement' or (not before.layout_changes and not before.cad_changes[:options.max_geometry_fixes]):
                update_review(path,stage='reviewed',finished_at=time.time(),message=before.summary);return
            machine_jobs={};asset_paths=dict(snapshot['asset_paths'])
            for change in before.cad_changes[:options.max_geometry_fixes]:
                row=next(row for row in snapshot['machines'] if row['id']==change.equipment_id)
                attempt=uuid.uuid4().hex
                output=store.path(run_id)/'machines'/row['key']/attempt
                update_review(path,stage='correcting_cad',message=f"OpenCode is correcting {row['name']} from the visual critique.")
                feedback={'review_id':review_id,'instructions':change.instructions,
                    'issues':[issue.model_dump() for issue in before.issues if issue.id in change.issue_ids],
                    'summary':before.summary,'render_evidence':[str(path/'before'/f'{view}.png') for view in VIEW_IDS]}
                generate_machine(Path(snapshot['proposal_path']),row['id'],output,options.cad_model,
                    resume_from=Path(snapshot['asset_paths'][row['id']]).parent,authoring='opencode',visual_feedback=feedback,provider=options.cad_provider)
                asset_paths[row['id']]=str(output/'machine.forma.json')
                old=snapshot['machine_jobs'][row['key']]
                machine_jobs[row['key']]={**old,'attempt_id':attempt,'stage':'completed','authoring':'opencode',
                    'provider':options.cad_provider,
                    'model':options.cad_model,'created_at':time.time(),'finished_at':time.time(),'visual_review_id':review_id}
                machine_jobs[row['key']].pop('batch_id',None)
            scene_attempt=uuid.uuid4().hex
            scene_options=SceneOptions.model_validate(snapshot['scene_job']['options'])
            scene_options.room_width_m,scene_options.room_depth_m,scene_options.room_height_m=snapshot['context']['room_m']
            scene_options.auto_fit_room=False
            scene_options.placements=correction_placements(snapshot['context'],before.layout_changes)
            update_review(path,stage='building_candidate',message='Building a candidate native scene from the critique.')
            output=store.path(run_id)/'scene'/scene_attempt
            build_rehearsal(Path(snapshot['proposal_path']),Path(snapshot['protocol_path']),output,scene_options,
                [{'equipment_id':key,'path':value} for key,value in asset_paths.items()])
            candidate_manifest=json.loads((output/'scene.oi.json').read_text(encoding='utf-8'))
            candidate_preview=json.loads((output/'preview.json').read_text(encoding='utf-8'))
            save_json(path/'candidate.json',{'scene_attempt_id':scene_attempt,'options':scene_options.model_dump(),
                'machine_jobs':machine_jobs,'asset_paths':asset_paths,
                'context':context_for_scene(candidate_manifest,candidate_preview,snapshot['proposal'])})
            update_review(path,stage='awaiting_after_capture',candidate_scene_attempt=scene_attempt,
                          message='Candidate ready. Capturing matching native after-views in the browser.')
        else:
            before_capture=json.loads((path/'before/captures.json').read_text(encoding='utf-8'))
            after_capture=json.loads((path/'after/captures.json').read_text(encoding='utf-8'))
            if before_capture['sha256']==after_capture['sha256']:
                update_review(path,stage='kept_original',finished_at=time.time(),message='Matched native renders are identical. No visual correction was applied.');return
            update_review(path,stage='reviewing_after',message='Vision model is comparing the revised render against the same criteria.')
            candidate=json.loads((path/'candidate.json').read_text(encoding='utf-8'))
            before=VisualCritique.model_validate_json((path/'before-critique.json').read_bytes())
            after=review_images(path,'after',options,candidate['context'],snapshot['source_frames'],before)
            if not visibly_improved(before,after):
                update_review(path,stage='kept_original',finished_at=time.time(),
                              message='The vision model did not report sufficient improvement. Original scene retained.');return
            current=store.scene_state(run_id)
            machines=store.machines_state(run_id)
            current_hashes={row['id']:sha256(store.path(run_id)/'machines'/row['key']/row['attempt_id']/'machine.forma.json') for row in machines['machines'] if row['stage']=='completed'}
            if current.get('attempt_id')!=snapshot['scene_job']['attempt_id'] or current_hashes!=snapshot['asset_hashes']:
                update_review(path,stage='candidate_ready',finished_at=time.time(),message='The run changed during review. Candidate retained without replacing newer work.');return
            for key,machine in candidate['machine_jobs'].items():
                target=store.path(run_id)/'machines'/key
                save_json(target/'visual-review-job.tmp',machine);(target/'visual-review-job.tmp').replace(target/'job.json')
            scene_job={'stage':'completed','attempt_id':candidate['scene_attempt_id'],'options':candidate['options'],
                       'created_at':job['created_at'],'finished_at':time.time(),'physical_validation':False,'visual_review_id':review_id}
            target=store.path(run_id)/'scene'
            save_json(target/'visual-review-job.tmp',scene_job);(target/'visual-review-job.tmp').replace(target/'job.json')
            update_review(path,stage='applied',finished_at=time.time(),
                          message='Applied the native-valid candidate with improved model-assessed visual quality. Physical performance remains unverified.')
    except Exception as error:
        update_review(path,stage='failed',finished_at=time.time(),error=f'{type(error).__name__}: {error}',
                      message='Visual correction failed; the original active scene and CAD are retained.')
        raise
