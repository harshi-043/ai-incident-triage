"""Run an analysis (grouping + incident detection) and read its results."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import MAX_PAGE_SIZE, check_id, get_app_settings
from app.core.config import Settings
from app.core.database import get_session
from app.core.errors import not_found
from app.incident.types import DetectionParams
from app.ingestion.normalize import LEVELS
from app.models.tables import ErrorGroup, LogSource
from app.repositories import incidents as repo
from app.repositories import logs as log_repo
from app.services import analysis_service

router = APIRouter(tags=["analysis"])


class AnalyzeRequest(BaseModel):
    source_id: str
    similarity_threshold: float | None = Field(default=None, ge=0.1, le=0.99, description="Wording similarity needed to merge two message patterns")
    gap_minutes: int | None = Field(default=None, ge=1, le=240, description="A longer quiet gap between errors starts a new incident")
    min_errors: int | None = Field(default=None, ge=2, le=10_000, description="Errors needed inside one window to create an incident")
    merge_across_services: bool = Field(default=False, description="Allow similar messages from different services to merge")
    force_new: bool = Field(default=False, description="Create a new analysis even if the same settings were analysed before")


@router.post("/logs/analyze", status_code=201)
def analyze(body: AnalyzeRequest, session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    check_id(body.source_id, "source")
    params = DetectionParams(
        similarity_threshold=body.similarity_threshold if body.similarity_threshold is not None else settings.similarity_threshold,
        gap_minutes=body.gap_minutes if body.gap_minutes is not None else settings.incident_gap_minutes,
        min_errors=body.min_errors if body.min_errors is not None else settings.incident_min_errors,
        merge_across_services=body.merge_across_services,
    )
    analysis, reused = analysis_service.run_analysis(session, settings, body.source_id, params, force_new=body.force_new)
    source = session.get(LogSource, analysis.source_id)
    return {"analysis": repo.analysis_to_dict(analysis, source), "reused": reused}


@router.get("/analyses")
def list_analyses(source_id: str | None = None, session: Session = Depends(get_session)):
    if source_id:
        check_id(source_id, "source")
    return {"items": [repo.analysis_to_dict(a, s) for a, s in repo.list_analyses(session, source_id)]}


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str, session: Session = Depends(get_session)):
    analysis = repo.get_analysis(session, check_id(analysis_id, "analysis"))
    if analysis is None:
        raise not_found("analysis", analysis_id)
    return {"analysis": repo.analysis_to_dict(analysis, session.get(LogSource, analysis.source_id))}


@router.get("/analyses/{analysis_id}/groups")
def list_groups(
    analysis_id: str,
    q: Annotated[str | None, Query(max_length=200)] = None,
    min_count: Annotated[int, Query(ge=1)] = 1,
    level: Annotated[str | None, Query(description="Highest level in the group")] = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 25,
    session: Session = Depends(get_session),
):
    if repo.get_analysis(session, check_id(analysis_id, "analysis")) is None:
        raise not_found("analysis", analysis_id)
    if level and level.upper() not in LEVELS:
        level = None
    rows, total = repo.list_groups(session, analysis_id, q=q, min_count=min_count, level=level.upper() if level else None,
                                   page=page, page_size=page_size)
    return {"items": [repo.group_to_dict(g) for g in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/groups/{group_id}")
def get_group(group_id: str, session: Session = Depends(get_session)):
    group = session.get(ErrorGroup, check_id(group_id, "group"))
    if group is None:
        raise not_found("group", group_id)
    samples = log_repo.get_records_by_ids(session, group.sample_record_ids)
    return {"group": repo.group_to_dict(group, detail=True), "samples": [log_repo.record_to_dict(r) for r in samples]}
