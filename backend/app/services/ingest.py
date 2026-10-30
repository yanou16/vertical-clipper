"""Getting a video into a project: YouTube download (yt-dlp) or validated upload."""
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .. import config
from .media import MediaError

_PROGRESS = re.compile(r"^\[download\]\s+([\d.]+)%")


def _js_runtime_args() -> list[str]:
    """YouTube hides some formats behind a small JavaScript puzzle. yt-dlp solves it with deno by
    default; if only node or bun is installed we point it at that one instead."""
    if shutil.which("deno"):
        return []
    for name in ("node", "bun"):
        if shutil.which(name):
            return ["--js-runtimes", name]
    return []


def format_args(quality: int) -> list[str]:
    """Pick the best stream up to `quality` pixels high.

    -f caps the height. -S then orders what is left: resolution first, then plain https streams
    (reliable) before streaming playlists, then the HIGHEST video bitrate. Without -S yt-dlp prefers
    the newest codec even when it is the most compressed one (AV1 at 498 kb/s instead of H.264 at
    1022 kb/s on the same 1080p video), which is why early downloads looked soft.
    """
    return [
        "-f", f"bv*[height<={quality}]+ba/b[height<={quality}]/b",
        "-S", f"res:{quality},proto,vbr",
    ]


def download_youtube(url: str, dest_dir: Path, quality: int,
                     on_progress: Callable[[float], None]) -> tuple[Path, str]:
    """Download the best video up to `quality` pixels high to dest_dir/source.mp4. Returns (path, title)."""
    template = str(dest_dir / "source.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist", "--newline", "--no-warnings",
        "--match-filter", f"duration<={config.MAX_VIDEO_MINUTES * 60}",
        *format_args(quality),
        *_js_runtime_args(),
        "--merge-output-format", "mp4",
        "--print", "after_move:title",
        "-o", template,
        "--", url,  # "--" so a hostile URL can never be parsed as an option
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    title, last_lines = "", []
    for line in proc.stdout:
        line = line.strip()
        if m := _PROGRESS.match(line):
            on_progress(float(m.group(1)) / 100)
        elif line and not line.startswith("["):
            title = line  # the --print line
        last_lines.append(line)
    proc.wait()
    source = dest_dir / "source.mp4"
    if proc.returncode != 0 or not source.exists():
        hint = next((l for l in reversed(last_lines) if l.startswith("ERROR")), "")
        if "does not pass filter" in hint or any("does not pass filter" in l for l in last_lines):
            raise MediaError(f"This video is longer than {config.MAX_VIDEO_MINUTES} minutes.")
        raise MediaError("Couldn't download this link. Is it public and a valid video URL?")
    return source, title or "YouTube video"


def check_upload_name(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_EXTENSIONS))
        raise MediaError(f"Unsupported file type '{ext or '?'}'. Allowed: {allowed}")
    return ext
