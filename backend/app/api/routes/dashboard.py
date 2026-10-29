"""GET /api/dashboard/summary"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import check_id
from app.core.database import get_session
from app.services.dashboard_service import dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(source_id: str | None = None, session: Session = Depends(get_session)):
    """Metrics for one log source (the newest one when `source_id` is not given). `has_data` is false when nothing is loaded."""
    if source_id:
        check_id(source_id, "source")
    return dashboard_summary(session, source_id)
