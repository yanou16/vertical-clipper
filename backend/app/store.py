"""Tiny file-based project store: one folder + one project.json per project.

Good enough for a single-machine tool; swap for SQLite/Postgres if it ever goes multi-user.
"""
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from . import config
from .models import Project

_lock = threading.RLock()
_ID_RE = re.compile(r"^[a-f0-9]{12}$")


def valid_id(value: str) -> bool:
    return bool(_ID_RE.match(value))


def project_dir(project_id: str) -> Path:
    if not valid_id(project_id):  # also blocks path traversal
        raise KeyError(project_id)
    return config.PROJECTS_DIR / project_id


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def create(title: str, source: str, source_url: Optional[str] = None) -> Project:
    project = Project(id=new_id(), title=title, source=source, source_url=source_url,
                      created_at=time.time())
    project_dir(project.id).mkdir(parents=True, exist_ok=True)
    save(project)
    return project


def get(project_id: str) -> Project:
    path = project_dir(project_id) / "project.json"
    with _lock:
        if not path.exists():
            raise KeyError(project_id)
        return Project.model_validate_json(path.read_text())


def save(project: Project) -> None:
    path = project_dir(project.id) / "project.json"
    tmp = path.with_suffix(".tmp")
    with _lock:
        tmp.write_text(project.model_dump_json())
        os.replace(tmp, path)  # atomic: readers never see a half-written file


def update(project_id: str, mutate: Callable[[Project], None]) -> Project:
    """Read-modify-write under a lock so background jobs and API calls don't clobber each other."""
    with _lock:
        project = get(project_id)
        mutate(project)
        save(project)
        return project


def list_all() -> list[Project]:
    if not config.PROJECTS_DIR.exists():
        return []
    projects = []
    for entry in config.PROJECTS_DIR.iterdir():
        try:
            projects.append(get(entry.name))
        except (KeyError, ValueError):
            continue
    return sorted(projects, key=lambda p: p.created_at, reverse=True)


def delete(project_id: str) -> None:
    import shutil
    folder = project_dir(project_id)
    with _lock:
        if folder.exists():
            shutil.rmtree(folder)


def write_json(project_id: str, name: str, data) -> None:
    (project_dir(project_id) / name).write_text(json.dumps(data))


def read_json(project_id: str, name: str):
    path = project_dir(project_id) / name
    return json.loads(path.read_text()) if path.exists() else None
