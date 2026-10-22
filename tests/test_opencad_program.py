"""Source capability checks and real multi-body OpenCAD/OCCT regression coverage."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from protocol_pipeline.opencad_program import CadProgram, build_program, validate_program, validate_body_meshes


def program_data() -> dict[str, Any]:
    """Use a real feature-based CAD fixture, with no live inference claim."""
    source = Path(__file__).resolve().parents[1] / 'examples/opencad-authoring/fixture.py'
    return {'description': 'Deterministic mounting-plate and hollow-collar fixture',
            'python_source': source.read_text(encoding='utf-8'),
            'components': [{'id': 'mount', 'name': 'Mounting plate', 'role': 'Four-hole support'},
                           {'id': 'collar', 'name': 'Tapered collar', 'role': 'Hollow locating interface'}],
            'assumptions': ['Synthetic test dimensions; no physical assembly validation']}


@pytest.mark.parametrize('source', [
    'import os\nos.system("echo bad")',
    'from pathlib import Path',
    'from opencad import RuntimeContext',
    'open("secret")',
    'x = Part().context',
    'x = ().__class__',
    'x = getattr(Part, "export")',
    'Part().export_step("outside.step")',
])
def test_modeling_source_rejects_non_geometry_capabilities(source: str) -> None:
    """Model source cannot opt into I/O or private runtime access."""
    with pytest.raises(ValueError):
        validate_program(CadProgram.model_validate({**program_data(), 'python_source': source}))


def test_modeling_program_supports_features_and_stable_component_ids() -> None:
    """Accept feature-based source and reject duplicate export identities."""
    validate_program(CadProgram.model_validate(program_data()))
    data = program_data()
    data['components'][1]['id'] = 'mount'
    with pytest.raises(ValueError, match='unique'):
        CadProgram.model_validate(data)


def test_native_build_is_bounded_and_does_not_inherit_provider_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check the actual subprocess boundary without requiring the native runtime."""
    monkeypatch.setattr('protocol_pipeline.opencad_program.cad_adapter_path', lambda: Path('/native/cad.py'))
    monkeypatch.setenv('NEBIUS_API_KEY', 'must-not-reach-cad')
    monkeypatch.setenv('GMI_API_KEY', 'must-not-reach-cad')
    monkeypatch.setenv('DATABASE_URL', 'must-not-reach-cad')

    def run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        """Return a native rejection after checking how execution was requested."""
        assert kwargs['timeout'] == 180
        assert not {'NEBIUS_API_KEY', 'GMI_API_KEY', 'DATABASE_URL'}.intersection(kwargs['env'])
        assert command[2] == 'build'
        assert kwargs['cwd'] != tmp_path / 'attempt'
        assert Path(command[3]).parent == kwargs['cwd']
        return SimpleNamespace(returncode=1, stdout='', stderr='OCCT: invalid loft section')

    monkeypatch.setattr('protocol_pipeline.opencad_program.subprocess.run', run)
    with pytest.raises(RuntimeError, match='invalid loft section'):
        build_program(CadProgram.model_validate(program_data()), tmp_path / 'attempt')
    assert (tmp_path / 'attempt/machine.py').read_text() == program_data()['python_source']
    assert 'invalid loft' in (tmp_path / 'attempt/build.stderr.log').read_text()


def test_short_build_workspace_preserves_timeout_diagnostics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Native code sees short paths; a deep snapshot retains partial artifacts on timeout."""
    import subprocess

    output = tmp_path
    while len(str(output)) < 200:
        output = output / 'deep-snapshot'
    output = output / 'attempt'
    monkeypatch.setenv('WORKBENCH_CAD_TEMP_ROOT', str(tmp_path / 'native'))
    monkeypatch.setattr('protocol_pipeline.opencad_program.cad_adapter_path', lambda: Path('/native/cad.py'))
    workspaces = []

    def run(command: list[str], **kwargs: Any) -> None:
        """Emulate a native Windows writer with a path-length limit and a timeout."""
        work = kwargs['cwd']
        workspaces.append(work)
        assert all(len(argument) < 240 for argument in command[3:] if argument != '--tree-output')
        (work / 'partial.step').write_text('partial native output')
        raise subprocess.TimeoutExpired(command, 180, output=b'partial stdout', stderr=b'native stalled')

    monkeypatch.setattr('protocol_pipeline.opencad_program.subprocess.run', run)
    with pytest.raises(RuntimeError, match='exceeded 180 seconds'):
        build_program(CadProgram.model_validate(program_data()), output)
    assert (output / 'partial.step').read_text() == 'partial native output'
    assert (output / 'build.stderr.log').read_text() == 'native stalled'
    assert not workspaces[0].exists()


@pytest.mark.parametrize('problem', ['missing', 'duplicate', 'nan', 'index'])
def test_component_mesh_contract_rejects_partial_or_invalid_exports(problem: str) -> None:
    """Compatibility does not weaken identity, finiteness or topology validation."""
    program = CadProgram.model_validate(program_data())
    bodies = [{'id': c.id, 'mesh': {'vertices': [0, 0, 0, 1, 0, 0, 0, 1, 0], 'faces': [0, 1, 2]}}
              for c in program.components]
    if problem == 'missing':
        bodies.pop()
    elif problem == 'duplicate':
        bodies[1]['id'] = bodies[0]['id']
    elif problem == 'nan':
        bodies[0]['mesh']['vertices'][0] = float('nan')
    else:
        bodies[0]['mesh']['faces'][0] = 99
    with pytest.raises(ValueError):
        validate_body_meshes(program, bodies)


@pytest.mark.skipif(os.getenv('WORKBENCH_NATIVE_CAD_TESTS') != '1', reason='Opt-in native CAD runtime test')
def test_older_adapter_without_preview_or_multibody_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real native geometry survives an adapter exposing only its final shape."""
    import cadquery as cq
    from protocol_pipeline.cad_runtime import cad_adapter_path

    adapter = cad_adapter_path()
    legacy = tmp_path / 'legacy_adapter.py'
    legacy.write_text(
        'import os, runpy, sys\n'
        f'api = runpy.run_path({str(adapter)!r}, run_name="legacy_test_adapter")\n'
        'original = runpy.run_path\n'
        'def load_model(*args, **kwargs):\n'
        '    result = original(*args, **kwargs)\n'
        '    result.pop("FORMA_PREVIEW_BODIES", None)\n'
        '    result.pop("FORMA_EXPORT_SHAPE_IDS", None)\n'
        '    return result\n'
        'runpy.run_path = load_model\n'
        'code = api["main"]()\n'
        'sys.stdout.flush()\n'
        'sys.stderr.flush()\n'
        'os._exit(code)\n', encoding='utf-8')
    monkeypatch.setenv('FORMA_CAD_ADAPTER_PATH', str(legacy))
    output = tmp_path / 'legacy-output'
    summary = build_program(CadProgram.model_validate(program_data()), output)
    assert summary['adapter_metadata'].get('articulated_bodies') is None
    assert len(cq.importers.importStep(str(output / 'adapter.step')).val().Solids()) == 1
    assert len(cq.importers.importStep(str(output / 'machine.step')).val().Solids()) == 2
    assert {body['id'] for body in summary['articulated_bodies']} == {'mount', 'collar'}
    mount = cq.importers.importStep(str(output / 'component-mount.step')).val()
    assert not mount.isInside((-25, -15, 4))
    assert mount.isInside((0, 20, 4))


@pytest.mark.skipif(os.getenv('WORKBENCH_NATIVE_CAD_TESTS') != '1', reason='Opt-in native CAD runtime test')
def test_native_features_export_all_bodies_and_preserve_holes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the real worker with fixture inference, then reopen its native STEP solids."""
    assert importlib.util.find_spec('opencad'), 'Install the pinned Forma OpenCAD runtime'
    import cadquery as cq

    from protocol_pipeline.opencode_machine_worker import execute

    class FixtureAuthor:
        """Replace only live inference; execute real authoring, native export and Forma validation."""

        session_id = 'fixture-no-live-inference'
        provider = 'fixture'

        def complete(self, contract: type[CadProgram], instruction: str,
                     content: list[dict[str, Any]]) -> tuple[CadProgram, dict[str, Any]]:
            """Return known feature-based source through the authoring contract."""
            assert 'Part.loft' in instruction
            return contract.model_validate(program_data()), {'provenance': 'deterministic fixture; no live inference'}

    monkeypatch.setattr('protocol_pipeline.opencode_machine.OpenCodeMachineSession', lambda *args, **kwargs: FixtureAuthor())
    execute(tmp_path, {'model': 'fixture', 'equipment': {'id': 'mount-fixture', 'name': 'Mount fixture'},
                       'operations': [], 'source_proposal_sha256': 'fixture-proposal'})
    report = json.loads((tmp_path / 'machine-report.json').read_text())
    assert report['forma_schema_valid'] is True
    assert report['machine_specific_cad']['representation'] == 'opencad-python'
    assert (tmp_path / 'machine-cad-program.json').is_file()
    cad = json.loads((tmp_path / 'machine.forma.json').read_text())['project_ir']['cad_model']
    assert cad['authoring_mode'] == 'opencode-opencad-python'
    assert {mesh['shapeId'] for mesh in cad['meshes']} == {'mount', 'collar'}
    assert all(mesh['vertices'] and mesh['faces'] for mesh in cad['meshes'])
    checks = cad['validation']
    assert checks['physical_validation'] is False
    assert len(checks['components']) == 2
    assert all(item['native_valid'] for item in checks['components'])
    assembly = cq.importers.importStep(str(tmp_path / 'machine.step')).val()
    assert len(assembly.Solids()) == 2
    mount = cq.importers.importStep(str(tmp_path / 'machine-cad/1/component-mount.step')).val()
    collar = cq.importers.importStep(str(tmp_path / 'machine-cad/1/component-collar.step')).val()
    assert mount.isValid() and collar.isValid()
    assert mount.Volume() < 80 * 50 * 8 - 4 * 3.14 * 3**2 * 8
    assert not mount.isInside((-25, -15, 4))
    assert mount.isInside((0, 20, 4))
    assert not collar.isInside((0, 0, 18))
    assert collar.isInside((8, 0, 18))
    tree = (tmp_path / 'machine.tree.json').read_text()
    assert 'Through mounting hole' in tree and 'Tapered collar loft' in tree
    assert (tmp_path / 'machine.py').read_text() == program_data()['python_source']
    assert json.loads((tmp_path / 'machine-validation.json').read_text()) == checks
