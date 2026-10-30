"""Thin wrappers around ffprobe / ffmpeg."""
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


class MediaError(RuntimeError):
    """A user-presentable media failure."""


@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    codec: str = ""
    bitrate: int = 0  # video bits per second, 0 when unknown


def require_binaries() -> None:
    missing = [b for b in ("ffmpeg", "ffprobe") if shutil.which(b) is None]
    if missing:
        raise MediaError(f"{', '.join(missing)} not found. Please install FFmpeg (see README).")


def _parse_rate(rate: str) -> float:
    num, _, den = rate.partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: Path) -> VideoInfo:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise MediaError("This file doesn't look like a valid video.")
    data = json.loads(out.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError("No video track found in this file.")
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise MediaError("Could not read the video duration.")
    fps = _parse_rate(video.get("avg_frame_rate", "0/1")) or _parse_rate(video.get("r_frame_rate", "30/1")) or 30.0
    return VideoInfo(
        duration=duration,
        width=int(video["width"]),
        height=int(video["height"]),
        fps=fps,
        has_audio=any(s.get("codec_type") == "audio" for s in data["streams"]),
        codec=video.get("codec_name", ""),
        bitrate=_to_int(video.get("bit_rate")) or _to_int(data.get("format", {}).get("bit_rate")),
    )


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def run_with_progress(cmd: list[str], duration: float, on_progress: Callable[[float], None]) -> None:
    """Run an ffmpeg command that was given `-progress pipe:1` and report 0..1 progress."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    for line in proc.stdout:
        if line.startswith("out_time_us="):
            try:
                on_progress(min(1.0, int(line.split("=")[1]) / 1e6 / max(duration, 0.01)))
            except ValueError:
                pass
    _, err = proc.communicate()
    if proc.returncode != 0:
        raise MediaError(f"ffmpeg failed: {err.strip().splitlines()[-1] if err.strip() else proc.returncode}")


def make_proxy(source: Path, dest: Path, duration: float, on_progress: Callable[[float], None]) -> None:
    """Small, browser-friendly H.264 copy used for the editor preview (any input codec plays)."""
    tmp = dest.with_suffix(".part.mp4")
    run_with_progress(
        ["ffmpeg", "-y", "-v", "error", "-nostats", "-progress", "pipe:1", "-i", str(source),
         "-vf", "scale=-2:480", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
         "-g", "30", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(tmp)],
        duration, on_progress,
    )
    tmp.replace(dest)


_SILENCE_START = re.compile(r"silence_start: ([\d.]+)")
_SILENCE_END = re.compile(r"silence_end: ([\d.]+)")


def detect_silences(source: Path, noise_db: int = -35, min_len: float = 0.4) -> list[tuple[float, float]]:
    """Return [(start, end)] of quiet stretches - natural places to cut speech."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "info", "-nostats", "-i", str(source), "-vn",
         "-af", f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    silences, start = [], None
    for line in proc.stderr.splitlines():
        if m := _SILENCE_START.search(line):
            start = float(m.group(1))
        elif (m := _SILENCE_END.search(line)) and start is not None:
            silences.append((start, float(m.group(1))))
            start = None
    return silences


def sanitize_filename(name: str, fallback: str = "clip") -> str:
    cleaned = re.sub(r"[^\w\- ]+", "", name, flags=re.UNICODE).strip().replace(" ", "_")
    return cleaned[:60] or fallback


def tail(text: Optional[str], n: int = 300) -> str:
    return (text or "")[-n:]
