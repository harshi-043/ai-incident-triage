"""GET /api/health: is the service up, and are its parts usable?"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import get_session
from app.api.deps import get_app_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request, session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    checks: dict[str, str] = {}
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001 - any failure means "not ok"; details stay in the server log
        checks["database"] = "error"
    checks["storage"] = "ok" if settings.storage_dir.exists() else "error"
    healthy = all(value == "ok" for value in checks.values())
    body = {
        "status": "ok" if healthy else "degraded",
        "version": settings.app_version,
        "checks": checks,
        "ai_provider": settings.ai_provider,
        "embedding_backend": settings.embedding_backend,
    }
    return JSONResponse(status_code=200 if healthy else 503, content=body)
