"""FastAPI-Anwendung: Schnittstelle unter /api/v1 und das gebaute Frontend."""

from __future__ import annotations

import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import __version__, catalog
from .api import family, imports, plans, recipes
from .config import Settings, get_settings
from .db import Database
from .importer import ImportRunner
from .migrate import upgrade

log = logging.getLogger("delikatessen")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.imports.resume_pending()
        yield
        app.state.imports.shutdown()

    app = FastAPI(
        title="Delikatessen",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/v1/openapi.json",
        redoc_url=None,
    )
    db = Database(settings.db_path)
    upgrade(db.engine)
    with db.sessionmaker() as session:
        catalog.seed(session)
    settings.image_dir.mkdir(parents=True, exist_ok=True)

    app.state.settings = settings
    app.state.db = db
    app.state.imports = ImportRunner(db.sessionmaker, settings)
    app.state.today_override = None

    api = APIRouter(prefix="/api/v1")
    for module in (recipes, plans, family, imports):
        api.include_router(module.router)
    app.include_router(api)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    if settings.frontend_dir:
        mount_frontend(app, settings.frontend_dir.resolve())
    return app


def mount_frontend(app: FastAPI, root: Path) -> None:
    index = root / "index.html"
    if not index.is_file():
        log.warning("Kein gebautes Frontend unter %s", root)
        return

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Nicht gefunden")
        target = (root / path).resolve()
        if path and target.is_file() and target.is_relative_to(root):
            if path.startswith("assets/"):
                cache = "public, max-age=31536000, immutable"
            else:
                cache = "no-cache"
            return FileResponse(target, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    @app.post("/teilen", include_in_schema=False)
    def share_fallback():
        # Ohne Service Worker landet das Teilen-Ziel hier: einfach die App öffnen
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
