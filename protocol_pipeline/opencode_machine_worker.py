# SPDX-License-Identifier: MPL-2.0
"""OpenCode/Nebius authors the mechanical concept; native Forma validates and exports it."""
import json
from pathlib import Path
from datetime import datetime, timezone


def execute(output: Path, source: dict) -> None:
    from forma_core import __version__
    from forma_core.workspaces.projects.models import HardwareIR
    from .design import write_json
    from .machine_cad import author_machine_cad
    from .opencode_machine import OpenCodeMachineSession

    def progress(stage, label, status='started', session_id=None):
        payload={'stage':stage,'label':label,'status':status,'at':datetime.now(timezone.utc).isoformat(), 'session_id':session_id}
        (output/'progress.tmp').write_text(json.dumps(payload),encoding='utf-8')
        (output/'progress.tmp').replace(output/'progress.json')
        print(json.dumps(payload),flush=True)
    def cad_progress(event):
        progress(event.step_id,event.label,event.status,author.session_id)

    progress('opencode_start',f"Connecting OpenCode to {source.get('provider','nebius')} authoring model")
    resume=None
    if source.get('visual_feedback') and source.get('resume_from'):
        previous=Path(source['resume_from'])
        if (previous/'opencode-session.json').is_file():
            resume=json.loads((previous/'opencode-session.json').read_text(encoding='utf-8'))
            resume.setdefault('directory',str(previous.resolve()))
    author=OpenCodeMachineSession(output,source['model'],source['equipment'],resume=resume,provider=source.get('provider','nebius'))
    progress('opencode_authoring',f'OpenCode session {author.session_id}: authoring {source["equipment"]["name"]}')
    # Reuse a hardware project only as context; OpenCode still authors and validates the CAD.
    project=None
    if source.get('resume_from'):
        previous=Path(source['resume_from'])
        candidate=previous/'machine.forma.json'
        if candidate.is_file():
            project=HardwareIR.model_validate_json(json.dumps(json.loads(candidate.read_text(encoding='utf-8'))['project_ir']))
    if project is None:
        project=HardwareIR(is_valid=False,assembly_metadata={'status':'mechanical_concept',
            'electrical_design_evaluated':False,'costs':'unknown; see the separate Step 5 planning scenario'})
    result=author_machine_cad(project,source,output,cad_progress,author=author)
    project.assembly_metadata.update(authoring='opencode',opencode_session_id=author.session_id,
                                     source_proposal_sha256=source['source_proposal_sha256'])
    # A real native Forma schema validation follows the CAD export.
    project=HardwareIR.model_validate(project.model_dump())
    write_json(output/'machine.forma.json',{'format':'form-project','version':1,'title':source['equipment']['name'],
        'project_id':source['equipment']['id'],'project_ir':project.model_dump(mode='json')})
    write_json(output/'machine-report.json',{'status':'cad_generated','equipment_id':source['equipment']['id'],
        'equipment_name':source['equipment']['name'],'core_version':__version__,'generation_called':True,
        'mode':'live','authoring':'opencode','provider':author.provider,'transport':f'OpenCode → {author.provider} → native Forma CAD validation/export',
        'requested_model':source['model'],'opencode_session_id':author.session_id,
        'source_proposal_sha256':source['source_proposal_sha256'],'cad_meshes':len(project.cad_model['meshes']),
        'components':len(project.components),'machine_specific_cad':result,
        'forma_schema_valid':True,'electrical_design_evaluated':False,'native_forma_workflow_called':False,
        'deterministic_is_valid':False,'validation_scope':'Mechanical CAD concept; electrical design not evaluated',
        'physical_validation':False})
    progress('completed','OpenCode-authored Forma CAD is ready for OpenIndustries','completed')
