"""
AI Log/Incident Triage Assistant: API entry point.

Start it from the backend folder with the virtual environment active:

    uvicorn app.main:app --reload --port 8000

Interactive API documentation is served at /docs (Swagger UI) and /redoc.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, dashboard, health, incidents, knowledge, logs, reports
from app.core.config import Settings, get_settings
from app.core.database import init_db, make_engine, make_session_factory
from app.core.errors import error_response, register_exception_handlers
from app.rag.retriever import KnowledgeIndex

logger = logging.getLogger("triage")

DESCRIPTION = """
Ingest application or routing logs, group related errors, detect incidents, and get runbook-backed,
READ-ONLY diagnostic suggestions with links to the log records they are based on.

**Safety:** this API has no endpoint that runs commands, restarts services or changes configuration.
It only analyses evidence and recommends checks for a human to review.

Every item it returns says where it came from: `observed` (a log record), `runbook` (retrieved
documentation), `rule` (a deterministic check) or `ai_hypothesis` (a model's suggestion).

Errors always look like `{"error": {"code": "...", "message": "...", "details": null}}`.
All sample data is synthetic.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Tests call this with their own settings (temporary storage folder)."""
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    engine = make_engine(settings.resolved_database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings.ensure_directories()  # folders and tables are created at start, not at import
        init_db(engine)
        yield
        engine.dispose()

    app = FastAPI(title=settings.app_name, version=settings.app_version, description=DESCRIPTION, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.kb = KnowledgeIndex()  # the runbook search index (built on first use)
    app.state.ai_http_client = None  # tests put a mocked httpx client here; None means a normal client is created per call

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    @app.middleware("http")
    async def reject_oversized_uploads(request: Request, call_next):  # noqa: ANN001, ANN202
        """Stop an obviously too-large upload before the body is read (the exact limit is checked while reading)."""
        if request.method == "POST" and request.url.path in {"/api/logs/upload"}:
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > settings.max_upload_bytes + 1024 * 1024:
                return error_response(413, "file_too_large", f"The file is larger than the {settings.max_upload_mb} MB limit.")
        if request.method == "POST" and request.url.path == "/api/knowledge/documents/upload":
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > settings.max_runbook_bytes + 1024 * 1024:
                return error_response(413, "file_too_large", f"The file is larger than the {settings.max_runbook_mb} MB limit.")
        return await call_next(request)

    register_exception_handlers(app)
    for router in (health.router, logs.router, analysis.router, incidents.router, dashboard.router, knowledge.router, reports.router):
        app.include_router(router, prefix="/api")

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": settings.app_name, "version": settings.app_version, "docs": "/docs", "health": "/api/health"}

    return app


app = create_app()
