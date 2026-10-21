# SPDX-License-Identifier: MPL-2.0
"""Local video workbench: durable jobs, real extraction, and evidence playback.

Run one server process on loopback. This is a trusted-user local workbench, not
an authenticated multi-user hosting service. Provider credentials stay server-side.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import platform
import subprocess
from importlib.metadata import PackageNotFoundError, version
import shutil
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .extraction import ExtractionProvider, create_provider, extract_protocol
from .autonomy import AutonomyProposal, evaluate_proposal, generate_proposal
from .compiler import ProtocolSpecification
from .environment import load_environment
from .pipeline import NEBIUS_REQUEST_TIMEOUT_S, NebiusHTTPError, extract_frames, save_json, sha256
from .models import StrictModel
from .model_config import DEFAULT_COMPILER_MODEL, DEFAULT_VISION_MODEL, model_presets

STATIC = Path(__file__).with_name("web_static")
MAX_UPLOAD = 100 * 1024 * 1024
TERMINAL = {"completed", "failed"}
logger = logging.getLogger(__name__)


class CostEdits(StrictModel):
    values: dict[str, float | None]

ARTIFACTS = (
    "source-manifest.json", "observations.json", "extracted-protocol.json",
    "extraction-summary.json", "extraction-failure.json", "compiled/report.md",
    "compiled/process-graph.json", "compiled/apparatus-requirements.json",
    "compiled/process-input.json", "compiled/summary.json",
    "provider-candidate-1.json", "provider-candidate-2.json",
)


def read_json(path: Path) -> Any:
    """Read a UTF-8 run artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def ingest_video(video: Path, output: Path, count: int) -> None:
    """Sample an uploaded video without manufacturing annotation ground truth."""
    output.mkdir(parents=True, exist_ok=False)
    frames = extract_frames(video, output, count)
    save_json(output / "manifest.json", {
        "schema_version": 1, "video_id": video.parent.name,
        "video_filename": video.name, "video_sha256": sha256(video),
        "frames": [frame.model_dump() for frame in frames],
        "annotation_ground_truth_sent_to_model": False,
        "sampling_limitations": "Sparse frames may miss actions; inferred intervals require review.",
    })


def runtime_provenance() -> dict[str, Any]:
    """Record reproducibility metadata without copying environment credentials."""
    repository = Path(__file__).resolve().parents[1]
    revision = None
    dirty = None
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository,
                                  capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=repository,
                                    capture_output=True, text=True, check=True, timeout=5).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    packages = {}
    for name in ("pydantic", "fastapi", "starlette", "uvicorn"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "not installed"
    return {"git_commit": revision, "working_tree_dirty": dirty,
            "python": platform.python_version(), "packages": packages}


class JobStore:
    """Persist isolated runs and execute at most one inference job at a time."""

    def __init__(self, root: Path, provider_factory: Callable[[], ExtractionProvider]) -> None:
        """Create a local store and retain a provider factory for each new run."""
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.provider_factory = provider_factory
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-extraction")
        self.slots = threading.BoundedSemaphore(4)
        self.pending: list[str] = []

    def path(self, run_id: str) -> Path:
        """Resolve a generated run ID, rejecting arbitrary filesystem paths."""
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise HTTPException(404, "Run not found")
        path = self.root / run_id
        if not (path / "job.json").is_file():
            raise HTTPException(404, "Run not found")
        return path

    def get(self, run_id: str) -> dict[str, Any]:
        """Read a job atomically with respect to worker updates."""
        with self.lock:
            job = read_json(self.path(run_id) / "job.json")
            job["queue_position"] = self.pending.index(run_id) + 1 if run_id in self.pending else 0
        now = job.get("finished_at") or time.time()
        job["elapsed_s"] = round(now - job["created_at"], 1)
        events = job.get("events", [])
        job["stage_elapsed_s"] = round(now - (events[-1]["at"] if events else job["created_at"]), 1)
        job["sampled_frames"] = []
        manifest = self.path(run_id) / "ingested/manifest.json"
        if manifest.is_file():
            try:
                job["sampled_frames"] = [
                    {"id": frame["id"], "timestamp_s": frame["timestamp_s"],
                     "url": f"/api/runs/{run_id}/frames/{frame['id']}"}
                    for frame in read_json(manifest)["frames"]
                ]
            except (OSError, json.JSONDecodeError):
                # The first poll can overlap the initial manifest write.
                pass
        stage = job["stage"]
        job["progress_message"] = {
            "queued": f"Waiting for the analysis worker. Queue position: {job['queue_position']}. Runs execute one at a time.",
            "ingesting_frames": f"Decoding video and sampling {job.get('frame_count', '')} frames with FFmpeg.",
            "extracting_observations": f"Waiting for Nebius vision model {job.get('vision_model', '')}. No model response yet; this request has a {NEBIUS_REQUEST_TIMEOUT_S}-second timeout.",
            "extracting_protocol": f"Observations received. Waiting for compiler model {job.get('model', '')} to return a protocol ({NEBIUS_REQUEST_TIMEOUT_S}-second request timeout).",
            "correcting_protocol": "The compiler returned an invalid source citation. Requesting one correction against the original observed actions.",
            "compiling": "Validating the protocol and writing apparatus, resource and report artifacts.",
            "completed": "Analysis completed. Results and evidence are ready below.",
            "failed": job.get("error", "Analysis failed."),
        }.get(stage, stage)
        return job

    def update(self, run_id: str, **values: Any) -> None:
        """Replace metadata atomically so polling never observes half-written JSON."""
        with self.lock:
            path = self.path(run_id)
            job = read_json(path / "job.json")
            previous = job["stage"]
            stage_started = job["events"][-1]["at"] if job["events"] else job["created_at"]
            job.update(values)
            if "stage" in values:
                job["events"].append({"stage": values["stage"], "at": time.time()})
            save_json(path / "job.tmp", job)
            (path / "job.tmp").replace(path / "job.json")
            if "stage" in values:
                logger.info("run=%s stage=%s previous=%s previous_duration_s=%.1f elapsed_s=%.1f",
                            run_id, values["stage"], previous, time.time() - stage_started,
                            time.time() - job["created_at"])

    def recover(self) -> None:
        """Mark interrupted jobs failed on startup; never silently repeat paid calls."""
        for path in self.root.glob("*/job.json"):
            job = read_json(path)
            if job["stage"] not in TERMINAL:
                self.update(job["id"], stage="failed", finished_at=time.time(),
                             error="Server restarted before this run completed. Start a new run to retry.")
            design_job = path.parent / 'autonomy/job.json'
            if design_job.is_file() and read_json(design_job)['stage'] not in TERMINAL:
                self.update_design(job['id'], stage='failed', finished_at=time.time(),
                                   error='Server restarted during design generation. Retry Step 5 to make a new request.')

    def update_design(self, run_id: str, **values: Any) -> None:
        with self.lock:
            path = self.path(run_id) / 'autonomy'
            job = read_json(path / 'job.json')
            job.update(values)
            save_json(path / 'job.tmp', job)
            (path / 'job.tmp').replace(path / 'job.json')
            logger.info('run=%s autonomy_stage=%s elapsed_s=%.1f', run_id, job['stage'], time.time() - job['created_at'])

    def design_state(self, run_id: str) -> dict[str, Any]:
        """Expose a distinct design stage without altering extraction success or its artifacts."""
        with self.lock:
            path = self.path(run_id) / 'autonomy'
            if not (path / 'job.json').is_file():
                return {'stage': 'not_started'}
            job = read_json(path / 'job.json')
            job['elapsed_s'] = round((job.get('finished_at') or time.time()) - job['created_at'], 1)
            if job['stage'] != 'completed':
                return job
            design = read_json(path / job['attempt_id'] / 'proposal.json')
            protocol_path = self.path(run_id) / 'extracted/extracted-protocol.json'
            if design['source_protocol_sha256'] != sha256(protocol_path):
                raise HTTPException(409, 'Source protocol changed; the saved design requires regeneration')
            proposal = AutonomyProposal.model_validate(design['proposal'])
            overrides = read_json(path / 'cost-overrides.json')['values'] if (path / 'cost-overrides.json').is_file() else {}
            economics = evaluate_proposal(proposal, ProtocolSpecification.model_validate_json(protocol_path.read_bytes()), overrides)
            return {**job, 'design': design, 'economics': economics}

    def execute_design(self, run_id: str) -> None:
        try:
            state = self.design_state(run_id)
            self.update_design(run_id, stage='designing')
            generate_proposal(self.provider_factory(), state['model'],
                              self.path(run_id) / 'extracted/extracted-protocol.json',
                              self.path(run_id) / 'autonomy' / state['attempt_id'])
            self.update_design(run_id, stage='completed', finished_at=time.time())
        except Exception as error:
            self.update_design(run_id, stage='failed', finished_at=time.time(),
                               error=f'{type(error).__name__}: {error}')
            logger.exception('run=%s autonomous design failed', run_id)
        finally:
            self.slots.release()

    def execute(self, run_id: str) -> None:
        """Run ingestion and extraction, retaining evidence on either outcome."""
        try:
            with self.lock:
                if run_id in self.pending:
                    self.pending.remove(run_id)
            job = self.get(run_id)
            path = self.path(run_id)
            provider = self.provider_factory()
            self.update(run_id, provider=provider.name, live_inference=provider.live, stage="ingesting_frames")
            ingest_video(path / job["video_file"], path / "ingested", job["frame_count"])
            extract_protocol(provider, job["model"], path / "extracted", run=path / "ingested",
                             vision_model=job["vision_model"],
                             progress=lambda stage: self.update(run_id, stage=stage))
            self.update(run_id, stage="completed", finished_at=time.time())
        except Exception as error:
            stage = self.get(run_id)["stage"]
            message = f"Failed during {stage}: {type(error).__name__}: {error}"
            if isinstance(error, TimeoutError):
                message = (f"Timed out during {stage} after {self.get(run_id)['stage_elapsed_s']}s. "
                           "The request did not finish before its timeout. No result was produced; "
                           "check the selected model and provider availability before retrying.")
            if isinstance(error, NebiusHTTPError) and error.status_code in {400, 403, 404, 422}:
                field = "Vision model" if stage == "extracting_observations" else "Compiler model"
                message = (f"{field} request was rejected by Nebius (HTTP {error.status_code}). "
                           f"The model may be unavailable or incompatible, or your account may lack access. "
                           f"Enter an available compatible model in the {field.lower()} field and start a new run.")
            self.update(run_id, stage="failed", finished_at=time.time(), error_type=type(error).__name__,
                         error=message, failed_stage=stage)
            logger.error("run=%s failed_stage=%s error_type=%s http_status=%s detail=%s artifacts=%s",
                         run_id, stage, type(error).__name__, getattr(error, "status_code", None),
                         message, self.path(run_id), exc_info=True)
        finally:
            self.slots.release()

    def results(self, run_id: str) -> dict[str, Any]:
        """Expose only completed artifacts; map operation evidence to real frames."""
        job = self.get(run_id)
        path = self.path(run_id)
        if job["stage"] != "completed":
            raise HTTPException(409, "Results are available only after successful compilation")
        output = path / "extracted"
        spec = read_json(output / "extracted-protocol.json")
        graph = read_json(output / "observations.json")["graph"]
        frames = read_json(path / "ingested/manifest.json")["frames"]
        frame_map = {frame["id"]: frame for frame in frames}
        actions = {action["id"]: action for action in graph["actions"]}
        for operation in spec["operations"]:
            evidence = []
            for ref in operation["source_refs"]:
                action = actions.get(ref.removeprefix("action:")) if ref.startswith("action:") else None
                if action:
                    for frame_id in action["evidence_frame_ids"]:
                        frame = frame_map[frame_id]
                        evidence.append({"action_id": action["id"], "frame_id": frame_id,
                                         "timestamp_s": frame["timestamp_s"],
                                         "url": f"/api/runs/{run_id}/frames/{frame_id}"})
            operation["evidence"] = evidence
        return {"job": job, "protocol": spec, "observations": graph,
                "summary": read_json(output / "extraction-summary.json"),
                "apparatus": read_json(output / "compiled/apparatus-requirements.json"),
                "process_graph": read_json(output / "compiled/process-graph.json"),
                "resource_template": read_json(output / "compiled/process-input.json"),
                "accounting": read_json(output / "compiled/summary.json")["accounting"],
                "report": (output / "compiled/report.md").read_text(encoding="utf-8"),
                "downloads": [name for name in ARTIFACTS if (output / name).is_file()]}


def create_app(root: Path | None = None,
               provider_factory: Callable[[], ExtractionProvider] | None = None) -> FastAPI:
    """Build a loopback workbench; injection supports deterministic transport tests."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_environment()
    store = JobStore(root or Path(os.getenv("WORKBENCH_RUNS", "runs/workbench")), provider_factory or (lambda: create_provider("nebius")))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Recover interrupted runs and finish workers before shutdown."""
        store.recover()
        yield
        store.executor.shutdown(wait=True)

    app = FastAPI(title="Procedure Workbench", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next: Callable[..., Any]) -> Any:
        """Reject cross-origin writes and add safe browser response defaults."""
        if request.method == "POST":
            origin = request.headers.get("origin")
            expected = str(request.base_url).rstrip("/")
            if request.headers.get("x-workbench-request") != "1" or (origin and origin != expected):
                return JSONResponse({"detail": "Use the local workbench to start a run"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; media-src 'self' blob:; frame-ancestors 'none'; object-src 'none'"
        return response

    @app.get("/")
    def index() -> FileResponse:
        """Serve the application shell."""
        return FileResponse(STATIC / "index.html")

    @app.get("/assets/{name}")
    def asset(name: str) -> FileResponse:
        """Serve only the two known static application assets."""
        if name not in {"app.js", "autonomy.js", "style.css"}:
            raise HTTPException(404)
        return FileResponse(STATIC / name)

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        """Report readiness without exposing secret values."""
        return {"credentials_available": bool(os.getenv("NEBIUS_API_KEY") or os.getenv("NEBIUS_TOKEN_FACTORY_KEY")),
                "ffmpeg_available": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
                **model_presets(),
                "presets": {"model": DEFAULT_COMPILER_MODEL, "vision_model": DEFAULT_VISION_MODEL},
                "provider": "nebius", "max_upload_bytes": MAX_UPLOAD}

    @app.get("/api/runs")
    def runs() -> list[dict[str, Any]]:
        """List stored runs, newest first."""
        return sorted([store.get(p.parent.name) for p in store.root.glob("*/job.json")],
                      key=lambda job: job["created_at"], reverse=True)

    @app.post("/api/runs", status_code=202)
    async def start(request: Request, filename: str = Query(min_length=1, max_length=200),
                    model: str = Query(min_length=1, max_length=200),
                    vision_model: str = Query(min_length=1, max_length=200),
                    frame_count: int = Query(default=8, ge=2, le=24)) -> dict[str, Any]:
        """Stream a bounded raw video upload to a unique run and queue analysis."""
        suffix = Path(filename).suffix.lower()
        if suffix not in {".mp4", ".webm", ".mov"} or not model.strip() or not vision_model.strip():
            raise HTTPException(422, "Supply MP4, WebM or MOV and explicit model IDs")
        if provider_factory is None and not (os.getenv("NEBIUS_API_KEY") or os.getenv("NEBIUS_TOKEN_FACTORY_KEY")):
            raise HTTPException(503, "Set NEBIUS_API_KEY or NEBIUS_TOKEN_FACTORY_KEY on the server first")
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise HTTPException(503, "Install ffmpeg and ffprobe on the server first")
        if not store.slots.acquire(blocking=False):
            raise HTTPException(429, "Four runs are already active or uploading; wait before retrying")
        run_id = uuid.uuid4().hex
        path = store.root / run_id
        path.mkdir()
        try:
            size = 0
            with (path / ("source" + suffix)).open("xb") as destination:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, "Video exceeds the 100 MiB limit")
                    destination.write(chunk)
            if not size:
                raise HTTPException(422, "Video is empty")
            now = time.time()
            job = {"id": run_id, "filename": filename, "video_file": "source" + suffix,
                   "model": model.strip(), "vision_model": vision_model.strip(), "frame_count": frame_count,
                   "created_at": now, "stage": "queued", "events": [{"stage": "queued", "at": now}],
                   "live_inference": None, "physical_validation": False,
                   "runtime": runtime_provenance()}
            save_json(path / "job.json", job)
            with store.lock:
                store.pending.append(run_id)
                logger.info("run=%s stage=queued queue_position=%s frames=%s vision_model=%r compiler_model=%r upload_bytes=%s",
                            run_id, len(store.pending), frame_count, vision_model.strip(), model.strip(), size)
                store.executor.submit(store.execute, run_id)
            return job
        except BaseException:
            with store.lock:
                if run_id in store.pending:
                    store.pending.remove(run_id)
            shutil.rmtree(path, ignore_errors=True)
            store.slots.release()
            raise

    @app.get("/api/runs/{run_id}")
    def status(run_id: str) -> dict[str, Any]:
        """Read actual stage and timing metadata."""
        return store.get(run_id)

    @app.get("/api/runs/{run_id}/results")
    def results(run_id: str) -> dict[str, Any]:
        """Return validated completed results."""
        return store.results(run_id)

    @app.get('/api/runs/{run_id}/autonomy')
    def autonomy_status(run_id: str) -> dict[str, Any]:
        return store.design_state(run_id)

    @app.post('/api/runs/{run_id}/autonomy', status_code=202)
    def start_autonomy(run_id: str, model: str = Query(min_length=1, max_length=200),
                       retry: bool = False) -> dict[str, Any]:
        if not model.strip():
            raise HTTPException(422, 'Choose an explicit design model')
        if store.get(run_id)['stage'] != 'completed':
            raise HTTPException(409, 'Complete extraction before generating the autonomous design')
        if provider_factory is None and not (os.getenv('NEBIUS_API_KEY') or os.getenv('NEBIUS_TOKEN_FACTORY_KEY')):
            raise HTTPException(503, 'Set NEBIUS_API_KEY or NEBIUS_TOKEN_FACTORY_KEY first')
        with store.lock:
            state = store.design_state(run_id)
            if state['stage'] != 'not_started' and (state['stage'] != 'failed' or not retry):
                return state
            if not store.slots.acquire(blocking=False):
                raise HTTPException(429, 'The analysis queue is full; wait before generating a design')
            try:
                path = store.path(run_id) / 'autonomy'
                path.mkdir(exist_ok=True)
                job = {'stage': 'queued', 'created_at': time.time(), 'attempt_id': uuid.uuid4().hex,
                       'model': model.strip(), 'physical_validation': False}
                save_json(path / 'job.json', job)
                store.executor.submit(store.execute_design, run_id)
                return job
            except BaseException:
                store.slots.release()
                raise

    @app.post('/api/runs/{run_id}/autonomy/costs')
    def edit_costs(run_id: str, edits: CostEdits) -> dict[str, Any]:
        with store.lock:
            state = store.design_state(run_id)
            if state['stage'] != 'completed':
                raise HTTPException(409, 'Generate the autonomous design before editing its costs')
            try:
                economics = evaluate_proposal(AutonomyProposal.model_validate(state['design']['proposal']),
                    ProtocolSpecification.model_validate_json((store.path(run_id) / 'extracted/extracted-protocol.json').read_bytes()),
                    edits.values)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            path = store.path(run_id) / 'autonomy'
            revision = {'values': edits.values, 'basis': 'user_assumptions', 'updated_at': time.time()}
            save_json(path / ('cost-revision-' + uuid.uuid4().hex + '.json'), revision)
            save_json(path / 'cost-overrides.tmp', revision)
            (path / 'cost-overrides.tmp').replace(path / 'cost-overrides.json')
            return economics

    @app.get('/api/runs/{run_id}/autonomy/export')
    def export_design(run_id: str) -> JSONResponse:
        state = store.design_state(run_id)
        if state['stage'] != 'completed':
            raise HTTPException(409, 'Generate the design before exporting it')
        return JSONResponse(state, headers={'Content-Disposition': f'attachment; filename="{run_id}-autonomous-design.json"'})

    @app.get("/api/runs/{run_id}/video")
    def video(run_id: str) -> FileResponse:
        """Serve the run's original video with byte-range support for seeking."""
        job = store.get(run_id)
        return FileResponse(store.path(run_id) / job["video_file"])

    @app.get("/api/runs/{run_id}/frames/{frame_id}")
    def frame(run_id: str, frame_id: str) -> FileResponse:
        """Resolve a frame only through its evidence manifest."""
        path = store.path(run_id) / "ingested"
        if (path / "manifest.json").is_file():
            for item in read_json(path / "manifest.json")["frames"]:
                if item["id"] == frame_id:
                    return FileResponse(path / item["path"], media_type="image/jpeg")
        raise HTTPException(404, "Frame not found")

    @app.get("/api/runs/{run_id}/artifacts/{name:path}")
    def artifact(run_id: str, name: str) -> FileResponse:
        """Download only allowlisted artifacts, never arbitrary server files."""
        path = store.path(run_id) / "extracted" / name
        if name not in ARTIFACTS or not path.is_file():
            raise HTTPException(404, "Artifact not found")
        return FileResponse(path, filename=path.name)

    @app.get("/api/runs/{run_id}/bundle")
    def bundle(run_id: str) -> FileResponse:
        """Package completed source and evidence with exact-byte checksums."""
        job = store.get(run_id)
        if job["stage"] != "completed":
            raise HTTPException(409, "Complete a run before exporting its evidence")
        path = store.path(run_id)
        with store.lock:
            destination = path / "evidence.zip"
            if not destination.exists():
                files = [path / job["video_file"], path / "job.json", path / "ingested/manifest.json"]
                files += sorted((path / "ingested/frames").glob("*.jpg"))
                files += [path / "extracted" / name for name in ARTIFACTS if (path / "extracted" / name).is_file()]
                checksums = {file.relative_to(path).as_posix(): sha256(file) for file in files}
                with zipfile.ZipFile(path / "evidence.tmp", "w", zipfile.ZIP_DEFLATED) as archive:
                    for file in files:
                        archive.write(file, file.relative_to(path).as_posix())
                    archive.writestr("checksums.json", json.dumps(checksums, indent=2))
                    archive.writestr("README.txt", "Contains the uploaded source video and model output. Review source permissions and content before sharing. Integration evidence is not semantic or physical validation.\n")
                (path / "evidence.tmp").replace(destination)
        return FileResponse(destination, filename=f"{run_id}-evidence.zip")

    return app


def main() -> None:
    """Start a single local server with a durable run directory."""
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--runs", type=Path, default=Path("runs/workbench"))
    parser.add_argument("--reload", action="store_true", help="Automatically reload backend code during development")
    args = parser.parse_args()
    if args.reload:
        os.environ["WORKBENCH_RUNS"] = str(args.runs.resolve())
        uvicorn.run("protocol_pipeline.web:create_app", factory=True, reload=True,
                    reload_dirs=[str(Path(__file__).parent)], host="127.0.0.1", port=args.port)
    else:
        uvicorn.run(create_app(args.runs), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

