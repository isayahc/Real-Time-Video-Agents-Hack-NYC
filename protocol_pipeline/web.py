"""Local video workbench: durable jobs, real extraction, and evidence playback.

Run one server process on loopback. This is a trusted-user local workbench, not
an authenticated multi-user hosting service. Provider credentials stay server-side.
"""
from __future__ import annotations

import argparse
import json
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
from .environment import load_environment
from .pipeline import NebiusHTTPError, extract_frames, save_json, sha256

STATIC = Path(__file__).with_name("web_static")
MAX_UPLOAD = 100 * 1024 * 1024
DEFAULT_VISION_MODEL = "Qwen/Qwen2.5-VL-72B-Instruct"
TERMINAL = {"completed", "failed"}
ARTIFACTS = (
    "source-manifest.json", "observations.json", "extracted-protocol.json",
    "extraction-summary.json", "extraction-failure.json", "compiled/report.md",
    "compiled/process-graph.json", "compiled/apparatus-requirements.json",
    "compiled/process-input.json", "compiled/summary.json",
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
        job["elapsed_s"] = round((job.get("finished_at") or time.time()) - job["created_at"], 1)
        return job

    def update(self, run_id: str, **values: Any) -> None:
        """Replace metadata atomically so polling never observes half-written JSON."""
        with self.lock:
            path = self.path(run_id)
            job = read_json(path / "job.json")
            job.update(values)
            if "stage" in values:
                job["events"].append({"stage": values["stage"], "at": time.time()})
            save_json(path / "job.tmp", job)
            (path / "job.tmp").replace(path / "job.json")

    def recover(self) -> None:
        """Mark interrupted jobs failed on startup; never silently repeat paid calls."""
        for path in self.root.glob("*/job.json"):
            job = read_json(path)
            if job["stage"] not in TERMINAL:
                self.update(job["id"], stage="failed", finished_at=time.time(),
                            error="Server restarted before this run completed. Start a new run to retry.")

    def execute(self, run_id: str) -> None:
        """Run ingestion and extraction, retaining evidence on either outcome."""
        try:
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
            # Provider/validation exceptions can contain source content or credentials.
            # Preserve the failure type/stage, never raw exception text in the UI.
            stage = self.get(run_id)["stage"]
            message = f"Failed during {stage}. Check video decoding, model access and server credentials; inspect retained artifacts. No successful result is claimed."
            if isinstance(error, NebiusHTTPError) and error.status_code in {400, 403, 404, 422}:
                field = "Vision model" if stage == "extracting_observations" else "Compiler model"
                message = (f"{field} request was rejected by Nebius (HTTP {error.status_code}). "
                           f"The model may be unavailable or incompatible, or your account may lack access. "
                           f"Enter an available compatible model in the {field.lower()} field and start a new run.")
            self.update(run_id, stage="failed", finished_at=time.time(), error_type=type(error).__name__,
                        error=message)
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
                "report": (output / "compiled/report.md").read_text(encoding="utf-8"),
                "downloads": [name for name in ARTIFACTS if (output / name).is_file()]}


def create_app(root: Path | None = None,
               provider_factory: Callable[[], ExtractionProvider] | None = None) -> FastAPI:
    """Build a loopback workbench; injection supports deterministic transport tests."""
    load_environment()
    store = JobStore(root or Path("runs/workbench"), provider_factory or (lambda: create_provider("nebius")))

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
        if name not in {"app.js", "style.css"}:
            raise HTTPException(404)
        return FileResponse(STATIC / name)

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        """Report readiness without exposing secret values."""
        return {"credentials_available": bool(os.getenv("NEBIUS_API_KEY") or os.getenv("NEBIUS_TOKEN_FACTORY_KEY")),
                "ffmpeg_available": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
                "model": os.getenv("NEBIUS_COMPILER_MODEL", "Qwen/Qwen3-235B-A22B-Instruct-2507"),
                "vision_model": os.getenv("NEBIUS_VISION_MODEL", "").strip() or DEFAULT_VISION_MODEL,
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
            store.executor.submit(store.execute, run_id)
            return job
        except BaseException:
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
                checksums = {str(file.relative_to(path)): sha256(file) for file in files}
                with zipfile.ZipFile(path / "evidence.tmp", "w", zipfile.ZIP_DEFLATED) as archive:
                    for file in files:
                        archive.write(file, str(file.relative_to(path)))
                    archive.writestr("checksums.json", json.dumps(checksums, indent=2))
                    archive.writestr("README.txt", "Contains the uploaded source video and model output. Review source permissions and content before sharing. Integration evidence is not semantic or physical validation.\n")
                (path / "evidence.tmp").replace(destination)
        return FileResponse(destination, filename=f"{run_id}-evidence.zip")

    return app


def main() -> None:
    """Start a single local server with a durable run directory."""
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--runs", type=Path, default=Path("runs/workbench"))
    args = parser.parse_args()
    uvicorn.run(create_app(args.runs), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

