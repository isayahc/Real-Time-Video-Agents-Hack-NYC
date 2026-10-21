# SPDX-License-Identifier: MPL-2.0
"""Isolated optional Forma runtime: native generation, schema and deterministic checks."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .design import DesignJob, write_json


def unwrap_project(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve supported Forma wrappers to the native Hardware IR object."""
    for key in ('project_ir', 'hardware_ir'):
        if isinstance(payload.get(key), dict):
            return payload[key]
    return payload


def execute(output: Path) -> None:
    """Call Forma Core directly with persistence disabled, then validate its result."""
    from forma_core import __version__
    from forma_core.config import config
    from forma_core.validation import build_validation_summary, validate_project
    from forma_core.workspaces.projects.models import HardwareIntermediateRepresentation

    job = DesignJob.model_validate_json((output / 'build-input.json').read_text())
    if job.mode == 'replay':
        raw = json.loads(Path(job.replay_project).read_text())
        project = HardwareIntermediateRepresentation.model_validate(unwrap_project(raw))
    else:
        from forma_core.generation import generate_project_with_workflow
        from forma_core.cli.main import _cli_generation_environment
        simulation = job.mode == 'simulation'
        settings = {**_cli_generation_environment(simulation=simulation),
                    'FORMA_DEV_MODE': 'true' if simulation else 'false',
                    'FORMA_DEVELOPMENT_MODE': 'true' if simulation else 'false',
                    'FORMA_DEPLOYMENT_MODE': 'local'}
        with config.override(settings):
            project = generate_project_with_workflow('default',
                (output / 'synthesis-prompt.txt').read_text(),
                provider_name='simulation' if simulation else job.provider,
                model_name=None if simulation else job.model, persist_project=False)
        metadata = project.assembly_metadata or {}
        if not simulation and (metadata.get('generation_error') or metadata.get('status') == 'failed'
                               or metadata.get('fallback_mode') or metadata.get('workflow_fallback')
                               or metadata.get('runtime_provider') == 'simulation'):
            raise RuntimeError('Live generation returned failed or fallback output')
    summary = build_validation_summary(validate_project(project))
    document = {'format': 'form-project', 'version': 1,
        'project_id': (project.assembly_metadata or {}).get('project_id') or 'protocol-apparatus',
        'project_ir': project.model_dump(mode='json')}
    write_json(output / 'apparatus.forma.json', document)
    write_json(output / 'forma-result.json', {'core_version': __version__, 'mode': job.mode,
        'generation_called': job.mode != 'replay', 'schema_valid': True,
        'deterministic_is_valid': not bool(summary.critical),
        'validation': summary.model_dump(mode='json'),
        'components': len(project.components), 'bom_lines': len(project.bom or []),
        'physical_validation': False})


def main() -> None:
    """Execute the private worker entry point without emitting provider diagnostics."""
    try:
        execute(Path(sys.argv[1]))
    except Exception:
        # The parent reports stage failure; provider messages may contain secrets.
        sys.exit(1)


if __name__ == '__main__':
    main()
