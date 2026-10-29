"""Incident list, investigation view, status/notes and the evidence records."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import MAX_PAGE_SIZE, check_id, get_app_settings
from app.core.config import Settings
from app.ai.providers import make_provider
from app.services import knowledge_service, summary_service
from app.core.database import get_session
from app.core.errors import AppError, not_found
from app.ingestion.normalize import LEVELS
from app.models.tables import ErrorGroup, IncidentNote
from app.repositories import incidents as repo
from app.repositories import logs as log_repo

router = APIRouter(prefix="/incidents", tags=["incidents"])


class IncidentUpdate(BaseModel):
    status: str | None = None
    reviewed: bool | None = None


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("The note cannot be empty.")
        return value.strip()


def _get(session: Session, incident_id: str):
    incident = repo.get_incident(session, check_id(incident_id, "incident"))
    if incident is None:
        raise not_found("incident", incident_id)
    return incident


@router.get("")
def list_incidents(
    analysis_id: str | None = None,
    source_id: Annotated[str | None, Query(description="Uses the latest analysis of this source")] = None,
    severity: Annotated[list[str] | None, Query()] = None,
    status: Annotated[list[str] | None, Query()] = None,
    reviewed: bool | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    service: Annotated[str | None, Query(max_length=120)] = None,
    sort: Annotated[str, Query(pattern="^(severity|first_seen|error_count|record_count|number|status)$")] = "severity",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 25,
    session: Session = Depends(get_session),
):
    if analysis_id:
        check_id(analysis_id, "analysis")
    if source_id:
        check_id(source_id, "source")
    if severity and any(s not in repo.SEVERITIES for s in severity):
        raise AppError(422, "invalid_severity", f"Severity must be one of: {', '.join(repo.SEVERITIES)}.")
    if status and any(s not in repo.STATUSES for s in status):
        raise AppError(422, "invalid_status", f"Status must be one of: {', '.join(repo.STATUSES)}.")
    rows, total = repo.query_incidents(
        session, analysis_id=analysis_id, source_id=source_id, severities=severity, statuses=status, reviewed=reviewed,
        q=q, service=service, sort=sort, order=order, page=page, page_size=page_size)
    return {"items": [repo.incident_to_dict(i) for i in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/{incident_id}")
def get_incident(incident_id: str, session: Session = Depends(get_session)):
    incident = _get(session, incident_id)
    from app.models.tables import LogSource  # local import keeps the module header short

    groups = [session.get(ErrorGroup, gid) for gid in incident.group_ids]
    related = []
    for rel in incident.detection.get("related", []):
        other = repo.get_incident(session, rel.get("incident_id", ""))
        if other is not None:
            related.append({"id": other.id, "label": f"INC-{other.number}", "title": other.title,
                            "severity": other.severity, "shared_patterns": rel.get("shared_patterns", [])})
    analysis = repo.get_analysis(session, incident.analysis_id)
    source = session.get(LogSource, analysis.source_id) if analysis else None
    return {
        "incident": repo.incident_to_dict(incident),
        "explanation": incident.explanation,
        "detection": {k: v for k, v in incident.detection.items() if k != "related"},
        "timeline": incident.timeline,
        "groups": [repo.group_to_dict(g) for g in groups if g is not None],
        "representative_records": repo.representative_records(session, incident),
        "related_incidents": related,
        "notes": [repo.note_to_dict(n) for n in sorted(incident.notes, key=lambda n: n.created_at, reverse=True)],
        "source": log_repo.source_to_dict(source) if source else None,
        "labels": {  # what each kind of statement means, shown by the UI
            "observed": "Read directly from log records",
            "inferred": "Concluded from the records; not confirmed",
        },
    }


@router.get("/{incident_id}/records")
def get_incident_records(
    incident_id: str,
    level: Annotated[list[str] | None, Query()] = None,
    service: Annotated[str | None, Query(max_length=120)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    session: Session = Depends(get_session),
):
    incident = _get(session, incident_id)
    levels = [lv.upper() for lv in level] if level else None
    if levels and any(lv not in LEVELS for lv in levels):
        raise AppError(422, "invalid_level", f"Level must be one of: {', '.join(LEVELS)}.")
    rows, total = repo.incident_records(session, incident.id, levels=levels, service=service, q=q, page=page, page_size=page_size)
    return {"items": [log_repo.record_to_dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.patch("/{incident_id}")
def update_incident(incident_id: str, body: IncidentUpdate, session: Session = Depends(get_session)):
    incident = _get(session, incident_id)
    repo.update_incident(session, incident, status=body.status, reviewed=body.reviewed)
    return {"incident": repo.incident_to_dict(incident)}


@router.post("/{incident_id}/notes", status_code=201)
def add_note(incident_id: str, body: NoteCreate, session: Session = Depends(get_session)):
    incident = _get(session, incident_id)
    return {"note": repo.note_to_dict(repo.add_note(session, incident, body.body))}


@router.delete("/{incident_id}/notes/{note_id}", status_code=204)
def delete_note(incident_id: str, note_id: int, session: Session = Depends(get_session)):
    incident = _get(session, incident_id)
    note = session.get(IncidentNote, note_id)
    if note is None or note.incident_id != incident.id:
        raise not_found("note", note_id)
    repo.delete_note(session, note)


@router.get("/{incident_id}/runbooks")
def get_incident_runbooks(
    incident_id: str, request: Request, top_k: Annotated[int, Query(ge=1, le=10)] = 4,
    session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings),
):
    """Runbook sections that match this incident's error patterns. Each result has a citation; "no relevant source" is a normal answer."""
    incident = _get(session, incident_id)
    query = knowledge_service.incident_search_query(session, incident)
    result = request.app.state.kb.search(session, settings, query, top_k=top_k, min_relevance=settings.min_relevance)
    result["incident_id"] = incident.id
    return result


class SummarizeRequest(BaseModel):
    use_ai: bool = Field(default=False, description="Also ask the configured AI provider. Sends clipped, redacted evidence to it.")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    use_ai: bool = False


@router.post("/{incident_id}/summarize")
def summarize_incident(incident_id: str, request: Request, body: SummarizeRequest | None = None, session: Session = Depends(get_session),
                       settings: Settings = Depends(get_app_settings)):
    """Facts, retrieved runbook sections, hypotheses and read-only checks. Works without an AI provider; AI is opt-in per request."""
    incident = _get(session, incident_id)
    use_ai = bool(body and body.use_ai)
    provider = make_provider(settings, request.app.state.ai_http_client)
    summary = summary_service.build_summary(session, settings, request.app.state.kb, incident, use_ai=use_ai, provider=provider)
    summary_service.save_summary(session, incident, summary)
    return {"summary": summary.model_dump()}


@router.get("/{incident_id}/summary")
def get_incident_summary(incident_id: str, session: Session = Depends(get_session)):
    """The most recently generated summary, or null if none was generated yet."""
    incident = _get(session, incident_id)
    return {"summary": summary_service.latest_summary(session, incident.id)}


@router.post("/{incident_id}/ask")
def ask_about_incident(incident_id: str, body: AskRequest, request: Request, session: Session = Depends(get_session),
                       settings: Settings = Depends(get_app_settings)):
    incident = _get(session, incident_id)
    provider = make_provider(settings, request.app.state.ai_http_client)
    return summary_service.answer_question(session, settings, request.app.state.kb, incident, body.question.strip(), use_ai=body.use_ai, provider=provider)
