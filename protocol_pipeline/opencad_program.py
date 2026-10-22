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
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from pydantic import Field, model_validator

from .models import StrictModel
from .cad_runtime import cad_adapter_path

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
        mesh = part.context.kernel.tessellate(part.shape_id, deflection=0.1)
        bodies.append({**component.model_dump(), 'shape_id': part.shape_id,
                       'coordinate_system': 'z-up', 'units': 'mm',
                       'mesh': {'shapeId': part.shape_id, 'name': component.name,
                                'vertices': mesh.vertices, 'faces': mesh.faces}})
        checks.append({'id': component.id, 'native_valid': True, 'solids': len(solids),
                       'volume_mm3': volume, 'dimensions_mm': dimensions})
    validate_body_meshes(program, bodies)
    assembly = cq.Compound.makeCompound(native_shapes)
    cq.exporters.export(assembly, str(directory / 'machine.step'))
    cq.exporters.export(assembly, str(directory / 'machine.stl'))
    reopened = cq.importers.importStep(str(directory / 'machine.step')).val()
    if not reopened.isValid() or len(reopened.Solids()) != sum(item['solids'] for item in checks):
        raise ValueError('Native STEP round-trip did not preserve every component solid')
    (directory / 'machine-bodies.json').write_text(json.dumps({
        'schema_version': 1, 'source': 'native OpenCAD tessellation of validated component solids',
        'bodies': bodies}, indent=2, allow_nan=False), encoding='utf-8')
    (directory / 'machine-validation.json').write_text(json.dumps({
        'status': 'native_geometry_valid', 'components': checks, 'physical_validation': False,
        'scope': 'OCCT solid validity, positive volume, finite dimensions, component identity and native exports; '
                 'assembly compatibility, collisions, reachability and fabrication remain unverified.'}, indent=2), encoding='utf-8')
    # Newer Forma adapters also use these globals. Our artifact contract does not
    # depend on the installed adapter recognizing its optional preview extension.
    return {'FORMA_EXPORT_SHAPE_IDS': shape_ids, 'FORMA_PREVIEW_BODIES': bodies}


def validate_body_meshes(program: CadProgram, bodies: Any) -> None:
    """Require one finite, indexed native triangle mesh per declared component."""
    if not isinstance(bodies, list) or any(not isinstance(body, dict) for body in bodies):
        raise ValueError('OpenCAD body metadata must be a list of component objects')
    if len(bodies) != len(program.components) or {body.get('id') for body in bodies} != {c.id for c in program.components}:
        raise ValueError('OpenCAD did not produce a native mesh for every component ID')
    for body in bodies:
        mesh = body.get('mesh') or {}
        vertices, faces = mesh.get('vertices'), mesh.get('faces')
        if (not isinstance(vertices, list) or len(vertices) < 9 or len(vertices) % 3
                or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in vertices)
                or not isinstance(faces, list) or len(faces) < 3 or len(faces) % 3
                or any(not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= len(vertices) // 3 for i in faces)):
            raise ValueError(f'{body["id"]}: OpenCAD native mesh must contain finite vertices and valid triangle indices')


def build_program(program: CadProgram, directory: Path) -> dict[str, Any]:
    """Build in a short native workspace, then retain all artifacts and diagnostics."""
    validate_program(program)
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    program_path = directory / 'program.json'
    program_path.write_text(program.model_dump_json(indent=2), encoding='utf-8')
    (directory / 'machine.py').write_text(program.python_source, encoding='utf-8')
    wrapper = directory / '_export.py'
    wrapper.write_text('from pathlib import Path\n'
                       'from protocol_pipeline.opencad_program import execute_program\n'
                       'root = Path(__file__).resolve().parent\n'
                       'globals().update(execute_program(root / "program.json", root))\n',
                       encoding='utf-8')
    # Provider credentials and unrelated app configuration never enter generated CAD execution.
    runtime_keys = ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'HOME', 'USERPROFILE',
                    'LOCALAPPDATA', 'APPDATA', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'LD_LIBRARY_PATH',
                    'DYLD_LIBRARY_PATH', 'PYTHONHOME')
    environment = {key: os.environ[key] for key in runtime_keys if key in os.environ}
    environment['PYTHONPATH'] = os.pathsep.join(filter(None, [
        str(Path(__file__).resolve().parents[1]), os.environ.get('PYTHONPATH', '')]))
    environment['PYTHONIOENCODING'] = 'utf-8'
    adapter = cad_adapter_path()
    # Native OCCT/tree writers need short paths even if Python can access a long
    # Windows snapshot path. Never run native exporters inside the snapshot tree.
    temporary_root = os.getenv('WORKBENCH_CAD_TEMP_ROOT')
    if temporary_root:
        Path(temporary_root).expanduser().mkdir(parents=True, exist_ok=True)
        temporary_root = str(Path(temporary_root).expanduser().resolve())
    with tempfile.TemporaryDirectory(prefix='ocad-', dir=temporary_root) as temporary:
        work = Path(temporary).resolve()
        for source in (program_path, directory / 'machine.py', wrapper):
            shutil.copyfile(source, work / source.name)
        command = [sys.executable, str(adapter), 'build', str(work / '_export.py'),
                   str(work / 'adapter.step'), '--tree-output', str(work / 'machine.tree.json')]
        try:
            result = subprocess.run(command, cwd=work, env=environment, capture_output=True,
                                    text=True, encoding='utf-8', timeout=BUILD_TIMEOUT_SECONDS, check=False)
            (work / 'build.stdout.log').write_text(result.stdout, encoding='utf-8')
            (work / 'build.stderr.log').write_text(result.stderr, encoding='utf-8')
        except subprocess.TimeoutExpired as error:
            (work / 'build-error.txt').write_text('OpenCAD build exceeded 180 seconds', encoding='utf-8')
            for name, content in (('stdout', error.stdout), ('stderr', error.stderr)):
                if content:
                    text = content.decode('utf-8', errors='replace') if isinstance(content, bytes) else content
                    (work / f'build.{name}.log').write_text(text, encoding='utf-8')
            raise RuntimeError('OpenCAD build exceeded 180 seconds; simplify the failing operations') from error
        finally:
            # Include partial outputs on failures/timeouts, before temp cleanup.
            for artifact in work.iterdir():
                if artifact.is_file():
                    shutil.copyfile(artifact, directory / artifact.name)
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
    bodies_path = directory / 'machine-bodies.json'
    if not bodies_path.is_file():
        raise ValueError('OpenCAD did not produce native component tessellation metadata')
    bodies = json.loads(bodies_path.read_text(encoding='utf-8'))['bodies']
    validate_body_meshes(program, bodies)
    return {'valid': True, 'path': str(directory / 'machine.step'),
            'tree_path': str(directory / 'machine.tree.json'), 'model_path': str(wrapper),
            'opencad_version': summary.get('opencad_version'), 'features': summary.get('features'),
            'articulated_bodies': bodies, 'adapter_metadata': summary,
            'mesh_source': 'native OpenCAD tessellation; independent of adapter preview metadata'}
