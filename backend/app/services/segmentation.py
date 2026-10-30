"""Split a long video into clips.

Strategy: aim for clips close to `target` seconds, but prefer to cut where it feels natural -
on a shot change, or in the middle of a pause in the audio. Pure function => easy to test.
"""
from dataclasses import dataclass

# How much we like each kind of boundary (higher = better place to cut).
CUT_WEIGHT = 1.0
SILENCE_WEIGHT = 0.7


@dataclass
class Candidate:
    time: float
    weight: float


def build_candidates(cuts: list[float], silences: list[tuple[float, float]]) -> list[Candidate]:
    candidates = [Candidate(t, CUT_WEIGHT) for t in cuts]
    candidates += [Candidate((a + b) / 2, SILENCE_WEIGHT) for a, b in silences]
    return sorted(candidates, key=lambda c: c.time)


def segment(
    duration: float,
    candidates: list[Candidate],
    target: float = 30.0,
    min_len: float = 15.0,
    max_len: float = 60.0,
) -> list[tuple[float, float]]:
    """Return [(start, end)] covering the whole video, each between min_len and max_len when possible."""
    min_len = min(min_len, max_len)
    target = max(min_len, min(target, max_len))

    if duration <= max_len:
        return [(0.0, round(duration, 2))]

    clips: list[tuple[float, float]] = []
    start = 0.0
    while duration - start > max_len:
        lo, hi, ideal = start + min_len, start + max_len, start + target
        # Score = natural-ness of the boundary minus distance from the ideal length.
        window = [c for c in candidates if lo <= c.time <= hi]
        if window:
            best = max(window, key=lambda c: c.weight - abs(c.time - ideal) / target)
            end = best.time
        else:
            end = ideal  # nothing natural nearby: hard cut at the target length
        clips.append((round(start, 2), round(end, 2)))
        start = end

    remainder = duration - start
    if remainder < min_len and clips:
        # Too short to stand alone: glue to the previous clip if that doesn't overshoot much.
        prev_start, _ = clips[-1]
        if duration - prev_start <= max_len * 1.25:
            clips[-1] = (prev_start, round(duration, 2))
            return clips
    clips.append((round(start, 2), round(duration, 2)))
    return clips
