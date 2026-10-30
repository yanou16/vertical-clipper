"""Getting a video into a project: YouTube download (yt-dlp) or validated upload."""
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .. import config
from .media import MediaError

_PROGRESS = re.compile(r"^\[download\]\s+([\d.]+)%")


def download_youtube(url: str, dest_dir: Path, on_progress: Callable[[float], None]) -> tuple[Path, str]:
    """Download the best <=1080p video to dest_dir/source.mp4. Returns (path, title)."""
    template = str(dest_dir / "source.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist", "--newline", "--no-warnings",
        "--match-filter", f"duration<={config.MAX_VIDEO_MINUTES * 60}",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
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
