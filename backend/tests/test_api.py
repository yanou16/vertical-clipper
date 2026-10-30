import pytest
from fastapi.testclient import TestClient

from app import config, jobs, store
from app.main import app
from app.models import Clip


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    # Never start real background work from API tests.
    monkeypatch.setattr(jobs, "submit_pipeline", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "submit_exports", lambda *a, **k: None)
    return TestClient(app)


@pytest.fixture()
def ready_project(client):
    project = store.create("demo", "upload")

    def make_ready(p):
        p.status, p.duration, p.width, p.height, p.fps = "ready", 120.0, 1920, 1080, 30.0
        p.clips = [Clip(id="aaaa1111", start=0, end=30), Clip(id="bbbb2222", start=30, end=60)]
    store.update(project.id, make_ready)
    return project.id


def test_rejects_non_http_urls(client):
    assert client.post("/api/projects/from-url", json={"url": "file:///etc/passwd"}).status_code == 422
    assert client.post("/api/projects/from-url", json={"url": "javascript:alert(1)"}).status_code == 422


def test_rejects_unsupported_upload_type(client):
    res = client.post("/api/projects/upload", files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert res.status_code == 415


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    res = client.post("/api/projects/upload", files={"file": ("a.mp4", b"x" * 10, "video/mp4")})
    assert res.status_code == 413
    assert store.list_all() == []  # the half-written project is cleaned up


def test_unknown_and_malicious_project_ids(client):
    assert client.get("/api/projects/doesnotexist").status_code == 404
    assert client.get("/api/projects/..%2F..%2Fetc").status_code == 404


def test_patch_clip_changes_boundaries(client, ready_project):
    res = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json={"end": 45})
    assert res.status_code == 200
    assert res.json()["clips"][0]["end"] == 45


@pytest.mark.parametrize("body", [{"end": 0.5}, {"start": 29.5}])
def test_patch_clip_rejects_too_short(client, ready_project, body):
    res = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json=body)
    assert res.status_code == 422


def test_patch_clip_rejects_too_long(client, ready_project):
    store.update(ready_project, lambda p: setattr(p, "duration", 600.0))
    res = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json={"end": 400})
    assert res.status_code == 422


def test_end_is_clamped_to_video_duration(client, ready_project):
    res = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json={"end": 500})
    assert res.json()["clips"][0]["end"] == 120.0


def test_unknown_api_route_is_a_json_404_not_the_html_page(client):
    res = client.get("/api/nope")
    assert res.status_code == 404 and res.headers["content-type"].startswith("application/json")


def test_clip_is_clamped_to_video_duration(client, ready_project):
    res = client.post(f"/api/projects/{ready_project}/clips", json={"start": 100, "end": 140})
    assert res.status_code == 201
    assert res.json()["clips"][-1]["end"] == 120.0


def test_editing_a_clip_invalidates_its_export(client, ready_project):
    def mark_done(p):
        p.clips[0].export_status, p.clips[0].exported_range = "done", (0.0, 30.0)
    store.update(ready_project, mark_done)
    res = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json={"end": 40})
    assert res.json()["clips"][0]["export_status"] == "idle"


def test_download_requires_a_finished_export(client, ready_project):
    assert client.get(f"/api/projects/{ready_project}/clips/aaaa1111/download").status_code == 409
    assert client.get(f"/api/projects/{ready_project}/download").status_code == 409


def test_cannot_edit_while_processing(client):
    project = store.create("busy", "upload")
    assert client.post(f"/api/projects/{project.id}/clips", json={"start": 0, "end": 10}).status_code == 409
