"""Recovery after a server restart, and the YouTube format rule."""
import pytest

from app import config, jobs, store
from app.models import Clip
from app.services import ingest


@pytest.fixture()
def recorder(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    calls = {"pipeline": [], "exports": []}
    monkeypatch.setattr(jobs, "submit_pipeline", lambda pid, url=None: calls["pipeline"].append((pid, url)))
    monkeypatch.setattr(jobs, "submit_exports", lambda pid, ids: calls["exports"].append((pid, list(ids))))
    return calls


def test_interrupted_youtube_project_is_resumed(recorder):
    project = store.create("clip", "youtube", "https://youtu.be/abc")
    store.update(project.id, lambda p: setattr(p, "status", "analyzing"))
    jobs.recover_interrupted()
    again = store.get(project.id)
    assert again.status == "queued" and again.attempts == 1
    assert recorder["pipeline"] == [(project.id, "https://youtu.be/abc")]


def test_interrupted_upload_is_resumed_without_a_url(recorder):
    project = store.create("clip", "upload")
    jobs.recover_interrupted()  # status is "queued": a restart interrupted it before it started
    assert recorder["pipeline"] == [(project.id, None)]


def test_a_project_that_keeps_getting_interrupted_is_marked_as_failed(recorder):
    project = store.create("clip", "upload")
    store.update(project.id, lambda p: (setattr(p, "status", "analyzing"),
                                        setattr(p, "attempts", config.MAX_RECOVERY_ATTEMPTS)))
    jobs.recover_interrupted()
    assert store.get(project.id).status == "error" and recorder["pipeline"] == []


def test_exports_interrupted_by_a_restart_are_queued_again(recorder):
    project = store.create("clip", "upload")

    def ready(p):
        p.status = "ready"
        p.clips = [Clip(id="a", start=0, end=10, export_status="rendering"),
                   Clip(id="b", start=10, end=20, export_status="done"),
                   Clip(id="c", start=20, end=30, export_status="queued")]
    store.update(project.id, ready)
    jobs.recover_interrupted()
    assert recorder["exports"] == [(project.id, ["a", "c"])]


def test_finished_projects_are_left_alone(recorder):
    project = store.create("clip", "upload")
    store.update(project.id, lambda p: setattr(p, "status", "ready"))
    jobs.recover_interrupted()
    assert recorder == {"pipeline": [], "exports": []}


def test_format_rule_caps_the_height_and_prefers_the_highest_bitrate():
    args = ingest.format_args(1440)
    assert "bv*[height<=1440]+ba/b[height<=1440]/b" in args
    assert args[args.index("-S") + 1] == "res:1440,proto,vbr"
