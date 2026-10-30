"""HTTP API. Kept thin: validation + calls into store/jobs."""
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config, jobs, store
from ..models import Clip, ClipCreate, ClipPatch, ExportRequest, Project, ResegmentRequest, UrlRequest
from ..services.ingest import check_upload_name
from ..services.media import MediaError, sanitize_filename

router = APIRouter(prefix="/api")


# ---- helpers -----------------------------------------------------------------

def _get_project(project_id: str) -> Project:
    try:
        return store.get(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found")


def _get_ready_project(project_id: str) -> Project:
    project = _get_project(project_id)
    if project.status != "ready":
        raise HTTPException(409, "The video is still being processed.")
    return project


def _find_clip(project: Project, clip_id: str) -> Clip:
    clip = next((c for c in project.clips if c.id == clip_id), None)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    return clip


def _validated_range(start: float, end: float, duration: float) -> tuple[float, float]:
    start, end = max(0.0, start), min(duration, end)
    if end - start < config.CLIP_MIN_LEN:
        raise HTTPException(422, f"A clip must be at least {config.CLIP_MIN_LEN:g} second long.")
    if end - start > config.CLIP_MAX_LEN:
        raise HTTPException(422, f"A clip can't be longer than {config.CLIP_MAX_LEN:g} seconds.")
    return round(start, 2), round(end, 2)


def _clean_keyframes(raw: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    """Validate manual framing points: inside the video, inside the frame, one per 10 ms, sorted."""
    cleaned: dict[float, float] = {}
    for t, cx in raw:
        if not (0 <= t <= duration) or not (0 <= cx <= 1):  # also rejects NaN
            raise HTTPException(422, "Framing points must be inside the video and the frame.")
        cleaned[round(t, 2)] = round(cx, 4)
    return sorted(cleaned.items())


def _is_current(clip: Clip) -> bool:
    """True when the exported file reflects the clip as it is now (same range and same framing)."""
    return clip.export_status == "done" and clip.exported_revision == clip.revision


# ---- projects ------------------------------------------------------------------

@router.get("/health")
def health():
    import shutil
    return {"ffmpeg": shutil.which("ffmpeg") is not None, "ffprobe": shutil.which("ffprobe") is not None,
            "face_model": config.MODEL_PATH.exists(), "max_upload_mb": config.MAX_UPLOAD_MB}


@router.get("/projects", response_model=list[Project])
def list_projects():
    return store.list_all()


@router.post("/projects/from-url", response_model=Project, status_code=201)
def create_from_url(body: UrlRequest):
    project = store.create("Downloading...", "youtube", body.url)
    def choose(p: Project) -> None:
        p.quality, p.light_download = body.quality, body.light
    project = store.update(project.id, choose)
    jobs.submit_pipeline(project.id, youtube_url=body.url)
    return project


@router.post("/projects/upload", response_model=Project, status_code=201)
async def create_from_upload(file: UploadFile = File(...)):
    try:
        ext = check_upload_name(file.filename or "")
    except MediaError as exc:
        raise HTTPException(415, str(exc))

    project = store.create(Path(file.filename or "video").stem[:80], "upload")
    target = store.project_dir(project.id) / f"source{ext}"
    limit, written = config.MAX_UPLOAD_MB * 1024 * 1024, 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(413, f"File too large (max {config.MAX_UPLOAD_MB} MB).")
                out.write(chunk)
    except HTTPException:
        store.delete(project.id)
        raise
    jobs.submit_pipeline(project.id)
    return project


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str):
    return _get_project(project_id)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str):
    _get_project(project_id)
    store.delete(project_id)


@router.post("/projects/{project_id}/retry", response_model=Project)
def retry_project(project_id: str):
    project = _get_project(project_id)
    if project.status != "error":
        raise HTTPException(409, "Only a failed video can be retried.")
    return jobs.retry(project_id)


@router.get("/projects/{project_id}/faces")
def faces_in_range(project_id: str, start: float = 0.0, end: float = 0.0):
    """Faces seen between `start` and `end` seconds, so the editor can offer 'click a face to follow it'."""
    _get_project(project_id)
    if not (0 <= end - start <= config.CLIP_MAX_LEN + 5):
        raise HTTPException(422, "Ask for one clip at a time.")
    lo, hi = start - 0.5, end + 0.5
    data = store.read_json(project_id, "faces.json") or []  # projects made before this feature have none
    return [{"t": t, "faces": [{"cx": f[0], "cy": f[1], "w": f[2], "h": f[3]} for f in faces]}
            for t, faces in data if lo <= t <= hi]


@router.get("/projects/{project_id}/media")
def preview_media(project_id: str):
    """Low-res preview of the source for the editor (supports HTTP range requests for seeking)."""
    _get_project(project_id)
    path = jobs.proxy_path(project_id)
    if not path.exists():
        raise HTTPException(404, "Preview not ready yet")
    return FileResponse(path, media_type="video/mp4")


# ---- clips -----------------------------------------------------------------------

@router.post("/projects/{project_id}/clips", response_model=Project, status_code=201)
def add_clip(project_id: str, body: ClipCreate):
    project = _get_ready_project(project_id)
    start, end = _validated_range(body.start, body.end, project.duration)

    def mutate(p: Project) -> None:
        p.clips.append(Clip(id=uuid.uuid4().hex[:8], start=start, end=end, title=f"Clip {len(p.clips) + 1}"))
        p.clips.sort(key=lambda c: c.start)
    return store.update(project_id, mutate)


@router.patch("/projects/{project_id}/clips/{clip_id}", response_model=Project)
def patch_clip(project_id: str, clip_id: str, body: ClipPatch):
    project = _get_ready_project(project_id)
    clip = _find_clip(project, clip_id)
    start = clip.start if body.start is None else body.start
    end = clip.end if body.end is None else body.end
    start, end = _validated_range(start, end, project.duration)
    keyframes = None if body.keyframes is None else _clean_keyframes(body.keyframes, project.duration)

    def mutate(p: Project) -> None:
        c = _find_clip(p, clip_id)
        changed = (c.start, c.end) != (start, end)
        c.start, c.end = start, end
        if keyframes is not None:
            changed = changed or [tuple(k) for k in c.keyframes] != keyframes
            c.keyframes = keyframes
        if body.title is not None:
            c.title = body.title.strip()
        if changed:
            c.revision += 1  # whatever was exported before is now out of date
        if c.export_status in ("done", "error") and not _is_current(c):
            c.export_status, c.export_progress, c.export_error = "idle", 0.0, None
    return store.update(project_id, mutate)


@router.delete("/projects/{project_id}/clips/{clip_id}", response_model=Project)
def delete_clip(project_id: str, clip_id: str):
    project = _get_ready_project(project_id)
    _find_clip(project, clip_id)

    def mutate(p: Project) -> None:
        p.clips = [c for c in p.clips if c.id != clip_id]
    jobs.export_path(project_id, clip_id).unlink(missing_ok=True)
    return store.update(project_id, mutate)


@router.post("/projects/{project_id}/resegment", response_model=Project)
def resegment(project_id: str, body: ResegmentRequest):
    _get_ready_project(project_id)
    return jobs.resegment(project_id, body.target, body.min_len, body.max_len)


# ---- export ----------------------------------------------------------------------

@router.post("/projects/{project_id}/exports", response_model=Project, status_code=202)
def start_exports(project_id: str, body: ExportRequest):
    project = _get_ready_project(project_id)
    wanted = body.clip_ids if body.clip_ids is not None else [c.id for c in project.clips]
    known = {c.id: c for c in project.clips}
    unknown = [cid for cid in wanted if cid not in known]
    if unknown:
        raise HTTPException(404, "Clip not found")
    # Skip clips that are already rendering/queued, or already exported and unchanged.
    todo = [cid for cid in wanted
            if known[cid].export_status not in ("queued", "rendering") and not _is_current(known[cid])]
    if todo:
        jobs.submit_exports(project_id, todo)
    return store.get(project_id)


@router.post("/projects/{project_id}/exports/cancel", response_model=Project)
def cancel_exports(project_id: str, body: ExportRequest):
    project = _get_ready_project(project_id)
    wanted = body.clip_ids if body.clip_ids is not None else [c.id for c in project.clips]
    return jobs.cancel_exports(project_id, wanted)


@router.get("/projects/{project_id}/clips/{clip_id}/download")
def download_clip(project_id: str, clip_id: str):
    project = _get_project(project_id)
    clip = _find_clip(project, clip_id)
    path = jobs.export_path(project_id, clip_id)
    if not _is_current(clip) or not path.exists():
        raise HTTPException(409, "This clip hasn't been exported yet.")
    index = project.clips.index(clip) + 1
    name = f"{index:02d}_{sanitize_filename(clip.title, 'clip')}.mp4"
    return FileResponse(path, media_type="video/mp4", filename=name)


@router.get("/projects/{project_id}/download")
def download_all(project_id: str, background: BackgroundTasks):
    project = _get_project(project_id)
    ready = [(i, c) for i, c in enumerate(project.clips, 1)
             if _is_current(c) and jobs.export_path(project_id, c.id).exists()]
    if not ready:
        raise HTTPException(409, "No exported clips yet.")
    tmp = Path(tempfile.mkstemp(suffix=".zip")[1])
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as archive:  # mp4 is already compressed
        for i, clip in ready:
            archive.write(jobs.export_path(project_id, clip.id),
                          f"{i:02d}_{sanitize_filename(clip.title, 'clip')}.mp4")
    background.add_task(tmp.unlink, missing_ok=True)
    zip_name = f"{sanitize_filename(project.title, 'clips')}_vertical.zip"
    return FileResponse(tmp, media_type="application/zip", filename=zip_name)
