# SPDX-License-Identifier: MPL-2.0
"""Compile model-authored OpenCAD Python with a controlled modeling API and native checks.

This local authoring worker is not a security sandbox for hostile Python. It limits
source capabilities, omits provider credentials from the CAD process and bounds build
time. Multi-tenant deployments must additionally provide OS/container isolation.
"""
from __future__ import annotations

import ast
import builtins
import inspect
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from pydantic import Field, model_validator

from .models import StrictModel

MODELING_METHODS = frozenset({
    'box', 'cylinder', 'sphere', 'cone', 'torus', 'extrude', 'revolve', 'loft', 'sweep',
    'union', 'cut', 'intersect', 'fillet', 'chamfer', 'shell', 'draft', 'offset',
    'linear_pattern', 'circular_pattern', 'mirror', 'translate', 'select_faces',
    'line', 'rect', 'arc', 'circle', 'build',
})
MATH_NAMES = frozenset(name for name in dir(math) if not name.startswith('_'))
COLLECTION_METHODS = frozenset({'append', 'extend', 'items', 'keys', 'values', 'get', 'copy'})
BUILTIN_NAMES = ('abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'float', 'int', 'len',
                 'list', 'max', 'min', 'range', 'round', 'set', 'sorted', 'str', 'sum',
                 'tuple', 'zip', 'ValueError')
BUILD_TIMEOUT_SECONDS = 180


class CadComponent(StrictModel):
    """Stable identity for one independently inspectable physical body."""

    id: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1)


class CadProgram(StrictModel):
    """Actual modeling source plus component identities, not a shape vocabulary."""

    description: str = Field(min_length=1)
    python_source: str = Field(min_length=1, max_length=60000)
    components: list[CadComponent] = Field(min_length=1, max_length=128)
    assumptions: list[str] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_components(self) -> CadProgram:
        """Prevent ambiguous body identity in scene selection and export."""
        if len({component.id for component in self.components}) != len(self.components):
            raise ValueError('CAD component IDs must be unique')
        return self


def validate_program(program: CadProgram) -> None:
    """Check Python syntax and restrict the source to geometry and numeric helpers."""
    tree = ast.parse(program.python_source, filename='machine.py')
    nodes = list(ast.walk(tree))
    if len(nodes) > 20000:
        raise ValueError('OpenCAD source exceeds the supported syntax budget')
    helpers = {node.name for node in nodes if isinstance(node, ast.FunctionDef)}
    callable_names = set(BUILTIN_NAMES) | helpers | {'Part', 'Sketch'}
    attributes = MODELING_METHODS | MATH_NAMES | COLLECTION_METHODS | {'shape_id', 'feature_id'}
    for node in nodes:
        if isinstance(node, ast.Import):
            if any(alias.name != 'math' or alias.asname for alias in node.names):
                raise ValueError('Only import math and from opencad import Part, Sketch are supported')
        if isinstance(node, ast.ImportFrom):
            allowed = {'opencad': {'Part', 'Sketch'}, 'math': MATH_NAMES,
                       '__future__': {'annotations'}}.get(node.module or '', set())
            if node.level or any(alias.name not in allowed or alias.asname for alias in node.names):
                raise ValueError('Unsupported import in OpenCAD source')
            if node.module == 'math':
                callable_names.update(alias.name for alias in node.names)
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.With, ast.AsyncWith,
                             ast.Global, ast.Nonlocal)):
            raise ValueError(f'{type(node).__name__} is not part of the CAD modeling API')
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            raise ValueError('CAD helper functions must not use decorators')
        if isinstance(node, (ast.Name, ast.arg)) and (node.id if isinstance(node, ast.Name) else node.arg).startswith('__'):
            raise ValueError('Private runtime access is not part of the CAD modeling API')
        if isinstance(node, ast.Attribute):
            if node.attr not in attributes or not isinstance(node.ctx, ast.Load):
                raise ValueError(f'Unsupported CAD attribute: {node.attr}; use the supplied OpenCAD API')
        if isinstance(node, ast.keyword) and node.arg == 'context':
            raise ValueError('Use the worker-provided OpenCAD context')
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in callable_names:
                    raise ValueError(f'Unsupported CAD call: {node.func.id}')
            elif not isinstance(node.func, ast.Attribute):
                raise ValueError('CAD calls must use named helpers or supported modeling methods')
    compile(tree, 'machine.py', 'exec')


def cad_api_reference() -> str:
    """Expose signatures from the installed OpenCAD version to avoid invented APIs."""
    import opencad
    from opencad import Part, Sketch

    lines = [f'Installed OpenCAD {opencad.__version__}. Geometry API:']
    for cls in (Part, Sketch):
        lines.append(f'{cls.__name__}{inspect.signature(cls)}')
        for name in sorted(MODELING_METHODS):
            member = getattr(cls, name, None)
            if member is not None:
                lines.append(f'{cls.__name__}.{name}{inspect.signature(member)}: {inspect.getdoc(member) or ""}')
    lines.append('Part.box is centered at the modeling origin. Sketch.rect uses its lower-left origin. '
                 'Sketch.circle(subtract=True) creates a hole in an enclosing profile. '
                 'parts must map each declared component ID to its final Part. '
                 'Temporary cutters must not be included. All components share the same millimeter/Z-up frame.')
    return '\n'.join(lines)


def _model_import(name: str, globals: Any = None, locals: Any = None,
                  fromlist: tuple[str, ...] = (), level: int = 0) -> Any:
    """Restrict imports even when executing the already-checked model source."""
    if name not in ('opencad', 'math', '__future__') or level:
        raise ValueError('Only modeling imports are available')
    return builtins.__import__(name, globals, locals, fromlist, level)


def execute_program(program_path: Path, directory: Path) -> dict[str, Any]:
    """Run inside Forma's native context and export checked bodies for its adapter."""
    import cadquery as cq
    from opencad import Part

    program = CadProgram.model_validate_json(program_path.read_bytes())
    validate_program(program)
    scope: dict[str, Any] = {'__builtins__': {
        **{name: getattr(builtins, name) for name in BUILTIN_NAMES}, '__import__': _model_import}}
    exec(compile(program.python_source, 'machine.py', 'exec'), scope)
    parts = scope.get('parts')
    if not isinstance(parts, dict) or set(parts) != {component.id for component in program.components}:
        raise ValueError('parts must contain exactly the declared component IDs')
    shape_ids: list[str] = []
    bodies: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    native_shapes = []
    for component in program.components:
        part = parts[component.id]
        if not isinstance(part, Part) or not part.shape_id:
            raise ValueError(f'{component.id}: expected a constructed OpenCAD Part')
        if part.shape_id in shape_ids:
            raise ValueError(f'{component.id}: multiple component IDs reference the same final shape')
        native = part.context.kernel.get_native_shape(part.shape_id)
        shape = cq.Shape(native)
        solids, volume, bounds = shape.Solids(), shape.Volume(), shape.BoundingBox()
        dimensions = [bounds.xlen, bounds.ylen, bounds.zlen]
        extents = [bounds.xmin, bounds.xmax, bounds.ymin, bounds.ymax, bounds.zmin, bounds.zmax]
        if not shape.isValid() or not solids or not math.isfinite(volume) or volume <= 0:
            raise ValueError(f'{component.id}: OpenCAD body must contain valid positive-volume native solids')
        if any(not math.isfinite(value) or value <= 0 or value > 10000 for value in dimensions):
            raise ValueError(f'{component.id}: CAD dimensions must be in (0, 10000] mm')
        if any(not math.isfinite(value) or abs(value) > 10000 for value in extents):
            raise ValueError(f'{component.id}: CAD placement is outside supported bounds')
        part.export_step(str(directory / f'component-{component.id}.step'))
        part.export_stl(str(directory / f'component-{component.id}.stl'))
        native_shapes.append(shape)
        shape_ids.append(part.shape_id)
        bodies.append({**component.model_dump(), 'shape_id': part.shape_id})
        checks.append({'id': component.id, 'native_valid': True, 'solids': len(solids),
                       'volume_mm3': volume, 'dimensions_mm': dimensions})
    cq.exporters.export(cq.Compound.makeCompound(native_shapes), str(directory / 'machine.stl'))
    (directory / 'machine-validation.json').write_text(json.dumps({
        'status': 'native_geometry_valid', 'components': checks, 'physical_validation': False,
        'scope': 'OCCT solid validity, positive volume, finite dimensions, component identity and native exports; '
                 'assembly compatibility, collisions, reachability and fabrication remain unverified.'}, indent=2), encoding='utf-8')
    return {'FORMA_EXPORT_SHAPE_IDS': shape_ids, 'FORMA_PREVIEW_BODIES': bodies}


def build_program(program: CadProgram, directory: Path) -> dict[str, Any]:
    """Compile once through Forma, retaining the real errors and named-body meshes."""
    from forma_core.workspaces.projects.cad_generation import _adapter_path

    validate_program(program)
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    program_path = directory / 'program.json'
    program_path.write_text(program.model_dump_json(indent=2), encoding='utf-8')
    (directory / 'machine.py').write_text(program.python_source, encoding='utf-8')
    wrapper = directory / '_export.py'
    wrapper.write_text('from pathlib import Path\n'
                       'from protocol_pipeline.opencad_program import execute_program\n'
                       f'globals().update(execute_program(Path({str(program_path)!r}), Path({str(directory)!r})))\n',
                       encoding='utf-8')
    # Provider credentials and unrelated app configuration never enter generated CAD execution.
    runtime_keys = ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'HOME', 'USERPROFILE',
                    'LOCALAPPDATA', 'APPDATA', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'LD_LIBRARY_PATH',
                    'DYLD_LIBRARY_PATH', 'PYTHONHOME')
    environment = {key: os.environ[key] for key in runtime_keys if key in os.environ}
    environment['PYTHONPATH'] = os.pathsep.join(filter(None, [
        str(Path(__file__).resolve().parents[1]), os.environ.get('PYTHONPATH', '')]))
    environment['PYTHONIOENCODING'] = 'utf-8'
    command = [sys.executable, str(_adapter_path()), 'build', str(wrapper),
               str(directory / 'machine.step'), '--tree-output', str(directory / 'machine.tree.json')]
    try:
        result = subprocess.run(command, cwd=directory, env=environment, capture_output=True,
                                text=True, encoding='utf-8', timeout=BUILD_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as error:
        (directory / 'build-error.txt').write_text('OpenCAD build exceeded 180 seconds', encoding='utf-8')
        raise RuntimeError('OpenCAD build exceeded 180 seconds; simplify the failing operations') from error
    (directory / 'build.stdout.log').write_text(result.stdout, encoding='utf-8')
    (directory / 'build.stderr.log').write_text(result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(f'OpenCAD native build failed: {(result.stderr or result.stdout)[-6000:]}')
    try:
        summary = json.loads(result.stdout)
    except ValueError as error:
        raise ValueError('OpenCAD adapter returned invalid build metadata') from error
    if not isinstance(summary, dict) or not summary.get('valid'):
        raise ValueError('OpenCAD adapter did not validate the assembly export')
    for name in ('machine.step', 'machine.stl', 'machine.tree.json', 'machine-validation.json'):
        if not (directory / name).is_file() or (directory / name).stat().st_size == 0:
            raise ValueError(f'OpenCAD did not produce {name}')
    bodies = summary.get('articulated_bodies') or []
    if len(bodies) != len(program.components) or any(
        not body.get('mesh', {}).get('vertices') or not body.get('mesh', {}).get('faces') for body in bodies
    ):
        raise ValueError('OpenCAD did not produce a native mesh for every component')
    return summary
