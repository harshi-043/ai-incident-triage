"""Log upload, sample loading, browsing and the data-quality report."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import MAX_PAGE_SIZE, check_id, get_app_settings
from app.core.config import Settings
from app.core.database import get_session
from app.core.errors import AppError, not_found
from app.ingestion.normalize import LEVELS
from app.repositories import logs as repo
from app.services import ingest_service

router = APIRouter(prefix="/logs", tags=["logs"])


class SampleRequest(BaseModel):
    name: str = Field(description="'application' or 'routing'")
    file: str | None = Field(default=None, description="Optional file of the sample, for example 'application.csv'")
    force: bool = False


def _ingest_response(source, quality, created: bool) -> dict:
    return {"source": repo.source_to_dict(source), "quality": quality, "already_ingested": not created}


@router.post("/upload", status_code=201)
async def upload_log(
    file: UploadFile = File(...),
    column_mapping: Annotated[str | None, Form(description='JSON such as {"message": "msg", "timestamp": "time"}')] = None,
    force: Annotated[bool, Form(description="Store again even when the same file was uploaded before")] = False,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
):
    # Read at most one byte more than the limit, so a huge upload is never loaded into memory.
    data = await file.read(settings.max_upload_bytes + 1)
    mapping = ingest_service.parse_column_mapping(column_mapping)
    source, quality, created = ingest_service.ingest_upload(
        session, settings, data, file.filename, column_mapping=mapping, force=force)
    return _ingest_response(source, quality, created)


@router.get("/samples")
def list_samples():
    return {"items": [{"name": k, **v} for k, v in ingest_service.SAMPLES.items()],
            "note": "All sample data is synthetic and generated from a fixed seed."}


@router.post("/samples", status_code=201)
def load_sample(body: SampleRequest, session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    source, quality, created = ingest_service.load_sample(session, settings, body.name, body.file, force=body.force)
    return _ingest_response(source, quality, created)


@router.get("/sources")
def list_sources(session: Session = Depends(get_session)):
    return {"items": [repo.source_to_dict(s) for s in repo.list_sources(session)]}


@router.get("/sources/{source_id}")
def get_source(source_id: str, session: Session = Depends(get_session)):
    source = repo.get_source(session, check_id(source_id, "source"))
    if source is None:
        raise not_found("source", source_id)
    return {"source": repo.source_to_dict(source), "quality": source.quality, "filters": repo.filter_options(session, source.id)}


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: str, session: Session = Depends(get_session)):
    """Deletes the source with its records, analyses and incidents."""
    source = repo.get_source(session, check_id(source_id, "source"))
    if source is None:
        raise not_found("source", source_id)
    repo.delete_source(session, source)


@router.get("/quality")
def quality_report(source_id: str, session: Session = Depends(get_session)):
    source = repo.get_source(session, check_id(source_id, "source"))
    if source is None:
        raise not_found("source", source_id)
    return {"source": repo.source_to_dict(source), "quality": source.quality}


@router.get("")
def list_logs(
    source_id: str,
    level: Annotated[list[str] | None, Query(description="Repeat to select several levels")] = None,
    service: Annotated[list[str] | None, Query(description="Repeat to select several services")] = None,
    q: Annotated[str | None, Query(max_length=200, description="Search in message, request id, exception, service")] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    min_status: Annotated[int | None, Query(ge=100, le=599)] = None,
    request_id: Annotated[str | None, Query(max_length=80)] = None,
    sort: Annotated[str, Query(pattern="^(timestamp|level|service|http_status|latency_ms|line_no|id)$")] = "timestamp",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    session: Session = Depends(get_session),
):
    check_id(source_id, "source")
    if repo.get_source(session, source_id) is None:
        raise not_found("source", source_id)
    levels = [lv.upper() for lv in level] if level else None
    if levels and any(lv not in LEVELS for lv in levels):
        raise AppError(422, "invalid_level", f"Level must be one of: {', '.join(LEVELS)}.")
    naive = lambda d: d.replace(tzinfo=None) if d and d.tzinfo is None else (d.astimezone(None).replace(tzinfo=None) if d else None)  # noqa: E731
    rows, total = repo.query_logs(
        session, source_id=source_id, levels=levels, services=service, q=q, start=naive(start), end=naive(end),
        min_status=min_status, request_id=request_id, sort=sort, order=order, page=page, page_size=page_size)
    return {"items": [repo.record_to_dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/{log_id}")
def get_log(log_id: int, context: Annotated[int, Query(ge=0, le=25, description="Neighbouring records to include")] = 5,
            session: Session = Depends(get_session)):
    record = repo.get_record(session, log_id)
    if record is None:
        raise not_found("log", log_id)
    neighbours = repo.get_context(session, record, context)
    return {
        "record": repo.record_to_dict(record, full=True),
        "context": {k: [repo.record_to_dict(r) for r in v] for k, v in neighbours.items()},
    }
