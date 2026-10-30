"""Pydantic models shared by the store and the HTTP API."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

ProjectStatus = Literal["queued", "downloading", "preparing", "analyzing", "ready", "error"]
ExportStatus = Literal["idle", "queued", "rendering", "done", "error"]


class Clip(BaseModel):
    id: str
    start: float
    end: float
    title: str = ""
    export_status: ExportStatus = "idle"
    export_progress: float = 0.0
    export_error: Optional[str] = None
    # The (start, end) that was actually rendered, to detect stale exports.
    exported_range: Optional[tuple[float, float]] = None

    @property
    def duration(self) -> float:
        return self.end - self.start


class Project(BaseModel):
    id: str
    title: str = "Untitled"
    source: Literal["youtube", "upload"] = "upload"
    source_url: Optional[str] = None
    status: ProjectStatus = "queued"
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    clips: list[Clip] = Field(default_factory=list)
    # Camera path for the 9:16 crop: [[time_s, center_x_0to1], ...]
    crop_path: list[list[float]] = Field(default_factory=list)
    tracking: Literal["faces", "center"] = "center"
    created_at: float = 0.0


# ---- request bodies -------------------------------------------------------

class UrlRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        v = v.strip()
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("Please paste a full link starting with http:// or https://")
        return v


class ClipPatch(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    title: Optional[str] = Field(default=None, max_length=120)


class ClipCreate(BaseModel):
    start: float
    end: float


class ResegmentRequest(BaseModel):
    target: float = Field(default=30.0, ge=5, le=180)
    min_len: float = Field(default=15.0, ge=3, le=180)
    max_len: float = Field(default=60.0, ge=5, le=180)


class ExportRequest(BaseModel):
    clip_ids: Optional[list[str]] = None  # None = every clip
