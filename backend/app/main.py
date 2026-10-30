"""FastAPI entry point. Also serves the built React app so the whole tool is one process."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, jobs
from .routers import projects

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    jobs.recover_interrupted()  # resume work that a previous run (or crash) left half-done
    yield


app = FastAPI(title="Vertical Clipper", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
app.include_router(projects.router)

config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

if (config.FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not found")  # unknown API routes must not return the HTML page
        candidate = (config.FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and config.FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(config.FRONTEND_DIST / "index.html")
