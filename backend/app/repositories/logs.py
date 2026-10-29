"""Database reads and writes for log sources and log records."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, func, insert, or_, select
from sqlalchemy.orm import Session

from app.ingestion.normalize import iso_z
from app.models.tables import LogRecord, LogSource

INSERT_CHUNK = 2000
SORTABLE = {
    "timestamp": LogRecord.timestamp, "service": LogRecord.service, "http_status": LogRecord.http_status,
    "latency_ms": LogRecord.latency_ms, "line_no": LogRecord.line_no, "id": LogRecord.id,
    "level": case(
        (LogRecord.level == "DEBUG", 0), (LogRecord.level == "INFO", 1), (LogRecord.level == "WARNING", 2),
        (LogRecord.level == "ERROR", 3), else_=4,
    ),
}


def record_to_dict(r: LogRecord, *, full: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": r.id, "source_id": r.source_id, "line_no": r.line_no, "timestamp": iso_z(r.timestamp), "level": r.level,
        "service": r.service, "host": r.host, "request_id": r.request_id, "route_id": r.route_id,
        "endpoint": r.endpoint, "http_status": r.http_status, "latency_ms": r.latency_ms,
        "exception_type": r.exception_type, "message": r.message,
    }
    if full:
        data.update({
            "environment": r.environment, "trace_id": r.trace_id, "normalized_message": r.normalized_message,
            "stack_trace": r.stack_trace, "raw_line": r.raw_line, "extra": r.extra or {},
        })
    return data


def source_to_dict(s: LogSource) -> dict[str, Any]:
    return {
        "id": s.id, "name": s.name, "original_filename": s.original_filename, "kind": s.kind, "format": s.format,
        "size_bytes": s.size_bytes, "record_count": s.record_count, "created_at": iso_z(s.created_at),
    }


def find_source_by_hash(session: Session, content_hash: str) -> LogSource | None:
    return session.scalars(select(LogSource).where(LogSource.content_hash == content_hash)).first()


def create_source(session: Session, source: LogSource, records: list[dict[str, Any]]) -> LogSource:
    """Insert the source and all its records in one transaction (all or nothing)."""
    session.add(source)
    session.flush()
    for start in range(0, len(records), INSERT_CHUNK):
        chunk = records[start:start + INSERT_CHUNK]
        session.execute(insert(LogRecord), [{**row, "source_id": source.id} for row in chunk])
    session.commit()
    return source


def list_sources(session: Session) -> list[LogSource]:
    return list(session.scalars(select(LogSource).order_by(LogSource.created_at.desc())))


def get_source(session: Session, source_id: str) -> LogSource | None:
    return session.get(LogSource, source_id)


def delete_source(session: Session, source: LogSource) -> None:
    session.delete(source)
    session.commit()


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def apply_filters(
    stmt, *, source_id: str | None, levels: list[str] | None, services: list[str] | None, q: str | None,
    start: datetime | None, end: datetime | None, min_status: int | None, request_id: str | None,
):
    if source_id:
        stmt = stmt.where(LogRecord.source_id == source_id)
    if levels:
        stmt = stmt.where(LogRecord.level.in_(levels))
    if services:
        stmt = stmt.where(LogRecord.service.in_(services))
    if q:
        like = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(or_(
            LogRecord.message.ilike(like, escape="\\"), LogRecord.request_id.ilike(like, escape="\\"),
            LogRecord.exception_type.ilike(like, escape="\\"), LogRecord.service.ilike(like, escape="\\"),
        ))
    if start:
        stmt = stmt.where(LogRecord.timestamp >= start)
    if end:
        stmt = stmt.where(LogRecord.timestamp <= end)
    if min_status:
        stmt = stmt.where(LogRecord.http_status >= min_status)
    if request_id:
        stmt = stmt.where(LogRecord.request_id == request_id)
    return stmt


def query_logs(
    session: Session, *, source_id: str | None, levels: list[str] | None = None, services: list[str] | None = None,
    q: str | None = None, start: datetime | None = None, end: datetime | None = None, min_status: int | None = None,
    request_id: str | None = None, sort: str = "timestamp", order: str = "asc", page: int = 1, page_size: int = 50,
) -> tuple[list[LogRecord], int]:
    filters = dict(source_id=source_id, levels=levels, services=services, q=q, start=start, end=end,
                   min_status=min_status, request_id=request_id)
    total = session.scalar(apply_filters(select(func.count()).select_from(LogRecord), **filters)) or 0
    column = SORTABLE.get(sort, LogRecord.timestamp)
    direction = column.desc() if order == "desc" else column.asc()
    # When sorting by time, records without a time go last. The id is the final tie-breaker, so paging is stable.
    ordering = [LogRecord.timestamp.is_(None), direction, LogRecord.id] if sort == "timestamp" else [direction, LogRecord.id]
    stmt = apply_filters(select(LogRecord), **filters).order_by(*ordering)
    rows = list(session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def get_record(session: Session, record_id: int) -> LogRecord | None:
    return session.get(LogRecord, record_id)


def get_context(session: Session, record: LogRecord, size: int) -> dict[str, list[LogRecord]]:
    """The records just before and after this one in the same file (by line number)."""
    base = select(LogRecord).where(LogRecord.source_id == record.source_id)
    before = list(session.scalars(base.where(LogRecord.line_no < record.line_no).order_by(LogRecord.line_no.desc()).limit(size)))
    after = list(session.scalars(base.where(LogRecord.line_no > record.line_no).order_by(LogRecord.line_no.asc()).limit(size)))
    return {"before": before[::-1], "after": after}


def get_records_by_ids(session: Session, ids: list[int]) -> list[LogRecord]:
    if not ids:
        return []
    return list(session.scalars(select(LogRecord).where(LogRecord.id.in_(ids)).order_by(LogRecord.timestamp, LogRecord.id)))


def filter_options(session: Session, source_id: str) -> dict[str, list[Any]]:
    services = session.scalars(
        select(LogRecord.service).where(LogRecord.source_id == source_id).distinct().order_by(LogRecord.service))
    levels = session.scalars(select(LogRecord.level).where(LogRecord.source_id == source_id).distinct())
    return {"services": list(services), "levels": sorted(set(levels), key=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].index)}
