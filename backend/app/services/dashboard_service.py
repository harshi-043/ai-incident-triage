"""Numbers for the dashboard. Everything is computed from the stored records and analyses (nothing is hard-coded)."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.normalize import iso_z
from app.models.tables import Analysis, ErrorGroup, Incident, LogRecord, LogSource
from app.repositories import incidents as inc_repo
from app.repositories import logs as log_repo

BUCKET_CHOICES = (60, 300, 900, 3600, 6 * 3600, 86400)  # seconds
TARGET_BUCKETS = 120


def _bucket_seconds(span_seconds: float) -> int:
    for size in BUCKET_CHOICES:
        if span_seconds / size <= TARGET_BUCKETS:
            return size
    return BUCKET_CHOICES[-1]


def dashboard_summary(session: Session, source_id: str | None) -> dict[str, Any]:
    sources = log_repo.list_sources(session)
    if not sources:
        return {"has_data": False, "sources": [], "reason": "No log data has been loaded yet."}
    source = next((s for s in sources if s.id == source_id), None) if source_id else sources[0]
    if source is None:
        return {"has_data": False, "sources": [log_repo.source_to_dict(s) for s in sources], "reason": "That source does not exist."}

    level_counts = dict(session.execute(
        select(LogRecord.level, func.count()).where(LogRecord.source_id == source.id).group_by(LogRecord.level)).all())
    total = sum(level_counts.values())
    errors = level_counts.get("ERROR", 0) + level_counts.get("CRITICAL", 0)

    # Trend over time: error-level, warning and all records per bucket.
    rows = session.execute(select(LogRecord.timestamp, LogRecord.level).where(
        LogRecord.source_id == source.id, LogRecord.timestamp.is_not(None))).all()
    trend: list[dict[str, Any]] = []
    if rows:
        start = min(r[0] for r in rows)
        end = max(r[0] for r in rows)
        size = _bucket_seconds((end - start).total_seconds())
        origin = start.replace(second=0, microsecond=0)
        if size >= 3600:
            origin = origin.replace(minute=0)
        buckets: dict[int, Counter] = {}
        for ts, level in rows:
            index = int((ts - origin).total_seconds() // size)
            buckets.setdefault(index, Counter())[level] += 1
        for index in range(0, max(buckets) + 1):
            c = buckets.get(index, Counter())
            trend.append({"time": iso_z(origin + timedelta(seconds=index * size)), "errors": c["ERROR"] + c["CRITICAL"],
                          "warnings": c["WARNING"], "total": sum(c.values())})
    else:
        size = 0

    top_services = session.execute(
        select(LogRecord.service, func.count().label("n")).where(
            LogRecord.source_id == source.id, LogRecord.level.in_(("ERROR", "CRITICAL")))
        .group_by(LogRecord.service).order_by(func.count().desc(), LogRecord.service).limit(8)).all()

    analysis = inc_repo.latest_analysis(session, source.id)
    result: dict[str, Any] = {
        "has_data": True,
        "source": log_repo.source_to_dict(source),
        "sources": [log_repo.source_to_dict(s) for s in sources],
        "totals": {"records": total, "errors": errors, "warnings": level_counts.get("WARNING", 0),
                   "info": level_counts.get("INFO", 0) + level_counts.get("DEBUG", 0)},
        "severity_distribution": [{"level": lv, "count": level_counts.get(lv, 0)} for lv in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")],
        "trend": {"bucket_seconds": size, "points": trend},
        "top_services": [{"service": s, "errors": n} for s, n in top_services],
        "analysis": None, "analysis_needed": analysis is None,
        "incidents": {"total": 0, "critical_or_high": 0, "by_severity": {}, "by_status": {}, "recent": []},
        "top_errors": [], "recent_activity": inc_repo.recent_activity(session, source.id),
    }
    if analysis is not None:
        incidents = list(session.scalars(select(Incident).where(Incident.analysis_id == analysis.id)))
        by_severity = Counter(i.severity for i in incidents)
        top_groups = session.scalars(select(ErrorGroup).where(ErrorGroup.analysis_id == analysis.id)
                                     .order_by(ErrorGroup.record_count.desc()).limit(8))
        result["analysis"] = inc_repo.analysis_to_dict(analysis)
        result["incidents"] = {
            "total": len(incidents),
            "critical_or_high": by_severity["critical"] + by_severity["high"],
            "by_severity": dict(by_severity),
            "by_status": dict(Counter(i.status for i in incidents)),
            "recent": [inc_repo.incident_to_dict(i) for i in sorted(incidents, key=lambda i: i.first_seen or i.created_at, reverse=True)[:5]],
        }
        result["top_errors"] = [inc_repo.group_to_dict(g) for g in top_groups]
    return result
