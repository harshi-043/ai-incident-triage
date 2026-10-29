"""Database reads and writes for analyses, error groups, incidents, notes and activity."""
from __future__ import annotations

from typing import Any

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.ingestion.normalize import iso_z
from app.models.tables import (
    ActivityLog, Analysis, ErrorGroup, Incident, IncidentNote, IncidentRecord, LogRecord, LogSource,
)
from app.repositories.logs import record_to_dict

STATUSES = ("open", "investigating", "resolved", "ignored")
SEVERITIES = ("critical", "high", "medium", "low")
SEVERITY_RANK = case(
    (Incident.severity == "critical", 0), (Incident.severity == "high", 1), (Incident.severity == "medium", 2), else_=3)


def analysis_to_dict(a: Analysis, source: LogSource | None = None) -> dict[str, Any]:
    data = {"id": a.id, "source_id": a.source_id, "params": a.params, "stats": a.stats, "created_at": iso_z(a.created_at)}
    if source is not None:
        data["source_name"] = source.name
    return data


def group_to_dict(g: ErrorGroup, *, detail: bool = False) -> dict[str, Any]:
    data = {
        "id": g.id, "analysis_id": g.analysis_id, "title": g.title, "template": g.template, "services": g.services,
        "exception_types": g.exception_types, "method": g.method, "explanation": g.explanation,
        "record_count": g.record_count, "first_seen": iso_z(g.first_seen), "last_seen": iso_z(g.last_seen),
        "max_level": g.max_level, "sample_record_ids": g.sample_record_ids,
    }
    if detail:
        data["member_templates"] = g.member_templates
    return data


def incident_to_dict(i: Incident, *, label: bool = True) -> dict[str, Any]:
    return {
        "id": i.id, "analysis_id": i.analysis_id, "number": i.number, "label": f"INC-{i.number}" if label else None,
        "title": i.title, "severity": i.severity, "status": i.status, "reviewed": i.reviewed,
        "first_seen": iso_z(i.first_seen), "last_seen": iso_z(i.last_seen), "record_count": i.record_count,
        "error_count": i.error_count, "services": i.services, "top_patterns": i.top_patterns,
        "updated_at": iso_z(i.updated_at),
    }


def note_to_dict(n: IncidentNote) -> dict[str, Any]:
    return {"id": n.id, "incident_id": n.incident_id, "body": n.body, "created_at": iso_z(n.created_at)}


# ---- analyses --------------------------------------------------------------------------------
def list_analyses(session: Session, source_id: str | None = None) -> list[tuple[Analysis, LogSource]]:
    stmt = select(Analysis, LogSource).join(LogSource, LogSource.id == Analysis.source_id).order_by(Analysis.created_at.desc())
    if source_id:
        stmt = stmt.where(Analysis.source_id == source_id)
    return [(a, s) for a, s in session.execute(stmt)]


def latest_analysis(session: Session, source_id: str) -> Analysis | None:
    return session.scalars(select(Analysis).where(Analysis.source_id == source_id).order_by(Analysis.created_at.desc())).first()


def get_analysis(session: Session, analysis_id: str) -> Analysis | None:
    return session.get(Analysis, analysis_id)


def list_groups(session: Session, analysis_id: str, *, q: str | None, min_count: int, level: str | None,
                page: int, page_size: int) -> tuple[list[ErrorGroup], int]:
    stmt = select(ErrorGroup).where(ErrorGroup.analysis_id == analysis_id, ErrorGroup.record_count >= min_count)
    if q:
        like = f"%{q.strip().replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(ErrorGroup.title.ilike(like), cast(ErrorGroup.services, String).ilike(like)))
    if level:
        stmt = stmt.where(ErrorGroup.max_level == level)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(stmt.order_by(ErrorGroup.record_count.desc(), ErrorGroup.title).offset((page - 1) * page_size).limit(page_size))
    return list(rows), total


# ---- incidents -------------------------------------------------------------------------------
def query_incidents(
    session: Session, *, analysis_id: str | None, source_id: str | None, severities: list[str] | None,
    statuses: list[str] | None, reviewed: bool | None, q: str | None, service: str | None,
    sort: str, order: str, page: int, page_size: int,
) -> tuple[list[Incident], int]:
    stmt = select(Incident)
    if analysis_id:
        stmt = stmt.where(Incident.analysis_id == analysis_id)
    elif source_id:
        latest = latest_analysis(session, source_id)
        if latest is None:
            return [], 0
        stmt = stmt.where(Incident.analysis_id == latest.id)
    if severities:
        stmt = stmt.where(Incident.severity.in_(severities))
    if statuses:
        stmt = stmt.where(Incident.status.in_(statuses))
    if reviewed is not None:
        stmt = stmt.where(Incident.reviewed == reviewed)
    if service:
        stmt = stmt.where(cast(Incident.services, String).like(f'%"{service.replace(chr(34), "")}"%'))
    if q:
        like = f"%{q.strip().replace('%', '').replace('_', '')}%"
        label = "INC-" + cast(Incident.number, String)  # lets "inc-3" find incident 3
        stmt = stmt.where(or_(Incident.title.ilike(like), Incident.explanation.ilike(like),
                              cast(Incident.services, String).ilike(like), label.ilike(like)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    columns = {"severity": SEVERITY_RANK, "first_seen": Incident.first_seen, "error_count": Incident.error_count,
               "number": Incident.number, "status": Incident.status, "record_count": Incident.record_count}
    column = columns.get(sort, SEVERITY_RANK)
    direction = column.desc() if order == "desc" else column.asc()
    rows = session.scalars(stmt.order_by(direction, Incident.first_seen, Incident.number).offset((page - 1) * page_size).limit(page_size))
    return list(rows), total


def get_incident(session: Session, incident_id: str) -> Incident | None:
    return session.get(Incident, incident_id)


def incident_records(session: Session, incident_id: str, *, levels: list[str] | None, service: str | None,
                     q: str | None, page: int, page_size: int) -> tuple[list[LogRecord], int]:
    stmt = select(LogRecord).join(IncidentRecord, IncidentRecord.record_id == LogRecord.id).where(IncidentRecord.incident_id == incident_id)
    if levels:
        stmt = stmt.where(LogRecord.level.in_(levels))
    if service:
        stmt = stmt.where(LogRecord.service == service)
    if q:
        like = f"%{q.strip().replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(LogRecord.message.ilike(like), LogRecord.request_id.ilike(like)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(stmt.order_by(LogRecord.timestamp.is_(None), LogRecord.timestamp, LogRecord.id)
                           .offset((page - 1) * page_size).limit(page_size))
    return list(rows), total


def incident_record_ids(session: Session, incident_id: str) -> set[int]:
    return set(session.scalars(select(IncidentRecord.record_id).where(IncidentRecord.incident_id == incident_id)))


def incident_http_statuses(session: Session, incident_id: str) -> set[int]:
    """The HTTP status codes seen on this incident's error-level records."""
    rows = session.scalars(
        select(LogRecord.http_status).join(IncidentRecord, IncidentRecord.record_id == LogRecord.id)
        .where(IncidentRecord.incident_id == incident_id, LogRecord.http_status.is_not(None),
               LogRecord.level.in_(("ERROR", "CRITICAL"))).distinct())
    return {int(s) for s in rows}


def representative_records(session: Session, incident: Incident, per_pattern: int = 2) -> list[dict[str, Any]]:
    """For each top pattern: its first records that belong to this incident."""
    out: list[dict[str, Any]] = []
    ids = incident_record_ids(session, incident.id)
    for pattern in incident.top_patterns[:4]:
        group = session.get(ErrorGroup, pattern.get("group_id"))
        if group is None:
            continue
        wanted = [rid for rid in group.record_ids if rid in ids][:per_pattern]
        for rec in session.scalars(select(LogRecord).where(LogRecord.id.in_(wanted)).order_by(LogRecord.timestamp, LogRecord.id)):
            out.append({"pattern_title": pattern["title"], "group_id": group.id, "record": record_to_dict(rec)})
    return out


# ---- changes ---------------------------------------------------------------------------------
def add_activity(session: Session, incident_id: str, kind: str, detail: str) -> None:
    session.add(ActivityLog(incident_id=incident_id, kind=kind, detail=detail[:300]))


def update_incident(session: Session, incident: Incident, *, status: str | None, reviewed: bool | None) -> None:
    if status is not None and status not in STATUSES:
        raise AppError(422, "invalid_status", f"Status must be one of: {', '.join(STATUSES)}.")
    if status is not None and status != incident.status:
        add_activity(session, incident.id, "status", f"Status changed from {incident.status} to {status}")
        incident.status = status
    if reviewed is not None and reviewed != incident.reviewed:
        add_activity(session, incident.id, "reviewed", "Marked as reviewed" if reviewed else "Review mark removed")
        incident.reviewed = reviewed
    session.commit()


def add_note(session: Session, incident: Incident, body: str) -> IncidentNote:
    note = IncidentNote(incident_id=incident.id, body=body)
    session.add(note)
    add_activity(session, incident.id, "note", "Investigation note added")
    session.commit()
    return note


def delete_note(session: Session, note: IncidentNote) -> None:
    add_activity(session, note.incident_id, "note", "Investigation note deleted")
    session.delete(note)
    session.commit()


def recent_activity(session: Session, source_id: str | None, limit: int = 8) -> list[dict[str, Any]]:
    stmt = (select(ActivityLog, Incident).join(Incident, Incident.id == ActivityLog.incident_id)
            .join(Analysis, Analysis.id == Incident.analysis_id).order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(limit))
    if source_id:
        stmt = stmt.where(Analysis.source_id == source_id)
    return [{"incident_id": i.id, "label": f"INC-{i.number}", "title": i.title, "kind": a.kind, "detail": a.detail,
             "created_at": iso_z(a.created_at)} for a, i in session.execute(stmt)]
