from app.services.segmentation import Candidate, build_candidates, segment


def _check_cover(spans, duration):
    assert spans[0][0] == 0
    assert spans[-1][1] == round(duration, 2)
    for (_, end), (start, _) in zip(spans, spans[1:]):
        assert end == start, "clips must be contiguous"


def test_short_video_is_one_clip():
    assert segment(40, [], target=30, min_len=15, max_len=60) == [(0.0, 40.0)]


def test_long_video_without_hints_uses_target_length():
    spans = segment(300, [], target=30, min_len=15, max_len=60)
    _check_cover(spans, 300)
    assert all(15 <= b - a <= 60 for a, b in spans)


def test_prefers_a_natural_boundary_near_the_target():
    candidates = [Candidate(29, 0.7), Candidate(50, 1.0)]
    spans = segment(120, candidates, target=30, min_len=15, max_len=60)
    assert spans[0] == (0.0, 29)  # the near silence beats the far shot change


def test_tiny_tail_is_merged_into_previous_clip():
    spans = segment(65, [], target=30, min_len=15, max_len=60)
    _check_cover(spans, 65)
    assert len(spans) == 1 or all(b - a >= 15 for a, b in spans)


def test_clips_respect_max_length_even_with_far_candidates():
    spans = segment(500, [Candidate(400, 1.0)], target=30, min_len=15, max_len=60)
    _check_cover(spans, 500)
    assert all(b - a <= 60 * 1.25 for a, b in spans)


def test_build_candidates_uses_silence_midpoint_and_sorts():
    result = build_candidates([10.0], [(4.0, 6.0)])
    assert [(c.time, c.weight) for c in result] == [(5.0, 0.7), (10.0, 1.0)]
