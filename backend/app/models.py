"""Pydantic models shared by the store and the HTTP API."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from . import config

ProjectStatus = Literal["queued", "downloading", "preparing", "analyzing", "ready", "error"]
ExportStatus = Literal["idle", "queued", "rendering", "done", "error"]


class Clip(BaseModel):
    id: str
    start: float
    end: float
    title: str = ""
    # Manual framing: [(time_s, centre_x 0..1)]. Empty = follow the automatic camera path.
    keyframes: list[tuple[float, float]] = Field(default_factory=list)
    # Bumped whenever something that changes the rendered video is edited (range or framing),
    # so a finished export can be recognised as out of date.
    revision: int = 0
    export_status: ExportStatus = "idle"
    export_progress: float = 0.0
    export_error: Optional[str] = None
    exported_revision: Optional[int] = None

    @property
    def duration(self) -> float:
        return self.end - self.start


class Project(BaseModel):
    id: str
    title: str = "Untitled"
    source: Literal["youtube", "upload"] = "upload"
    source_url: Optional[str] = None
    quality: int = config.DEFAULT_QUALITY  # requested max height for YouTube downloads
    status: ProjectStatus = "queued"
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None
    attempts: int = 0  # automatic recoveries after a server restart
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    video_codec: str = ""
    video_kbps: int = 0
    clips: list[Clip] = Field(default_factory=list)
    # Automatic camera path for the 9:16 crop: [[time_s, center_x_0to1], ...]
    crop_path: list[list[float]] = Field(default_factory=list)
    tracking: Literal["faces", "center"] = "center"
    has_faces: bool = False  # faces.json exists (lets the editor offer "click a face")
    created_at: float = 0.0


# ---- request bodies -------------------------------------------------------

class UrlRequest(BaseModel):
    url: str
    quality: int = config.DEFAULT_QUALITY

    @field_validator("url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        v = v.strip()
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("Please paste a full link starting with http:// or https://")
        return v

    @field_validator("quality")
    @classmethod
    def known_quality(cls, v: int) -> int:
        if v not in config.QUALITY_CHOICES:
            raise ValueError(f"Quality must be one of {', '.join(map(str, config.QUALITY_CHOICES))}")
        return v


class ClipPatch(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    title: Optional[str] = Field(default=None, max_length=120)
    keyframes: Optional[list[tuple[float, float]]] = Field(default=None, max_length=300)


class ClipCreate(BaseModel):
    start: float
    end: float


class ResegmentRequest(BaseModel):
    target: float = Field(default=30.0, ge=5, le=180)
    min_len: float = Field(default=15.0, ge=3, le=180)
    max_len: float = Field(default=60.0, ge=5, le=180)


class ExportRequest(BaseModel):
    clip_ids: Optional[list[str]] = None  # None = every clip
