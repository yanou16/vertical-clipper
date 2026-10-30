"""Download progress parsing and the stream-choice rule."""
import pytest

from app.services.ingest import format_args, parse_progress, stream_after


def test_video_progress_takes_most_of_the_bar():
    fraction, text = parse_progress("[download]  50.0% of ~ 210.14MiB at  288.00KiB/s ETA 07:12", stream=0)
    assert fraction == pytest.approx(0.475)
    assert text == "Downloading the video 50% of 210.14MiB at 288.00KiB/s, 07:12 left"


def test_audio_fills_the_last_slice_of_the_bar():
    fraction, text = parse_progress("[download] 100% of 5.20MiB at 1.10MiB/s ETA 00:00", stream=1)
    assert fraction == pytest.approx(1.0)
    assert text.startswith("Downloading the audio 100%")


def test_unknown_speed_and_eta_are_left_out_instead_of_shown_as_nonsense():
    _, text = parse_progress("[download]   3.0% of ~ 100.00MiB at Unknown B/s ETA Unknown", stream=0)
    assert text == "Downloading the video 3% of 100.00MiB"


def test_progress_never_goes_past_100_percent():
    fraction, _ = parse_progress("[download] 100.0% of 10.00MiB at 1.00MiB/s ETA 00:00", stream=0)
    assert fraction <= 0.95 + 1e-9


@pytest.mark.parametrize("line", ["[youtube] Extracting URL: x", "[download] Destination: source.f298.mp4", "", "Some title"])
def test_other_lines_are_not_progress(line):
    assert parse_progress(line, stream=0) is None


def test_light_mode_prefers_30_fps_and_vp9_but_keeps_the_height_cap():
    light = format_args(720, light=True)
    normal = format_args(720)
    assert "bv*[height<=720]+ba/b[height<=720]/b" in light
    sort = light[light.index("-S") + 1]
    assert "fps:30" in sort and "vcodec:vp9" in sort and sort.startswith("res:720")
    assert "fps" not in normal[normal.index("-S") + 1]


def _run_lines(lines):
    """Feed progress lines through stream_after like the download loop does; return the stream of each."""
    stream, last, seen = 0, 0.0, []
    for line in lines:
        stream, last = stream_after(line, last, stream)
        seen.append(stream)
    return seen


def test_audio_is_detected_when_the_percentage_falls_back_to_zero():
    video = [f"[download] {p:5.1f}% of 100.00MiB at 1.00MiB/s ETA 00:10" for p in (0.0, 10.3, 41.4, 99.9, 100.0)]
    audio = [f"[download] {p:5.1f}% of 5.00MiB at 1.00MiB/s ETA 00:01" for p in (0.0, 50.0, 100.0)]
    assert _run_lines(video + audio) == [0, 0, 0, 0, 0, 1, 1, 1]


def test_a_single_stream_download_never_switches_to_audio():
    lines = [f"[download] {p:5.1f}% of 100.00MiB at 1.00MiB/s ETA 00:10" for p in (0.0, 25.0, 50.0, 75.0, 100.0)]
    assert set(_run_lines(lines)) == {0}


def test_lines_that_are_not_progress_do_not_change_the_stream():
    assert stream_after("some title", 50.0, 0) == (0, 50.0)
