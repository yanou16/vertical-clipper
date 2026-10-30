"""Render one clip as a 1080x1920 MP4, following the camera path.

Pipeline:  ffmpeg (decode segment -> raw frames) -> Python/OpenCV (per-frame crop + resize)
           -> ffmpeg (encode H.264 + original audio).
Doing the crop in Python lets the window move smoothly frame-by-frame, which an ffmpeg
crop filter can't do without a gigantic expression.
"""
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .. import config
from .media import MediaError, VideoInfo
from .tracking import centers_at


def render_clip(source: Path, info: VideoInfo, crop_path: list[list[float]],
                start: float, end: float, out_file: Path,
                on_progress: Callable[[float], None]) -> None:
    width, height, fps = info.width, info.height, min(info.fps, 60.0)
    duration = end - start
    crop_w = min(width, int(round(height * 9 / 16 / 2)) * 2)
    frame_bytes = width * height * 3
    total_frames = max(1, int(round(duration * fps)))
    # Camera centre for every output frame, computed once up front.
    centers = centers_at(crop_path, start + np.arange(total_frames + 2) / fps)

    decoder = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
         "-an", "-vf", f"fps={fps:.3f}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    part = out_file.with_suffix(".part.mp4")
    audio_map = ["-map", "1:a:0?", "-c:a", "aac", "-b:a", "160k"] if info.has_audio else ["-an"]
    with tempfile.TemporaryFile() as enc_log:
        encoder = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{config.OUT_WIDTH}x{config.OUT_HEIGHT}",
             "-r", f"{fps:.3f}", "-i", "-",
             "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
             "-map", "0:v", *audio_map,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-shortest", "-movflags", "+faststart", str(part)],
            stdin=subprocess.PIPE, stderr=enc_log,
        )
        assert decoder.stdout is not None and encoder.stdin is not None
        try:
            index = 0
            while True:
                raw = decoder.stdout.read(frame_bytes)
                if len(raw) < frame_bytes:
                    break
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
                cx = float(centers[min(index, len(centers) - 1)])
                x0 = int(round(cx * width - crop_w / 2))
                x0 = max(0, min(width - crop_w, x0))
                window = frame[:, x0:x0 + crop_w]
                interp = cv2.INTER_AREA if height >= config.OUT_HEIGHT else cv2.INTER_CUBIC
                out = cv2.resize(window, (config.OUT_WIDTH, config.OUT_HEIGHT), interpolation=interp)
                encoder.stdin.write(out.tobytes())
                index += 1
                if index % 15 == 0:
                    on_progress(min(0.99, index / total_frames))
        except BrokenPipeError:
            pass
        finally:
            decoder.stdout.close()
            decoder.wait()
            try:
                encoder.stdin.close()
            except BrokenPipeError:
                pass
            encoder.wait()
        if encoder.returncode != 0 or not part.exists():
            enc_log.seek(0)
            detail = enc_log.read().decode(errors="replace").strip().splitlines()
            part.unlink(missing_ok=True)
            raise MediaError(f"Encoding failed: {detail[-1] if detail else 'unknown error'}")
    part.replace(out_file)
    on_progress(1.0)
