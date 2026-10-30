"""One pass over the (small) proxy video: find shot changes and the faces in each sampled frame."""
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from .. import config
from .media import MediaError

# Shot change = the colour histogram of two consecutive samples differs a lot.
CUT_THRESHOLD = 0.45
MIN_SHOT_SECONDS = 1.0
FACE_SCORE_THRESHOLD = 0.6


@dataclass
class Face:
    cx: float  # centre x, 0..1 of frame width
    area: float  # 0..1 of frame area
    # Box, only needed to draw "click a face" targets in the editor. All 0..1 of the frame.
    cy: float = 0.5
    w: float = 0.0
    h: float = 0.0


@dataclass
class Analysis:
    sample_fps: float
    times: list[float] = field(default_factory=list)
    faces: list[list[Face]] = field(default_factory=list)  # faces[i] = faces seen at times[i]
    cuts: list[float] = field(default_factory=list)  # seconds where a new shot starts


def _histogram(frame: np.ndarray) -> np.ndarray:
    small = cv2.resize(frame, (160, int(160 * frame.shape[0] / frame.shape[1])))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    return cv2.normalize(hist, hist, 1.0, 0.0, cv2.NORM_L1)


def _make_face_detector(width: int, height: int) -> Optional["cv2.FaceDetectorYN"]:
    if not config.MODEL_PATH.exists():
        return None
    return cv2.FaceDetectorYN.create(
        str(config.MODEL_PATH), "", (width, height),
        score_threshold=FACE_SCORE_THRESHOLD, nms_threshold=0.3, top_k=20,
    )


def analyze(proxy: Path, src_width: int, src_height: int, duration: float,
            on_progress: Callable[[float], None]) -> Analysis:
    width = config.ANALYSIS_WIDTH
    height = int(round(width * src_height / src_width / 2)) * 2
    fps = config.ANALYSIS_FPS
    frame_bytes = width * height * 3

    cmd = ["ffmpeg", "-v", "error", "-i", str(proxy), "-an",
           "-vf", f"fps={fps},scale={width}:{height}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert proc.stdout is not None

    detector = _make_face_detector(width, height)
    result = Analysis(sample_fps=fps)
    expected = max(1, int(duration * fps))
    prev_hist, last_cut = None, -MIN_SHOT_SECONDS

    index = 0
    while True:
        raw = proc.stdout.read(frame_bytes)
        if len(raw) < frame_bytes:
            break
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
        t = index / fps

        hist = _histogram(frame)
        if prev_hist is not None:
            distance = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)
            if distance > CUT_THRESHOLD and t - last_cut >= MIN_SHOT_SECONDS:
                result.cuts.append(round(t - 0.5 / fps, 3))
                last_cut = t
        prev_hist = hist

        faces: list[Face] = []
        if detector is not None:
            _, found = detector.detect(frame)
            for row in (found if found is not None else []):
                x, y, w, h = row[:4]
                faces.append(Face(
                    cx=float((x + w / 2) / width), area=float(w * h / (width * height)),
                    cy=float((y + h / 2) / height), w=float(w / width), h=float(h / height),
                ))
        result.times.append(t)
        result.faces.append(faces)

        index += 1
        if index % 20 == 0:
            on_progress(min(1.0, index / expected))

    proc.wait()
    if index == 0:
        raise MediaError("Couldn't read any frames from this video.")
    return result
