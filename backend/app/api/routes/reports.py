"""Exports and the (read-only) settings view."""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.ai.providers import ai_configuration_problem
from app.api.deps import check_id, get_app_settings
from app.core.config import Settings
from app.core.database import get_session
from app.core.errors import AppError, not_found
from app.models.tables import LogSource
from app.repositories import incidents as repo
from app.repositories import logs as log_repo
from app.services import export_service as exp

router = APIRouter(tags=["reports"])
FORMAT = Annotated[str, Query(pattern="^(md|json|csv)$", description="md, json or csv")]
MEDIA = {"md": "text/markdown; charset=utf-8", "json": "application/json", "csv": "text/csv; charset=utf-8"}


def _download(content: str, media: str, filename: str) -> Response:
    return Response(content=content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"',
                                                                "X-Content-Type-Options": "nosniff"})


@router.get("/incidents/{incident_id}/export")
def export_incident(incident_id: str, request: Request, format: FORMAT = "md", session: Session = Depends(get_session),
                    settings: Settings = Depends(get_app_settings)):
    incident = repo.get_incident(session, check_id(incident_id, "incident"))
    if incident is None:
        raise not_found("incident", incident_id)
    data = exp.incident_export_data(session, settings, request.app.state.kb, incident)
    label = f"INC-{incident.number}"
    if format == "json":
        content = json.dumps(data, indent=2, ensure_ascii=False)
    elif format == "csv":
        content = exp.incident_records_csv(data)
    else:
        content = exp.incident_markdown(data)
    return _download(content, MEDIA[format], exp.safe_filename(label, incident.title, format))


@router.get("/reports/export")
def export_report(source_id: str | None = None, format: FORMAT = "md", session: Session = Depends(get_session)):
    """All incidents of the newest analysis of a source (the newest source when `source_id` is not given)."""
    sources = log_repo.list_sources(session)
    source = next((s for s in sources if s.id == check_id(source_id, "source")), None) if source_id else (sources[0] if sources else None)
    if source is None:
        raise not_found("source", source_id or "(none loaded)")
    analysis = repo.latest_analysis(session, source.id)
    if analysis is None:
        raise AppError(409, "analysis_needed", "Analyse this log source before exporting a report.")
    data = exp.report_data(session, analysis, source)
    content = json.dumps(data, indent=2, ensure_ascii=False) if format == "json" else exp.report_csv(data) if format == "csv" else exp.report_markdown(data)
    return _download(content, MEDIA[format], exp.safe_filename("incident-report", source.name.rsplit(".", 1)[0], format))


@router.get("/settings")
def get_settings_view(settings: Settings = Depends(get_app_settings)):
    """Non-secret configuration. The API key is never returned, only whether one is set."""
    problem = ai_configuration_problem(settings)
    return {
        "version": settings.app_version,
        "ai": {"provider": settings.ai_provider, "model": settings.ai_model, "key_set": bool(settings.ai_api_key),
               "ready": settings.ai_provider != "none" and problem is None, "problem": problem, "timeout_seconds": settings.ai_timeout_seconds,
               "max_evidence_records": settings.ai_max_evidence_records},
        "retrieval": {"embedding_backend": settings.embedding_backend, "embedding_model": settings.embedding_model,
                      "chunk_size_chars": settings.chunk_size_chars, "chunk_overlap_chars": settings.chunk_overlap_chars,
                      "min_relevance": settings.min_relevance},
        "detection_defaults": {"similarity_threshold": settings.similarity_threshold, "gap_minutes": settings.incident_gap_minutes,
                               "min_errors": settings.incident_min_errors},
        "limits": {"max_upload_mb": settings.max_upload_mb, "max_log_records": settings.max_log_records, "max_runbook_mb": settings.max_runbook_mb},
        "privacy": "Logs and runbooks stay on this machine. When AI help is requested for one incident and a provider is configured, "
                   "a clipped and redacted set of that incident's records and runbook excerpts is sent to that provider.",
        "safety": "This application never runs commands, restarts services or changes configuration. Suggestions are for a human to review.",
        "how_to_change": "Settings are read from environment variables (see .env.example). Restart the server after changing them.",
    }
