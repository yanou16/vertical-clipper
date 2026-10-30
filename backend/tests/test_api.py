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


def _mark_exported(project_id, clip_index=0):
    def mark_done(p):
        c = p.clips[clip_index]
        c.export_status, c.exported_revision = "done", c.revision
    store.update(project_id, mark_done)


def test_editing_a_clip_invalidates_its_export(client, ready_project):
    _mark_exported(ready_project)
    res = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json={"end": 40})
    clip = res.json()["clips"][0]
    assert clip["export_status"] == "idle" and clip["revision"] == 1


def test_renaming_a_clip_keeps_its_export(client, ready_project):
    _mark_exported(ready_project)
    res = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json={"title": "Intro"})
    clip = res.json()["clips"][0]
    assert clip["export_status"] == "done" and clip["revision"] == 0 and clip["title"] == "Intro"


def test_download_requires_a_finished_export(client, ready_project):
    assert client.get(f"/api/projects/{ready_project}/clips/aaaa1111/download").status_code == 409
    assert client.get(f"/api/projects/{ready_project}/download").status_code == 409


def test_cannot_edit_while_processing(client):
    project = store.create("busy", "upload")
    assert client.post(f"/api/projects/{project.id}/clips", json={"start": 0, "end": 10}).status_code == 409


# ---- YouTube quality -------------------------------------------------------------

def test_quality_must_be_a_known_choice(client):
    res = client.post("/api/projects/from-url", json={"url": "https://youtu.be/x", "quality": 999})
    assert res.status_code == 422


def test_quality_is_stored_on_the_project(client):
    res = client.post("/api/projects/from-url", json={"url": "https://youtu.be/x", "quality": 2160})
    assert res.status_code == 201 and res.json()["quality"] == 2160


def test_quality_defaults_to_the_sharper_setting(client):
    res = client.post("/api/projects/from-url", json={"url": "https://youtu.be/x"})
    assert res.json()["quality"] == config.DEFAULT_QUALITY


# ---- manual framing ------------------------------------------------------------------

def test_keyframes_are_saved_sorted_and_bump_the_revision(client, ready_project):
    res = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111",
                       json={"keyframes": [[10, 0.7], [2, 0.3]]})
    clip = res.json()["clips"][0]
    assert clip["keyframes"] == [[2, 0.3], [10, 0.7]] and clip["revision"] == 1


def test_saving_the_same_keyframes_twice_changes_nothing(client, ready_project):
    body = {"keyframes": [[2, 0.3]]}
    client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json=body)
    clip = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json=body).json()["clips"][0]
    assert clip["revision"] == 1


def test_changing_the_framing_invalidates_the_export(client, ready_project):
    _mark_exported(ready_project)
    res = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json={"keyframes": [[5, 0.4]]})
    assert res.json()["clips"][0]["export_status"] == "idle"


def test_an_empty_list_goes_back_to_automatic_framing(client, ready_project):
    client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json={"keyframes": [[5, 0.4]]})
    clip = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json={"keyframes": []}).json()["clips"][0]
    assert clip["keyframes"] == []


@pytest.mark.parametrize("points", [[[5, 1.5]], [[5, -0.1]], [[-1, 0.5]], [[500, 0.5]]])
def test_keyframes_must_be_inside_the_video_and_frame(client, ready_project, points):
    res = client.patch(f"/api/projects/{ready_project}/clips/aaaa1111", json={"keyframes": points})
    assert res.status_code == 422


def test_faces_endpoint_is_empty_for_projects_without_face_data(client, ready_project):
    res = client.get(f"/api/projects/{ready_project}/faces", params={"start": 0, "end": 30})
    assert res.status_code == 200 and res.json() == []


def test_faces_endpoint_returns_only_the_requested_range(client, ready_project):
    store.write_json(ready_project, "faces.json", [[1.0, [[0.4, 0.4, 0.1, 0.2]]], [50.0, [[0.6, 0.4, 0.1, 0.2]]]])
    res = client.get(f"/api/projects/{ready_project}/faces", params={"start": 0, "end": 30})
    assert [s["t"] for s in res.json()] == [1.0]
    assert res.json()[0]["faces"][0] == {"cx": 0.4, "cy": 0.4, "w": 0.1, "h": 0.2}


def test_faces_endpoint_refuses_huge_ranges(client, ready_project):
    assert client.get(f"/api/projects/{ready_project}/faces", params={"start": 0, "end": 5000}).status_code == 422


# ---- retry and cancel ---------------------------------------------------------------------

def test_only_a_failed_project_can_be_retried(client, ready_project):
    assert client.post(f"/api/projects/{ready_project}/retry").status_code == 409


def test_retry_puts_a_failed_project_back_in_the_queue(client):
    project = store.create("broken", "upload")
    store.update(project.id, lambda p: (setattr(p, "status", "error"), setattr(p, "error", "boom")))
    res = client.post(f"/api/projects/{project.id}/retry")
    assert res.status_code == 200
    assert res.json()["status"] == "queued" and res.json()["error"] is None


def test_cancel_returns_waiting_exports_to_idle_and_spares_finished_ones(client, ready_project):
    def setup(p):
        p.clips[0].export_status = "queued"
        p.clips[1].export_status, p.clips[1].exported_revision = "done", p.clips[1].revision
    store.update(ready_project, setup)
    res = client.post(f"/api/projects/{ready_project}/exports/cancel", json={})
    statuses = [c["export_status"] for c in res.json()["clips"]]
    assert statuses == ["idle", "done"]
