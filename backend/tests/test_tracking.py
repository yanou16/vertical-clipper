import numpy as np

from app.services.analysis import Analysis, Face
from app.services.tracking import build_crop_path, centers_at, crop_half_width, effective_path


def _analysis(xs, cuts=(), fps=4.0):
    """xs[i] = x position of a single face at sample i (None = no face)."""
    a = Analysis(sample_fps=fps, cuts=list(cuts))
    for i, x in enumerate(xs):
        a.times.append(i / fps)
        a.faces.append([] if x is None else [Face(cx=x, area=0.05)])
    return a


def test_no_faces_falls_back_to_centered_crop():
    path, mode = build_crop_path(_analysis([None] * 40), 10, 1920, 1080)
    assert mode == "center" and path == [[0.0, 0.5]]


def test_camera_follows_a_moving_subject():
    xs = list(np.linspace(0.3, 0.7, 40))
    path, mode = build_crop_path(_analysis(xs), 10, 1920, 1080)
    assert mode == "faces"
    centers = centers_at(path, np.array([0.0, 9.9]))
    assert centers[0] < 0.4 and centers[1] > 0.6


def test_static_subject_keeps_camera_still_despite_jitter():
    rng = np.random.default_rng(0)
    xs = list(0.5 + rng.uniform(-0.01, 0.01, 80))
    path, _ = build_crop_path(_analysis(xs), 20, 1920, 1080)
    centers = centers_at(path, np.linspace(0, 19, 100))
    assert centers.max() - centers.min() < 0.01


def test_camera_stays_inside_the_frame():
    path, _ = build_crop_path(_analysis([0.01] * 40), 10, 1920, 1080)
    half = crop_half_width(1920, 1080)
    assert min(c for _, c in path) >= half - 1e-3  # path values are rounded to 4 decimals


def test_camera_jumps_at_a_shot_change_instead_of_gliding():
    xs = [0.3] * 20 + [0.7] * 20
    path, _ = build_crop_path(_analysis(xs, cuts=[4.9]), 10, 1920, 1080)
    before, after = centers_at(path, np.array([4.8, 5.0]))
    assert before < 0.4 and after > 0.6  # already on the new subject right after the cut


def test_gaps_without_a_face_hold_the_last_position():
    xs = [0.3] * 10 + [None] * 10 + [0.3] * 10
    path, _ = build_crop_path(_analysis(xs), 7.5, 1920, 1080)
    centers = centers_at(path, np.linspace(0, 7, 30))
    assert np.allclose(centers, centers[0], atol=0.01)


# ---- manual framing -------------------------------------------------------------

def test_without_keyframes_the_automatic_path_is_used():
    auto = [[0.0, 0.4], [5.0, 0.6]]
    assert effective_path(auto, [], 1920, 1080) is auto


def test_keyframes_replace_the_automatic_path_and_are_sorted():
    path = effective_path([[0.0, 0.5]], [(8.0, 0.7), (2.0, 0.3)], 1920, 1080)
    assert path == [[2.0, 0.3], [8.0, 0.7]]


def test_a_single_keyframe_locks_the_framing_for_the_whole_clip():
    path = effective_path([[0.0, 0.5]], [(4.0, 0.3)], 1920, 1080)
    centers = centers_at(path, np.array([0.0, 4.0, 100.0]))
    assert np.allclose(centers, 0.3)


def test_keyframes_cannot_push_the_window_out_of_the_frame():
    half = crop_half_width(1920, 1080)
    path = effective_path([], [(1.0, 0.0), (2.0, 1.0)], 1920, 1080)
    assert path[0][1] == half and path[1][1] == 1 - half
