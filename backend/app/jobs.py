"""Background work: the ingest/analysis pipeline and clip exports.

Jobs run in a small thread pool. State is written to the project store, and the
frontend simply polls GET /api/projects/{id}.

Because the pool lives in memory, a server restart kills running jobs. `recover_interrupted()`
runs at startup and puts them back in the queue, so nothing stays stuck on "analyzing".
"""
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from . import config, store
from .models import Clip, Project
from .services import analysis, ingest, media, segmentation, tracking
from .services.render import ExportCancelled, render_clip

log = logging.getLogger("clipper.jobs")
_pool = ThreadPoolExecutor(max_workers=config.WORKER_THREADS, thread_name_prefix="clipper")

_PROCESSING = ("queued", "downloading", "preparing", "analyzing")
_cancel_lock = threading.Lock()
_cancelled: set[tuple[str, str]] = set()  # (project_id, clip_id) of exports the user asked to stop


def _throttled(update: Callable[[float], None], every: float = 0.5) -> Callable[[float], None]:
    """Wrap a progress callback so we don't rewrite project.json hundreds of times per second."""
    last = [0.0]

    def inner(value: float) -> None:
        now = time.monotonic()
        if value >= 1.0 or now - last[0] >= every:
            last[0] = now
            update(value)
    return inner


def _set(project_id: str, **fields) -> None:
    def mutate(p: Project) -> None:
        for key, value in fields.items():
            setattr(p, key, value)
    store.update(project_id, mutate)


# --------------------------------------------------------------------------
# Ingest + analysis
# --------------------------------------------------------------------------

def submit_pipeline(project_id: str, youtube_url: Optional[str] = None) -> None:
    _pool.submit(_run_pipeline, project_id, youtube_url)


def source_path(project_id: str) -> Path:
    return store.project_dir(project_id) / "source.mp4"


def proxy_path(project_id: str) -> Path:
    return store.project_dir(project_id) / "proxy.mp4"


def _run_pipeline(project_id: str, youtube_url: Optional[str]) -> None:
    folder = store.project_dir(project_id)
    try:
        media.require_binaries()
        project = store.get(project_id)
        source = _find_source(folder)

        if youtube_url:
            if source is not None and project.duration > 0:
                # A previous attempt already downloaded and read this file (duration is only saved after
                # that), so a retry or a restart doesn't download a multi-GB video twice.
                log.info("Reusing the downloaded video for %s", project_id)
            else:
                _set(project_id, status="downloading", progress=0.0, message="Downloading the video...")
                source, title = ingest.download_youtube(
                    youtube_url, folder, project.quality,
                    _throttled(lambda v: _set(project_id, progress=v)),
                )
                _set(project_id, title=title)
        elif source is None:
            raise media.MediaError("The uploaded file is missing.")

        info = media.probe(source)
        if info.width <= info.height:
            raise media.MediaError("This looks like a vertical video. Please use a horizontal (16:9) video.")
        if info.duration > config.MAX_VIDEO_MINUTES * 60:
            raise media.MediaError(f"This video is longer than {config.MAX_VIDEO_MINUTES} minutes.")
        _set(project_id, duration=info.duration, width=info.width, height=info.height, fps=info.fps,
             video_codec=info.codec, video_kbps=round(info.bitrate / 1000))

        _set(project_id, status="preparing", progress=0.0, message="Preparing the preview...")
        media.make_proxy(source, proxy_path(project_id), info.duration,
                         _throttled(lambda v: _set(project_id, progress=v)))

        _set(project_id, status="analyzing", progress=0.0, message="Finding the best moments and tracking faces...")
        result = analysis.analyze(
            proxy_path(project_id), info.width, info.height, info.duration,
            _throttled(lambda v: _set(project_id, progress=v * 0.9)),
        )
        silences = media.detect_silences(proxy_path(project_id)) if info.has_audio else []
        crop_path, mode = tracking.build_crop_path(result, info.duration, info.width, info.height)

        candidates = segmentation.build_candidates(result.cuts, silences)
        spans = segmentation.segment(
            info.duration, candidates,
            config.DEFAULT_TARGET_LEN, config.DEFAULT_MIN_LEN, config.DEFAULT_MAX_LEN,
        )
        store.write_json(project_id, "candidates.json", [[c.time, c.weight] for c in candidates])
        # Only the samples that have faces: [[time, [[cx, cy, w, h], ...]], ...] (powers "click a face").
        store.write_json(project_id, "faces.json", [
            [round(t, 2), [[round(f.cx, 3), round(f.cy, 3), round(f.w, 3), round(f.h, 3)] for f in faces]]
            for t, faces in zip(result.times, result.faces) if faces
        ])

        def finish(p: Project) -> None:
            p.crop_path, p.tracking = crop_path, mode
            p.has_faces = any(result.faces)
            p.clips = [Clip(id=uuid.uuid4().hex[:8], start=a, end=b, title=f"Clip {i + 1}")
                       for i, (a, b) in enumerate(spans)]
            p.status, p.progress, p.message, p.error, p.attempts = "ready", 1.0, "", None, 0
        store.update(project_id, finish)
    except KeyError:
        return  # the project was deleted while it was being processed
    except media.MediaError as exc:
        _fail(project_id, str(exc))
    except Exception:  # noqa: BLE001 - never leave a project stuck in "analyzing"
        log.exception("Pipeline failed for %s", project_id)
        _fail(project_id, "Something went wrong while processing this video.")


def _fail(project_id: str, message: str) -> None:
    try:
        _set(project_id, status="error", error=message, message="")
    except KeyError:
        pass


def _find_source(folder: Path) -> Optional[Path]:
    path = folder / "source.mp4"
    if path.exists():
        return path
    matches = sorted(folder.glob("source.*"))
    return matches[0] if matches else None


def retry(project_id: str) -> Project:
    """Run a failed project again from the start (a finished download is reused)."""
    def mutate(p: Project) -> None:
        p.status, p.error, p.progress, p.message, p.attempts = "queued", None, 0.0, "Trying again...", 0
    project = store.update(project_id, mutate)
    submit_pipeline(project_id, project.source_url if project.source == "youtube" else None)
    return project


def recover_interrupted() -> None:
    """Called once at startup: put back whatever a previous run left half-done."""
    for project in store.list_all():
        try:
            if project.status in _PROCESSING:
                if project.attempts >= config.MAX_RECOVERY_ATTEMPTS:
                    _fail(project.id, "Processing was interrupted several times. Please try again.")
                    continue
                log.info("Resuming interrupted project %s (attempt %d)", project.id, project.attempts + 1)
                _set(project.id, status="queued", message="Resuming after a restart...",
                     attempts=project.attempts + 1)
                submit_pipeline(project.id, project.source_url if project.source == "youtube" else None)
            else:
                stuck = [c.id for c in project.clips if c.export_status in ("queued", "rendering")]
                if stuck:
                    log.info("Re-queueing %d interrupted exports for %s", len(stuck), project.id)
                    submit_exports(project.id, stuck)
        except Exception:  # noqa: BLE001 - one broken project must not stop the server from starting
            log.exception("Could not recover project %s", project.id)


def resegment(project_id: str, target: float, min_len: float, max_len: float) -> Project:
    project = store.get(project_id)
    raw = store.read_json(project_id, "candidates.json") or []
    candidates = [segmentation.Candidate(t, w) for t, w in raw]
    spans = segmentation.segment(project.duration, candidates, target, min_len, max_len)

    def mutate(p: Project) -> None:
        p.clips = [Clip(id=uuid.uuid4().hex[:8], start=a, end=b, title=f"Clip {i + 1}")
                   for i, (a, b) in enumerate(spans)]
    return store.update(project_id, mutate)


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------

def export_path(project_id: str, clip_id: str) -> Path:
    folder = store.project_dir(project_id) / "exports"
    folder.mkdir(exist_ok=True)
    return folder / f"{clip_id}.mp4"


def submit_exports(project_id: str, clip_ids: list[str]) -> None:
    def mark_queued(p: Project) -> None:
        for clip in p.clips:
            if clip.id in clip_ids:
                clip.export_status, clip.export_progress, clip.export_error = "queued", 0.0, None
    store.update(project_id, mark_queued)
    for clip_id in clip_ids:
        _pool.submit(_run_export, project_id, clip_id)


def cancel_exports(project_id: str, clip_ids: list[str]) -> Project:
    """Stop exports that are waiting or rendering. Finished ones are left alone."""
    project = store.get(project_id)
    active = [c.id for c in project.clips if c.id in clip_ids and c.export_status in ("queued", "rendering")]
    with _cancel_lock:
        _cancelled.update((project_id, cid) for cid in active)

    def mutate(p: Project) -> None:
        for clip in p.clips:
            # A waiting export just goes back to idle; a rendering one notices the flag and stops itself.
            if clip.id in active and clip.export_status == "queued":
                clip.export_status, clip.export_progress = "idle", 0.0
    return store.update(project_id, mutate)


def _is_cancelled(key: tuple[str, str]) -> bool:
    with _cancel_lock:
        return key in _cancelled


def _take_cancel(key: tuple[str, str]) -> bool:
    with _cancel_lock:
        if key in _cancelled:
            _cancelled.discard(key)
            return True
        return False


def _set_clip(project_id: str, clip_id: str, **fields) -> None:
    def mutate(p: Project) -> None:
        for clip in p.clips:
            if clip.id == clip_id:
                for key, value in fields.items():
                    setattr(clip, key, value)
    store.update(project_id, mutate)


def _run_export(project_id: str, clip_id: str) -> None:
    key = (project_id, clip_id)
    try:
        if _take_cancel(key):  # cancelled while still waiting in the queue
            return
        project = store.get(project_id)
        clip = next((c for c in project.clips if c.id == clip_id), None)
        if clip is None:  # deleted while queued
            return
        start, end, revision = clip.start, clip.end, clip.revision
        path = tracking.effective_path(project.crop_path, clip.keyframes, project.width, project.height)
        _set_clip(project_id, clip_id, export_status="rendering", export_progress=0.0)
        info = media.VideoInfo(project.duration, project.width, project.height, project.fps,
                               has_audio=media.probe(source_path(project_id)).has_audio)
        render_clip(
            source_path(project_id), info, path, start, end,
            export_path(project_id, clip_id),
            _throttled(lambda v: _set_clip(project_id, clip_id, export_progress=v)),
            cancelled=lambda: _is_cancelled(key),
        )
        # `revision` is the one we rendered; if the clip was edited meanwhile it no longer matches
        # and the UI offers to export again.
        _set_clip(project_id, clip_id, export_status="done", export_progress=1.0, exported_revision=revision)
    except ExportCancelled:
        _take_cancel(key)
        try:
            _set_clip(project_id, clip_id, export_status="idle", export_progress=0.0)
        except KeyError:
            pass
    except media.MediaError as exc:
        _set_clip(project_id, clip_id, export_status="error", export_error=str(exc))
    except KeyError:
        return  # project deleted meanwhile
    except Exception:  # noqa: BLE001
        log.exception("Export failed for %s/%s", project_id, clip_id)
        _set_clip(project_id, clip_id, export_status="error", export_error="The export failed.")
