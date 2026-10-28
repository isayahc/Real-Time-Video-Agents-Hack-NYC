# SPDX-License-Identifier: MPL-2.0
"""Run every workbench stage and append a self-contained, versioned snapshot."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any, Callable, Iterator
from urllib.parse import urlencode
from urllib.request import urlopen
import uuid

from .environment import load_environment
from .extraction import GMIProvider, NebiusProvider
from .lab_layout import plan_lab
from .machines import forma_runtime
from .opencode_machine import ensure_server
from . import opencode_v2
from .pipeline import sha256
from .snapshots import (E2EConfig, allocate_snapshot, atomic_json, copy_source, file_index,
                        read_json, resolve_input)
from .viewer import native_viewer_bundle
from .visual_review import (CaptureBundle, VisualReviewOptions, VisualReviewStart,
                            accept_after_capture, execute_review, review_state, save_capture, start_review)
from .web import JobStore, runtime_provenance


def preflight(config: E2EConfig, directory: Path | None = None) -> dict[str, Any]:
    """Check native tools and exact account model IDs without making inference calls."""
    for binary in ('ffmpeg', 'ffprobe', 'node'):
        if not shutil.which(binary):
            raise RuntimeError(f'Install {binary} before running E2E')
    runtime = forma_runtime()
    if not runtime['available']:
        raise RuntimeError(runtime['message'])
    for provider, model in ((NebiusProvider(), config.vision_model), (GMIProvider(), config.text_model)):
        provider.client.timeout_s = 30
        if model not in provider.client.available_models():
            raise ValueError(f'{provider.name} account does not list requested model {model}; no fallback was selected')
    url = ensure_server()
    if opencode_v2.is_v2(url):
        opencode_v2.check_model(url, directory or Path(__file__).resolve().parents[1], 'gmi', config.text_model)
    else:
        query = urlencode({'directory': str(directory or Path(__file__).resolve().parents[1])})
        with urlopen(url + '/provider?' + query, timeout=30) as response:
            providers = json.load(response)
        gmi = next((row for row in providers.get('all', []) if row.get('id') == 'gmi'), {})
        if config.text_model not in gmi.get('models', {}) or 'gmi' not in providers.get('connected', []):
            raise ValueError(f'OpenCode must have connected provider gmi and model {config.text_model}; check repository opencode.json')
    return {'status': 'passed', 'vision_provider': 'nebius', 'vision_model': config.vision_model,
            'text_provider': 'gmi', 'text_model': config.text_model,
            'model_catalogs_checked': True, 'inference_compatibility_verified': False}


@contextmanager
def native_capture() -> Iterator[Callable[[dict[str, Any], list[dict[str, Any]] | None], CaptureBundle]]:
    """Use the production native viewer in headless Chromium, with no manual clicks."""
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory(prefix='workbench-viewer-') as temporary:
        bundle = native_viewer_bundle(Path(temporary))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=['--enable-unsafe-swiftshader'])
            try:
                page = browser.new_page(viewport={'width': 960, 'height': 640})
                page.add_script_tag(path=str(bundle))
                if not page.evaluate("() => !!document.createElement('canvas').getContext('webgl2')"):
                    raise RuntimeError('Chromium cannot create a WebGL2 context')

                def capture(document: dict[str, Any], frames: list[dict[str, Any]] | None = None) -> CaptureBundle:
                    """Serialize real native renders and the exact cameras used for comparison."""
                    raw = page.evaluate('([document, frames]) => OpenIndustriesNative.captureViews(document, frames || undefined)',
                                        [document, frames])
                    return CaptureBundle.model_validate(raw)

                yield capture
            finally:
                browser.close()


def require_stage(state: dict[str, Any], expected: str = 'completed') -> dict[str, Any]:
    """Turn retained service failures into a failing script exit, never partial success."""
    if state['stage'] != expected:
        errors = [row.get('error', row['stage']) for row in state.get('machines', []) if row['stage'] != 'completed']
        raise RuntimeError(state.get('error') or state.get('message') or '; '.join(errors) or f'Unexpected stage: {state["stage"]}')
    return state


class PipelineRun:
    """Synchronous orchestration of the same services used by the browser workbench."""

    def __init__(self, root: Path, document: dict[str, Any], config: E2EConfig) -> None:
        """Create a local store; all worker artifacts live inside this version."""
        self.root, self.document, self.config = root, document, config
        self.store = JobStore(root / 'workbench', GMIProvider)
        self.run_id = uuid.uuid4().hex
        self.run = self.store.root / self.run_id
        self.run.mkdir()
        document['run_path'] = self.run.relative_to(root).as_posix()

    def stage(self, name: str, action: Callable[[], Any]) -> Any:
        """Persist stage transitions before and after execution, including failures."""
        checkpoint = {'status': 'running', 'started_at': time.time()}
        self.document['stages'][name] = checkpoint
        atomic_json(self.root / 'snapshot.json', self.document)
        print(f'[{self.root.name}] {name}', file=sys.stderr, flush=True)
        try:
            result = action()
        except BaseException as error:
            checkpoint.update(status='failed', finished_at=time.time(), error_type=type(error).__name__, error=str(error))
            raise
        else:
            checkpoint.update(status='completed', finished_at=time.time())
            return result
        finally:
            atomic_json(self.root / 'snapshot.json', self.document)

    def extract(self) -> None:
        """Sample the input video, observe through Nebius, and compile through GMI."""
        source = self.root / self.document['source']['path']
        video = self.run / source.name
        shutil.copy2(source, video)
        atomic_json(self.run / 'job.json', {
            'id': self.run_id, 'filename': video.name, 'video_file': video.name,
            'provider': 'gmi', 'vision_provider': 'nebius', 'model': self.config.text_model,
            'vision_model': self.config.vision_model, 'frame_count': self.config.frame_count,
            'created_at': time.time(), 'stage': 'queued', 'events': [], 'physical_validation': False,
            'runtime': self.document['runtime'],
        })
        self.store.slots.acquire()
        self.store.execute(self.run_id)
        require_stage(self.store.get(self.run_id))

    def design(self) -> None:
        """Generate the autonomous proposal and retain its economic assumptions."""
        atomic_json(self.run / 'autonomy/job.json', {
            'stage': 'queued', 'created_at': time.time(), 'attempt_id': uuid.uuid4().hex,
            'model': self.config.text_model, 'provider': 'gmi', 'physical_validation': False,
        })
        self.store.slots.acquire()
        self.store.execute_design(self.run_id)
        state = require_stage(self.store.design_state(self.run_id))
        atomic_json(self.run / 'autonomy/economics.json', state['economics'])

    def cad(self) -> None:
        """Author all equipment through OpenCode/GMI and validate actual OpenCAD solids."""
        state = self.store.machines_state(self.run_id)
        if not state['machines']:
            raise ValueError('Proposal contains no equipment to generate')
        for row in state['machines']:
            atomic_json(self.run / 'machines' / row['key'] / 'job.json', {
                'equipment_id': row['id'], 'stage': 'queued', 'created_at': time.time(),
                'attempt_id': uuid.uuid4().hex, 'model': self.config.text_model,
                'authoring': 'opencode', 'provider': 'gmi', 'physical_validation': False,
                'source_proposal_sha256': state['source_proposal_sha256'],
            })
        self.store.slots.acquire()
        self.store.execute_machines(self.run_id, [row['key'] for row in state['machines']])
        require_stage(self.store.machines_state(self.run_id), 'ready')

    def scene(self) -> None:
        """Build the native scene using the generated, validated CAD assets."""
        count = len(self.store.design_state(self.run_id)['design']['proposal']['operation_designs'])
        if count * self.config.scene.seconds_per_operation > 120:
            raise ValueError('Storyboard exceeds 120 seconds; reduce config.scene.seconds_per_operation')
        atomic_json(self.run / 'scene/job.json', {
            'stage': 'queued', 'created_at': time.time(), 'attempt_id': uuid.uuid4().hex,
            'options': self.config.scene.model_dump(mode='json'), 'physical_validation': False,
        })
        self.store.slots.acquire()
        self.store.execute_scene(self.run_id)
        require_stage(self.store.scene_state(self.run_id))

    def review(self, capture: Callable[..., CaptureBundle]) -> None:
        """Capture, critique, correct and recapture automatically with identical cameras."""
        outcomes = []
        for _ in range(self.config.visual_passes):
            scene = require_stage(self.store.scene_state(self.run_id))
            manifest = read_json(self.run / 'scene' / scene['attempt_id'] / 'scene.oi.json')
            state = start_review(self.store, self.run_id, VisualReviewStart(
                scene_attempt_id=scene['attempt_id'], capture=capture(manifest, None),
                options=VisualReviewOptions(vision_model=self.config.vision_model,
                                           cad_model=self.config.text_model, cad_provider='gmi')), launch=False)
            execute_review(self.store, self.run_id, state['id'], 'before')
            state = review_state(self.store, self.run_id)
            if state['stage'] == 'awaiting_after_capture':
                manifest = read_json(self.run / 'scene' / state['candidate_scene_attempt'] / 'scene.oi.json')
                accept_after_capture(self.store, self.run_id, state['id'], capture(manifest, state['camera_frames']), launch=False)
                execute_review(self.store, self.run_id, state['id'], 'after')
                state = review_state(self.store, self.run_id)
            if state['stage'] not in {'applied', 'kept_original', 'reviewed'}:
                raise RuntimeError(state.get('error') or f'Visual review did not finish: {state["stage"]}')
            outcomes.append({'id': state['id'], 'outcome': state['stage'],
                             'critique': state.get('after') or state.get('before')})
            if state['stage'] != 'applied':
                break
        atomic_json(self.run / 'visual-reviews/summary.json', {'passes': outcomes, 'physical_validation': False})

    def lab(self, capture: Callable[..., CaptureBundle]) -> None:
        """Plan and render the final lab after any accepted scene correction."""
        scene = require_stage(self.store.scene_state(self.run_id))
        folder = self.run / 'scene' / scene['attempt_id']
        design = require_stage(self.store.design_state(self.run_id))
        proposal = self.run / 'autonomy' / design['attempt_id'] / 'proposal.json'
        report, manifest = plan_lab(read_json(folder / 'scene.oi.json'), read_json(folder / 'preview.json'),
                                    read_json(proposal)['proposal'])
        report.update(source_scene_sha256=sha256(folder / 'scene.oi.json'), source_proposal_sha256=sha256(proposal))
        attempt = uuid.uuid4().hex
        output = self.run / 'lab' / attempt
        atomic_json(output / 'report.json', report)
        atomic_json(output / 'scene.oi.json', manifest)
        atomic_json(self.run / 'lab/current.json', {'attempt_id': attempt})
        save_capture(output / 'renders', capture(manifest, None))


def run_e2e(root: Path, video: Path | None = None, snapshot: Path | None = None,
            overrides: dict[str, Any] | None = None) -> Path:
    """Append one full run, inheriting settings/source from a supplied or latest snapshot."""
    root = root.resolve()
    source, parent = resolve_input(video, snapshot, root)
    config = E2EConfig.model_validate({**(parent['config'] if parent else {}), **(overrides or {})})
    output = allocate_snapshot(root)
    document: dict[str, Any] = {
        'schema_version': 1, 'kind': 'workbench-e2e', 'version': int(output.name[1:]),
        'status': 'running', 'created_at': time.time(), 'config': config.model_dump(mode='json'),
        'parent': {'version': parent['version'], 'source_sha256': parent['source']['sha256'],
                   'document_sha256': hashlib.sha256(json.dumps(parent, sort_keys=True).encode()).hexdigest()} if parent else None,
        'runtime': runtime_provenance(), 'physical_validation': False, 'stages': {},
        'rerun_policy': 'all_stages_from_saved_video; no prior model or CAD results reused',
    }
    pipeline = None
    try:
        document['source'] = copy_source(source, output / 'input')
        if source.suffix.lower() == '.zip':
            document['imported_archive_sha256'] = sha256(source)
        pipeline = PipelineRun(output, document, config)
        # Browser and native bundle also preflight before the first paid inference.
        with ExitStack() as stack:
            def prepare() -> Callable[..., CaptureBundle]:
                """Check rendering before catalogs, retaining any setup failure as a stage."""
                capture = stack.enter_context(native_capture())
                document['preflight'] = preflight(config, pipeline.run)
                return capture

            capture = pipeline.stage('preflight', prepare)
            pipeline.stage('extraction', pipeline.extract)
            pipeline.stage('proposal', pipeline.design)
            pipeline.stage('cad', pipeline.cad)
            pipeline.stage('scene', pipeline.scene)
            pipeline.stage('visual_review', lambda: pipeline.review(capture))
            pipeline.stage('lab', lambda: pipeline.lab(capture))
        document['status'] = 'completed'
    except BaseException as error:
        document.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                        error_type=type(error).__name__, error=str(error))
        print(f'Run failed; retained snapshot: {output}', file=sys.stderr)
        raise
    finally:
        if pipeline:
            pipeline.store.executor.shutdown(wait=True)
        document.update(finished_at=time.time(), files=file_index(output))
        atomic_json(output / 'snapshot.json', document)
    return output


def main() -> None:
    """Expose full runs, portable snapshot input and an inference-free setup check."""
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--video', type=Path)
    source.add_argument('--snapshot', type=Path, help='E2E directory/snapshot.json or legacy PR #50 ZIP/directory')
    parser.add_argument('--snapshots-dir', type=Path, default=Path('snapshots/e2e'))
    parser.add_argument('--config', type=Path, help='JSON settings overriding inherited snapshot settings')
    parser.add_argument('--vision-model')
    parser.add_argument('--text-model')
    parser.add_argument('--frames', type=int)
    parser.add_argument('--visual-passes', type=int)
    parser.add_argument('--check', action='store_true', help='Check tools, browser and account model catalogs without inference')
    args = parser.parse_args()
    overrides = read_json(args.config) if args.config else {}
    overrides.update({key: value for key, value in {
        'vision_model': args.vision_model, 'text_model': args.text_model,
        'frame_count': args.frames, 'visual_passes': args.visual_passes}.items() if value is not None})
    try:
        if args.check:
            parent = resolve_input(None, args.snapshot, args.snapshots_dir)[1] if args.snapshot else None
            config = E2EConfig.model_validate({**(parent['config'] if parent else {}), **overrides})
            with native_capture():
                print(json.dumps(preflight(config)))
        else:
            output = run_e2e(args.snapshots_dir, args.video, args.snapshot, overrides)
            print(json.dumps({'status': 'completed', 'snapshot': str(output / 'snapshot.json')}))
    except Exception as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
