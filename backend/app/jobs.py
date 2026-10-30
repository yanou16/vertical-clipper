"""Background work: the ingest/analysis pipeline and clip exports.

Jobs run in a small thread pool. State is written to the project store, and the
frontend simply polls GET /api/projects/{id}.
"""
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from . import config, store
from .models import Clip, Project
from .services import analysis, ingest, media, segmentation, tracking
from .services.render import render_clip

log = logging.getLogger("clipper.jobs")
_pool = ThreadPoolExecutor(max_workers=config.WORKER_THREADS, thread_name_prefix="clipper")


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
        source = _find_source(folder)

        if youtube_url:
            _set(project_id, status="downloading", progress=0.0, message="Downloading the video...")
            source, title = ingest.download_youtube(
                youtube_url, folder,
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
        _set(project_id, duration=info.duration, width=info.width, height=info.height, fps=info.fps)

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

        def finish(p: Project) -> None:
            p.crop_path, p.tracking = crop_path, mode
            p.clips = [Clip(id=uuid.uuid4().hex[:8], start=a, end=b, title=f"Clip {i + 1}")
                       for i, (a, b) in enumerate(spans)]
            p.status, p.progress, p.message, p.error = "ready", 1.0, "", None
        store.update(project_id, finish)
    except media.MediaError as exc:
        _set(project_id, status="error", error=str(exc), message="")
    except Exception:  # noqa: BLE001 - never leave a project stuck in "analyzing"
        log.exception("Pipeline failed for %s", project_id)
        _set(project_id, status="error", message="",
             error="Something went wrong while processing this video.")


def _find_source(folder: Path) -> Optional[Path]:
    path = folder / "source.mp4"
    if path.exists():
        return path
    matches = sorted(folder.glob("source.*"))
    return matches[0] if matches else None


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


def _set_clip(project_id: str, clip_id: str, **fields) -> None:
    def mutate(p: Project) -> None:
        for clip in p.clips:
            if clip.id == clip_id:
                for key, value in fields.items():
                    setattr(clip, key, value)
    store.update(project_id, mutate)


def _run_export(project_id: str, clip_id: str) -> None:
    try:
        project = store.get(project_id)
        clip = next((c for c in project.clips if c.id == clip_id), None)
        if clip is None:  # deleted while queued
            return
        start, end = clip.start, clip.end
        _set_clip(project_id, clip_id, export_status="rendering", export_progress=0.0)
        info = media.VideoInfo(project.duration, project.width, project.height, project.fps,
                               has_audio=media.probe(source_path(project_id)).has_audio)
        render_clip(
            source_path(project_id), info, project.crop_path, start, end,
            export_path(project_id, clip_id),
            _throttled(lambda v: _set_clip(project_id, clip_id, export_progress=v)),
        )
        _set_clip(project_id, clip_id, export_status="done", export_progress=1.0,
                  exported_range=(start, end))
    except media.MediaError as exc:
        _set_clip(project_id, clip_id, export_status="error", export_error=str(exc))
    except KeyError:
        return  # project deleted meanwhile
    except Exception:  # noqa: BLE001
        log.exception("Export failed for %s/%s", project_id, clip_id)
        _set_clip(project_id, clip_id, export_status="error", export_error="The export failed.")
