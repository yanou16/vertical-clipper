"""Turn raw face detections into a smooth "virtual camera" path for the 9:16 crop.

The path is a list of [time, centre_x] points (centre_x is 0..1 of the source width).
Rules that make it look professional instead of jittery:
  * follow the main subject (largest face, sticky to whoever we followed before)
  * ignore small movements (dead zone) and ease towards the target
  * never glide across a shot change - the camera jumps with the cut
"""
import numpy as np

from .analysis import Analysis

DEAD_ZONE = 0.035  # fraction of frame width the subject may move before the camera follows
EASING = 0.45  # 0..1, higher = camera catches up faster
STICKY_DISTANCE = 0.15  # a face this close to the last one is "the same person"
MIN_FACE_COVERAGE = 0.15  # below this share of frames with faces we fall back to a centred crop
QUANTUM = 0.002  # drop points that change less than this, keeps the stored path small


def crop_half_width(src_width: int, src_height: int) -> float:
    """Half the width of the 9:16 window, as a fraction of the source width."""
    return min(0.5, (src_height * 9 / 16) / src_width / 2)


def _pick_subject(faces, previous):
    if not faces:
        return None
    if previous is not None:
        near = [f for f in faces if abs(f.cx - previous) < STICKY_DISTANCE]
        if near:
            return max(near, key=lambda f: f.area).cx
    return max(faces, key=lambda f: f.area).cx


def _fill_gaps(values: np.ndarray) -> np.ndarray:
    """Replace NaN (no face) by interpolating between neighbours; all-NaN -> centred."""
    valid = ~np.isnan(values)
    if not valid.any():
        return np.full_like(values, 0.5)
    idx = np.arange(len(values))
    return np.interp(idx, idx[valid], values[valid])


def _follow(targets: np.ndarray) -> np.ndarray:
    camera = np.empty_like(targets)
    position = targets[0]
    for i, target in enumerate(targets):
        error = target - position
        if abs(error) > DEAD_ZONE:
            position += (error - np.sign(error) * DEAD_ZONE) * EASING
        camera[i] = position
        # (the camera stops once inside the dead zone, so static shots stay perfectly still)
    return camera


def _median3(values: np.ndarray) -> np.ndarray:
    if len(values) < 3:
        return values
    padded = np.pad(values, 1, mode="edge")
    return np.median(np.stack([padded[:-2], padded[1:-1], padded[2:]]), axis=0)


def build_crop_path(analysis: Analysis, duration: float, src_width: int, src_height: int
                    ) -> tuple[list[list[float]], str]:
    n = len(analysis.times)
    half = crop_half_width(src_width, src_height)
    with_faces = sum(1 for faces in analysis.faces if faces)
    mode = "faces" if n and with_faces / n >= MIN_FACE_COVERAGE else "center"
    if mode == "center":
        return [[0.0, 0.5]], mode

    step = 1 / analysis.sample_fps
    # Shot boundaries as sample indices.
    starts = [0] + [min(n - 1, int(round((c + 0.5 * step) / step))) for c in analysis.cuts]
    starts = sorted(set(starts))
    shots = list(zip(starts, starts[1:] + [n]))

    points: list[tuple[float, float]] = []
    previous_subject = None
    for a, b in shots:
        raw = np.full(b - a, np.nan)
        for i in range(a, b):
            subject = _pick_subject(analysis.faces[i], previous_subject)
            if subject is not None:
                raw[i - a] = subject
                previous_subject = subject
        targets = _median3(_fill_gaps(raw))
        camera = np.clip(_follow(targets), half, 1 - half)

        shot_start = 0.0 if a == 0 else analysis.times[a] - 0.5 * step
        shot_end = duration if b >= n else analysis.times[b] - 0.5 * step
        points.append((shot_start, float(camera[0])))
        points += [(analysis.times[i], float(camera[i - a])) for i in range(a, b) if analysis.times[i] > shot_start]
        points.append((max(shot_start, shot_end - 0.001), float(camera[-1])))
        previous_subject = None  # new shot => new framing, don't stay sticky across a cut

    return _compress(points), mode


def _compress(points: list[tuple[float, float]]) -> list[list[float]]:
    """Keep only points where the path actually changes (plus the flat point right before a change)."""
    kept: list[tuple[float, float]] = [points[0]]
    skipped = None
    for t, c in points[1:]:
        if abs(c - kept[-1][1]) > QUANTUM or t - kept[-1][0] < 0.002:
            if skipped is not None:
                kept.append(skipped)
                skipped = None
            kept.append((t, c))
        else:
            skipped = (t, c)
    if skipped is not None:
        kept.append(skipped)
    return [[round(t, 3), round(c, 4)] for t, c in kept]


def effective_path(auto_path: list[list[float]], keyframes, src_width: int, src_height: int
                   ) -> list[list[float]]:
    """The camera path to use for one clip: the user's keyframes if there are any, else the automatic path.

    Between keyframes the camera glides in a straight line; before the first and after the last it holds
    still. A single keyframe therefore locks the framing for the whole clip.
    """
    if not keyframes:
        return auto_path
    half = crop_half_width(src_width, src_height)
    points = sorted((float(t), min(max(float(c), half), 1 - half)) for t, c in keyframes)
    return [[t, c] for t, c in points]


def centers_at(path: list[list[float]], times: np.ndarray) -> np.ndarray:
    """Camera centre (0..1) for each timestamp."""
    arr = np.asarray(path, dtype=float)
    return np.interp(times, arr[:, 0], arr[:, 1])
