"""Getting a video into a project: YouTube download (yt-dlp) or validated upload."""
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from .. import config
from .media import MediaError

# "[download]  45.2% of ~ 210.14MiB at  288.00KiB/s ETA 07:12 (frag 3/90)"
_PROGRESS = re.compile(
    r"^\[download\]\s+(?P<pct>[\d.]+)%"
    r"(?:\s+of\s+~?\s*(?P<size>\S+))?"
    r"(?:\s+at\s+(?P<speed>\S+))?"
    r"(?:\s+ETA\s+(?P<eta>\S+))?"
)

# yt-dlp downloads the video stream, then the (much smaller) audio stream, each counting 0-100%.
# We map them onto one 0-1 bar. The audio is a few percent of the bytes, so it gets a small slice.
_VIDEO_SHARE = 0.95


def stream_after(line: str, last_pct: float, stream: int) -> tuple[int, float]:
    """Which stream a progress line belongs to: 0 = video, 1 = audio. Returns (stream, this line's percent).

    With --print, yt-dlp runs in quiet mode and does not announce each new file, so we notice the
    audio starting from the percentage falling back to ~0 after the video reached the end.
    """
    m = _PROGRESS.match(line)
    if m is None:
        return stream, last_pct
    pct = float(m["pct"])
    return (stream + 1 if pct + 5 < last_pct else stream), pct


def parse_progress(line: str, stream: int) -> Optional[tuple[float, str]]:
    """Turn one yt-dlp progress line into (overall fraction 0..1, a sentence for the user)."""
    m = _PROGRESS.match(line)
    if m is None:
        return None
    own = min(1.0, float(m["pct"]) / 100)  # progress of the current stream
    fraction = own * _VIDEO_SHARE if stream <= 0 else _VIDEO_SHARE + own * (1 - _VIDEO_SHARE)
    parts = [f"Downloading the {'video' if stream <= 0 else 'audio'} {own * 100:.0f}%"]
    if m["size"]:
        parts.append(f"of {m['size']}")
    if m["speed"] and "nknown" not in m["speed"]:
        parts.append(f"at {m['speed']}")
    text = " ".join(parts)
    if m["eta"] and "nknown" not in m["eta"]:
        text += f", {m['eta']} left"
    return fraction, text


def _js_runtime_args() -> list[str]:
    """YouTube hides some formats behind a small JavaScript puzzle. yt-dlp solves it with deno by
    default; if only node or bun is installed we point it at that one instead."""
    if shutil.which("deno"):
        return []
    for name in ("node", "bun"):
        if shutil.which(name):
            return ["--js-runtimes", name]
    return []


def format_args(quality: int, light: bool = False) -> list[str]:
    """Pick which stream to download, up to `quality` pixels high.

    -f caps the height. -S then orders what is left, most important first.

    Normal mode: resolution, then plain https streams (reliable), then the HIGHEST video bitrate.
    Without -S yt-dlp prefers the newest codec even when it is the most compressed one (AV1 at
    498 kb/s instead of H.264 at 1022 kb/s on the same 1080p video), which looked soft.

    Light mode: same height, but prefer 30 fps or less, and VP9 (a codec that is good at small
    sizes), then the highest bitrate among those. On a 10 minute 720p video that is 75 MB instead
    of 210 MB, which matters a lot on a slow connection. Little is lost for talking-head content.
    """
    order = f"res:{quality},fps:30,proto,vcodec:vp9,vbr" if light else f"res:{quality},proto,vbr"
    return ["-f", f"bv*[height<={quality}]+ba/b[height<={quality}]/b", "-S", order]


def download_youtube(url: str, dest_dir: Path, quality: int,
                     on_progress: Callable[[float, str], None], light: bool = False) -> tuple[Path, str]:
    """Download the video to dest_dir/source.mp4. Returns (path, title).

    `on_progress(fraction, text)` is called as the download advances.
    """
    template = str(dest_dir / "source.%(ext)s")
    cmd = [
        # -u: unbuffered. Piped Python output is normally held back in 8 KB blocks, which made the
        # progress bar sit at 0% for minutes and then jump.
        sys.executable, "-u", "-m", "yt_dlp",
        # --print below makes yt-dlp "quiet", which hides the progress lines; --progress brings them back.
        "--no-playlist", "--newline", "--no-warnings", "--progress",
        "--match-filter", f"duration<={config.MAX_VIDEO_MINUTES * 60}",
        *format_args(quality, light),
        *_js_runtime_args(),
        "--merge-output-format", "mp4",
        "--print", "after_move:title",
        "-o", template,
        "--", url,  # "--" so a hostile URL can never be parsed as an option
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    title, last_lines, stream, last_pct = "", [], 0, 0.0
    for line in proc.stdout:
        line = line.strip()
        stream, last_pct = stream_after(line, last_pct, stream)
        if progress := parse_progress(line, stream):
            on_progress(*progress)
        elif line.startswith("[Merger]"):
            on_progress(1.0, "Putting the video and audio together...")
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
