"""Run grouping and incident detection over a log source and save the result."""
from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import asdict

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import new_id
from app.core.errors import AppError, not_found
from app.incident.detection import detect_incidents
from app.incident.grouping import build_groups
from app.incident.types import DetectionParams, Group, IncidentDraft, Rec
from app.ingestion.normalize import iso_z
from app.models.tables import Analysis, ErrorGroup, Incident, IncidentRecord, LogRecord, LogSource

MAX_STORED_GROUP_RECORD_IDS = 5000


def load_recs(session: Session, source_id: str) -> list[Rec]:
    """Read only the columns the pipeline needs (much lighter than loading whole ORM objects)."""
    rows = session.execute(
        select(LogRecord.id, LogRecord.line_no, LogRecord.timestamp, LogRecord.level, LogRecord.service,
               LogRecord.exception_type, LogRecord.normalized_message, LogRecord.message, LogRecord.http_status,
               LogRecord.latency_ms, LogRecord.request_id)
        .where(LogRecord.source_id == source_id).order_by(LogRecord.line_no))
    return [Rec(id=r[0], line_no=r[1], ts=r[2], level=r[3], service=r[4], exception_type=r[5], template=r[6],
                message=r[7], http_status=r[8], latency_ms=r[9], request_id=r[10]) for r in rows]


def params_hash(params: DetectionParams) -> str:
    return hashlib.sha256(json.dumps(asdict(params), sort_keys=True).encode()).hexdigest()


def _event_dict(e) -> dict:
    return {"time": iso_z(e.time), "kind": e.kind, "title": e.title, "detail": e.detail,
            "origin": e.origin, "evidence_ids": e.evidence_ids}


def _sample_ids(group: Group) -> list[int]:
    """First, middle and last record of the group (by time), so a reader sees how it evolved."""
    r = group.records
    picks = [r[0], r[len(r) // 2], r[-1]] if len(r) >= 3 else r
    return list(dict.fromkeys(x.id for x in picks))


def run_analysis(
    session: Session, settings: Settings, source_id: str, params: DetectionParams, *, force_new: bool = False,
) -> tuple[Analysis, bool]:
    """Returns (analysis, reused). The same source with the same settings is analysed only once unless `force_new`."""
    source = session.get(LogSource, source_id)
    if source is None:
        raise not_found("source", source_id)
    digest = params_hash(params)
    if not force_new:
        existing = session.scalars(select(Analysis).where(Analysis.source_id == source_id, Analysis.params_hash == digest)
                                   .order_by(Analysis.created_at.desc())).first()
        if existing is not None:
            return existing, True

    started = time.perf_counter()
    records = load_recs(session, source_id)
    if not records:
        raise AppError(422, "no_records", "This source has no log records to analyse.")

    groups = build_groups(records, params)
    drafts, isolated = detect_incidents(records, groups, params)

    analysis = Analysis(id=new_id("an"), source_id=source_id, params=asdict(params), params_hash=digest)
    session.add(analysis)
    session.flush()

    # Groups
    group_ids: dict[str, str] = {}
    for g in groups:
        g.id = new_id("grp")
        group_ids[g.key] = g.id
        session.add(ErrorGroup(
            id=g.id, analysis_id=analysis.id, title=g.title[:300], template=g.template, services=g.services,
            exception_types=g.exception_types, method=g.method, explanation=g.explanation,
            member_templates=g.member_templates[:20], record_count=g.count, first_seen=g.first_seen, last_seen=g.last_seen,
            max_level=g.max_level, sample_record_ids=_sample_ids(g),
            record_ids=[r.id for r in g.records[:MAX_STORED_GROUP_RECORD_IDS]]))

    # Incidents
    incident_ids: dict[int, str] = {}
    for d in drafts:
        incident_ids[d.number] = new_id("inc")
    for d in drafts:
        session.add(_incident_row(analysis.id, d, incident_ids, group_ids))
    session.flush()
    link_rows = [{"incident_id": incident_ids[d.number], "record_id": r.id} for d in drafts for r in d.records]
    for start in range(0, len(link_rows), 5000):
        session.execute(insert(IncidentRecord), link_rows[start:start + 5000])

    analysis.stats = _stats(records, groups, drafts, isolated, time.perf_counter() - started)
    session.commit()
    return analysis, False


def _incident_row(analysis_id: str, d: IncidentDraft, incident_ids: dict[int, str], group_ids: dict[str, str]) -> Incident:
    detection = dict(d.detection)
    for rel in detection.get("related", []):
        rel["incident_id"] = incident_ids[rel["number"]]
    patterns = [{**p, "group_id": group_ids[p["group_key"]]} for p in d.top_patterns]
    return Incident(
        id=incident_ids[d.number], analysis_id=analysis_id, number=d.number, title=d.title, severity=d.severity,
        first_seen=d.first_seen, last_seen=d.last_seen, record_count=len(d.records), error_count=d.error_count,
        services=d.services, group_ids=[group_ids[g.key] for g in d.groups], top_patterns=patterns,
        timeline=[_event_dict(e) for e in d.timeline], detection=detection, explanation=d.explanation,
        related_incident_ids=[incident_ids[n] for n in d.related_numbers])


def _stats(records: list[Rec], groups: list[Group], drafts: list[IncidentDraft], isolated: list[Group], seconds: float) -> dict:
    times = [r.ts for r in records if r.ts]
    levels = Counter(r.level for r in records)
    return {
        "total_records": len(records),
        "records_without_timestamp": sum(1 for r in records if r.ts is None),
        "level_counts": dict(levels),
        "problem_records": sum(1 for r in records if r.is_problem),
        "error_records": sum(1 for r in records if r.is_error),
        "group_count": len(groups),
        "similarity_groups": sum(1 for g in groups if g.method == "similarity"),
        "merged_patterns": sum(len(g.member_templates) for g in groups if g.method == "similarity"),
        "incident_count": len(drafts),
        "severity_counts": dict(Counter(d.severity for d in drafts)),
        "isolated_error_groups": [{"title": g.title, "count": g.error_count} for g in isolated[:10]],
        "isolated_error_group_count": len(isolated),
        "time_range": {"start": iso_z(min(times)) if times else None, "end": iso_z(max(times)) if times else None},
        "duration_seconds": round(seconds, 2),
    }
