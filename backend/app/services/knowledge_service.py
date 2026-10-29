"""Add, list and remove runbooks, and search them. Runbook text is untrusted: it is stored and shown, never run."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import ALLOWED_RUNBOOK_EXTENSIONS, Settings
from app.core.database import new_id
from app.core.errors import AppError
from app.ingestion.normalize import iso_z
from app.models.tables import ErrorGroup, Incident, IndexState, RunbookChunk, RunbookDocument
from app.rag.chunker import chunk_text
from app.rag.loader import RunbookError, load_runbook, title_from_text
from app.rag.retriever import KnowledgeIndex, query_from_incident
from app.repositories import incidents as incident_repo


def document_to_dict(doc: RunbookDocument, chunk_count: int | None = None) -> dict[str, Any]:
    return {"id": doc.id, "title": doc.title, "filename": doc.filename, "kind": doc.kind, "size_bytes": doc.size_bytes,
            "chunk_count": chunk_count if chunk_count is not None else len(doc.chunks), "created_at": iso_z(doc.created_at)}


def add_document(session: Session, settings: Settings, kb: KnowledgeIndex, data: bytes, filename: str | None,
                 *, kind: str = "upload") -> tuple[RunbookDocument, bool]:
    """Store a runbook and its chunks. The same content twice returns the existing document (created=False)."""
    try:
        name, text = load_runbook(data, filename, max_bytes=settings.max_runbook_bytes)
    except RunbookError as exc:
        raise AppError(exc.status_code, exc.code, exc.message) from None
    content_hash = hashlib.sha256(data).hexdigest()
    existing = session.scalar(select(RunbookDocument).where(RunbookDocument.content_hash == content_hash))
    if existing is not None:
        return existing, False
    chunks = chunk_text(text, size=settings.chunk_size_chars, overlap=settings.chunk_overlap_chars)
    if not chunks:
        raise AppError(422, "no_text", "No readable text was found in the file.")
    doc = RunbookDocument(id=new_id("doc"), title=title_from_text(text, name), filename=name, kind=kind,
                          content_hash=content_hash, size_bytes=len(data), text=text)
    doc.chunks = [RunbookChunk(ordinal=c.ordinal, heading=c.heading[:300], text=c.text, char_start=c.char_start, char_end=c.char_end)
                  for c in chunks]
    session.add(doc)
    session.commit()
    kb.invalidate()
    return doc, True


def load_sample_runbooks(session: Session, settings: Settings, kb: KnowledgeIndex) -> list[tuple[RunbookDocument, bool]]:
    """Load the bundled synthetic runbooks (safe to call again: files already loaded are skipped)."""
    folder: Path = settings.sample_runbook_dir
    files = sorted(p for p in folder.glob("*") if p.is_file() and p.suffix.lower() in ALLOWED_RUNBOOK_EXTENSIONS) if folder.is_dir() else []
    if not files:
        raise AppError(404, "no_sample_runbooks", "The sample runbook folder is empty or missing.")
    return [add_document(session, settings, kb, p.read_bytes(), p.name, kind="sample") for p in files]


def list_documents(session: Session) -> list[dict[str, Any]]:
    counts = dict(session.execute(select(RunbookChunk.document_id, func.count()).group_by(RunbookChunk.document_id)).all())
    docs = session.scalars(select(RunbookDocument).order_by(RunbookDocument.created_at, RunbookDocument.title))
    return [document_to_dict(d, counts.get(d.id, 0)) for d in docs]


def delete_document(session: Session, kb: KnowledgeIndex, doc: RunbookDocument) -> None:
    session.delete(doc)
    session.commit()
    kb.invalidate()


def status(session: Session, settings: Settings, kb: KnowledgeIndex) -> dict[str, Any]:
    kb.ensure(session, settings)
    state = session.get(IndexState, 1)
    return {"documents": session.scalar(select(func.count()).select_from(RunbookDocument)) or 0,
            "chunks": session.scalar(select(func.count()).select_from(RunbookChunk)) or 0,
            "built_at": iso_z(state.built_at) if state and state.built_at else None,
            "chunk_size_chars": settings.chunk_size_chars, "chunk_overlap_chars": settings.chunk_overlap_chars,
            **kb.describe(settings)}


def incident_search_query(session: Session, incident: Incident) -> str:
    """The text used to look up runbooks for an incident (built from what was observed; see query_from_incident)."""
    groups = [g for g in (session.get(ErrorGroup, gid) for gid in incident.group_ids) if g is not None]
    statuses = incident_repo.incident_http_statuses(session, incident.id)
    slow = any(e.get("kind") == "latency_threshold" for e in incident.timeline)
    return query_from_incident(
        [{"template": g.template, "exception_types": g.exception_types} for g in groups], statuses, slow) or incident.title
