# SPDX-License-Identifier: MPL-2.0
"""Generate machine CAD through OpenCode authoring or Forma's native hardware workflow."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal

from pydantic import Field

from .autonomy import AutonomyProposal
from .cad_runtime import cad_adapter_path, forma_source
from .design import write_json
from .models import StrictModel
from .pipeline import sha256


class MachineOptions(StrictModel):
    model: str = Field(min_length=1, max_length=200)
    authoring: Literal['opencode','forma'] = 'opencode'
    provider: Literal['nebius','gmi'] = 'nebius'


def machine_key(equipment_id: str) -> str:
    return hashlib.sha256(equipment_id.encode()).hexdigest()[:24]


def process_alive(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def forma_runtime() -> dict:
    """Check installed geometry packages and the adapter used by actual native builds."""
    installed = importlib.util.find_spec('forma_core') is not None
    source = forma_source()
    try:
        adapter = cad_adapter_path()
    except ValueError as error:
        return {'available': False, 'source_root': str(source) if (source / 'forma_core').is_dir() else None,
                'cad_adapter': None, 'message': str(error)}
    ready = installed and importlib.util.find_spec('opencad') is not None and importlib.util.find_spec('cadquery') is not None
    return {'available': ready, 'source_root': str(source) if (source / 'forma_core').is_dir() else None,
            'cad_adapter': str(adapter) if adapter.is_file() else None,
            'message': 'Forma Core and its native CAD adapter are available.' if ready else
                       'Forma Core, OpenCAD, CadQuery and the Forma cad.py adapter are required. Set FORMA_ROOT or FORMA_CAD_ADAPTER_PATH if needed.'}


def generate_machine(proposal_path: Path, equipment_id: str, output: Path, model: str,
                     resume_from: Path | None = None, authoring: str = 'opencode', visual_feedback: dict | None = None,
                     provider: str = 'nebius') -> dict:
    if not forma_runtime()['available']:
        raise ValueError(forma_runtime()['message'])
    if authoring != 'opencode':
        key=(os.getenv('GMI_API_KEY') or os.getenv('GMI_CLOUD_API_KEY') or os.getenv('GMICLOUD_API_KEY')) if provider=='gmi' else (os.getenv('NEBIUS_API_KEY') or os.getenv('NEBIUS_TOKEN_FACTORY_KEY'))
        if not key:raise ValueError(f'Set server credentials for {provider} before Forma generation')
    document = json.loads(proposal_path.read_text(encoding='utf-8'))
    proposal = AutonomyProposal.model_validate(document['proposal'])
    equipment = next((item for item in proposal.equipment if item.id == equipment_id), None)
    if equipment is None:
        raise ValueError('Equipment does not belong to this autonomous proposal')
    output.mkdir(parents=True, exist_ok=False)
    operations = [op.model_dump() for op in proposal.operation_designs if equipment_id in op.equipment_ids]
    write_json(output / 'machine-input.json', {
        'equipment': equipment.model_dump(), 'operations': operations, 'proposal_title': proposal.title,
        'assumptions': proposal.assumptions, 'limitations': proposal.limitations, 'model': model.strip(),
        'source_proposal_sha256': sha256(proposal_path),
        'authoring': authoring,
        'provider':provider,
        'design_scope':proposal.design_scope,
        'machine_requirements':[item.model_dump() for item in proposal.machine_requirements],
        'component_bill_of_materials':[item.model_dump() for item in proposal.component_bill_of_materials],
        'visual_feedback':visual_feedback,
        'resume_from': str(resume_from.resolve()) if resume_from and resume_from.is_dir() else None,
    })
    environment = dict(os.environ)
    runtime = forma_runtime()
    environment['FORMA_CAD_ADAPTER_PATH'] = runtime['cad_adapter']
    environment['PYTHONUNBUFFERED'] = '1'
    roots = [str(Path(__file__).resolve().parents[1])]
    # FORMA_ROOT locates the hardware adapter, not a replacement Python package.
    # Prepending that checkout shadows the installed/pinned Forma used by preflight
    # and in-process tests, and may expose an incompatible development API.
    if environment.get('PYTHONPATH'):
        roots.append(environment['PYTHONPATH'])
    environment['PYTHONPATH'] = os.pathsep.join(roots)
    result = subprocess.run([sys.executable, '-m', 'protocol_pipeline.machine_worker', str(output.resolve())],
                            cwd=output, env=environment, capture_output=True, text=True, encoding='utf-8',
                            timeout=1800, check=False)
    (output / 'worker.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    if result.returncode:
        failure = output / 'machine-failure.json'
        detail = json.loads(failure.read_text(encoding='utf-8'))['error'] if failure.is_file() else result.stderr.strip()
        raise RuntimeError(f'Forma machine generation failed (worker exit {result.returncode}): {detail or "Native worker exited without a diagnostic; inspect its retained log"}')
    report = json.loads((output / 'machine-report.json').read_text(encoding='utf-8'))
    raw = json.loads((output / 'machine.forma.json').read_text(encoding='utf-8'))
    ir = raw.get('project_ir', raw)
    meshes = (ir.get('cad_model') or {}).get('meshes', [])
    if not meshes or not any(mesh.get('vertices') and mesh.get('faces') for mesh in meshes):
        raise ValueError('Forma returned no CAD mesh. This machine is not ready for the OpenIndustries scene.')
    return report
