# SPDX-License-Identifier: MPL-2.0
"""Native OpenIndustries rehearsal scenes, separate from cost and physical evidence."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import Field

from .autonomy import AutonomyProposal
from .compiler import ProtocolSpecification
from .design import SceneRequest, write_json
from .models import StrictModel
from .pipeline import sha256


class ScenePlacement(StrictModel):
    instance_id: str = Field(min_length=1,max_length=128)
    position_m: tuple[float,float,float]
    rotation_y_deg: Literal[0,90,180,270] = 0
    relation: Literal['floor','mounted','working_position','inventory'] = 'floor'
    anchor_instance_id: str | None = None
    rationale: str = Field(min_length=1)


class SceneOptions(StrictModel):
    room_width_m: float = Field(default=6, ge=1, le=100)
    room_depth_m: float = Field(default=5, ge=1, le=100)
    room_height_m: float = Field(default=3, ge=1, le=100)
    seconds_per_operation: float = Field(default=3, ge=.5, le=10)
    auto_fit_room: bool = True
    expand_stock_quantities: bool = False
    placements: list[ScenePlacement] = Field(default_factory=list,max_length=1000)


class RoomLayoutError(ValueError):
    def __init__(self, layout: dict):
        self.layout = layout
        super().__init__(layout['message'])


def openindustries_runtime() -> dict:
    """Resolve an explicitly configured or conventional sibling checkout; never install it silently."""
    configured = os.getenv('OPENINDUSTRIES_ROOT') or os.getenv('OI_ROOT')
    candidates = [Path(configured)] if configured else [
        Path(__file__).resolve().parents[2] / 'OpenIndustries',
        Path(__file__).resolve().parents[2] / 'Open-Industries',
        Path(__file__).resolve().parents[2] / 'open-industries',
    ]
    for root in candidates:
        if ((root / 'src/lib/workspace.ts').is_file() and (root / 'src/lib/form.ts').is_file()
                and (root / 'node_modules/tsx/dist/loader.mjs').is_file() and shutil.which('node')):
            return {'available': True, 'root': str(root.resolve()),
                    'message': 'OpenIndustries native scene and keyframe APIs are available.'}
    return {'available': False, 'root': None,
            'message': 'Set OPENINDUSTRIES_ROOT to a compatible OpenIndustries checkout with npm dependencies installed. Node.js is required.'}


def build_rehearsal(proposal_path: Path, protocol_path: Path, output: Path,
                    options: SceneOptions, machine_assets: list[dict] | None = None) -> dict:
    """Build and round-trip a portable scene with real native keyframes and sampled poses."""
    runtime = openindustries_runtime()
    if not runtime['available']:
        raise ValueError(runtime['message'])
    design = json.loads(proposal_path.read_text(encoding='utf-8'))
    proposal = AutonomyProposal.model_validate(design['proposal'])
    protocol = ProtocolSpecification.model_validate_json(protocol_path.read_bytes())
    if design['source_protocol_sha256'] != sha256(protocol_path):
        raise ValueError('The design source protocol has changed; regenerate the design first')
    assets = machine_assets or []
    if {item['equipment_id'] for item in assets} != {item.id for item in proposal.equipment} or len(assets) != len(proposal.equipment):
        raise ValueError('Generate a Forma machine CAD asset for every equipment line in Step 6. Placeholder geometry is not accepted.')
    for item in assets:
        path = Path(item['path'])
        document = json.loads(path.read_text(encoding='utf-8'))
        ir = document.get('project_ir', document.get('hardware_ir', document))
        meshes = (ir.get('cad_model') or {}).get('meshes', [])
        if not meshes or not any(mesh.get('vertices') and mesh.get('faces') for mesh in meshes):
            raise ValueError(f"{item['equipment_id']} has no Forma CAD mesh; render dimensions and envelope boxes are not accepted")
        item['path'] = str(path.resolve())
        item['sha256'] = sha256(path)
    duration = len(proposal.operation_designs) * options.seconds_per_operation
    if duration > 120:
        raise ValueError('OpenIndustries timelines are limited to 120 seconds; reduce seconds per operation')
    room = SceneRequest(name=proposal.title, room_m=(options.room_width_m, options.room_depth_m, options.room_height_m))
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'scene-input.json', {
        'schema_version': 1, 'proposal': proposal.model_dump(),
        'protocol_operations': [operation.model_dump() for operation in protocol.operations],
        'room_m': room.room_m, 'seconds_per_operation': options.seconds_per_operation,
        'auto_fit_room': options.auto_fit_room, 'expand_stock_quantities': options.expand_stock_quantities,
        'placements':[placement.model_dump() for placement in options.placements],
        'source_proposal_sha256': sha256(proposal_path), 'source_protocol_sha256': sha256(protocol_path),
        'machine_assets': assets,
        'geometry_basis': 'generated_forma_cad_meshes',
        'timing_basis': 'user_selected_storyboard_timing_not_measured_cycle_time',
    })
    root = Path(runtime['root'])
    command = [shutil.which('node'), '--import', (root / 'node_modules/tsx/dist/loader.mjs').as_uri(),
               str(Path(__file__).with_name('scene_bridge.mts')), str(root), str(output.resolve())]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=60, check=False)
    if result.returncode:
        if (output / 'layout-report.json').is_file():
            layout=json.loads((output/'layout-report.json').read_text(encoding='utf-8'))
            if not layout.get('fits'):
                raise RoomLayoutError(layout)
        raise RuntimeError('OpenIndustries scene builder failed: ' + (result.stderr or result.stdout).strip())
    return json.loads((output / 'scene-report.json').read_text(encoding='utf-8'))
