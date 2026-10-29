"""
Database tables (SQLAlchemy).

How the data fits together:

    LogSource  --1:n-->  LogRecord          one uploaded file (or sample) and its parsed lines
    LogSource  --1:n-->  Analysis           one grouping/incident run over a source
    Analysis   --1:n-->  ErrorGroup         related errors found in that run
    Analysis   --1:n-->  Incident           bursts of related errors
    Incident   --n:m-->  LogRecord          the evidence (IncidentRecord)
    Incident   --1:n-->  IncidentNote       investigation notes written by a person
    RunbookDocument --1:n--> RunbookChunk   the searchable pieces of a runbook
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Timestamps are stored as naive UTC (SQLite has no time zones) and sent to the API with a 'Z'."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class LogSource(Base):
    """One ingested file (or generated sample) plus its data-quality report."""

    __tablename__ = "log_sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    original_filename: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16), default="upload")  # upload | sample
    format: Mapped[str] = mapped_column(String(16))  # csv | txt | json
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    quality: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    records: Mapped[list[LogRecord]] = relationship(back_populates="source", cascade="all, delete-orphan", passive_deletes=True)
    analyses: Mapped[list[Analysis]] = relationship(back_populates="source", cascade="all, delete-orphan", passive_deletes=True)


class LogRecord(Base):
    """One parsed log line. The original text is kept next to the normalised fields."""

    __tablename__ = "log_records"
    __table_args__ = (Index("ix_log_records_source_ts", "source_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("log_sources.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)  # line (TXT/JSONL) or row (CSV) number in the original file

    timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    level: Mapped[str] = mapped_column(String(10), index=True)  # DEBUG INFO WARNING ERROR CRITICAL
    service: Mapped[str] = mapped_column(String(120), index=True, default="unknown")
    host: Mapped[str | None] = mapped_column(String(120), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(60), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    route_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(300), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(200), nullable=True)

    message: Mapped[str] = mapped_column(Text)  # original message, never altered
    normalized_message: Mapped[str] = mapped_column(Text)  # variable values masked, used for grouping
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    source: Mapped[LogSource] = relationship(back_populates="records")


class Analysis(Base):
    """One grouping and incident-detection run over a source, with the settings that were used."""

    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("log_sources.id", ondelete="CASCADE"), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    params_hash: Mapped[str] = mapped_column(String(64), index=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    source: Mapped[LogSource] = relationship(back_populates="analyses")
    groups: Mapped[list[ErrorGroup]] = relationship(back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True)
    incidents: Mapped[list[Incident]] = relationship(back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True)


class ErrorGroup(Base):
    """Related errors. `method` says whether they are identical after masking or only similar."""

    __tablename__ = "error_groups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    template: Mapped[str] = mapped_column(Text)  # the masked message that represents the group
    services: Mapped[list[str]] = mapped_column(JSON, default=list)
    exception_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(16))  # exact | similarity
    explanation: Mapped[str] = mapped_column(Text)
    member_templates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    max_level: Mapped[str] = mapped_column(String(10), default="ERROR")
    sample_record_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    record_ids: Mapped[list[int]] = mapped_column(JSON, default=list)

    analysis: Mapped[Analysis] = relationship(back_populates="groups")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)  # 1, 2, 3 ... inside the analysis, used in the title
    title: Mapped[str] = mapped_column(String(300))
    severity: Mapped[str] = mapped_column(String(10))  # critical | high | medium | low
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | investigating | resolved | ignored
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    services: Mapped[list[str]] = mapped_column(JSON, default=list)
    group_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    top_patterns: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    detection: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # the rule values that created it
    explanation: Mapped[str] = mapped_column(Text, default="")
    related_incident_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    analysis: Mapped[Analysis] = relationship(back_populates="incidents")
    notes: Mapped[list[IncidentNote]] = relationship(back_populates="incident", cascade="all, delete-orphan", passive_deletes=True)
    summaries: Mapped[list[IncidentSummary]] = relationship(back_populates="incident", cascade="all, delete-orphan", passive_deletes=True)


class IncidentRecord(Base):
    """Links an incident to the log records that belong to it (its evidence)."""

    __tablename__ = "incident_records"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("log_records.id", ondelete="CASCADE"), primary_key=True, index=True)


class IncidentNote(Base):
    __tablename__ = "incident_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="notes")


class IncidentSummary(Base):
    """A saved AI (or deterministic) summary, so it is not regenerated on every page view."""

    __tablename__ = "incident_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))  # none | anthropic | openai | ...
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="summaries")


class ActivityLog(Base):
    """A short audit trail of what people did to incidents (status changes, reviews, notes, summaries)."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # status | reviewed | note | summary
    detail: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class RunbookDocument(Base):
    __tablename__ = "runbook_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16), default="upload")  # upload | sample
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    chunks: Mapped[list[RunbookChunk]] = relationship(back_populates="document", cascade="all, delete-orphan", passive_deletes=True)


class RunbookChunk(Base):
    __tablename__ = "runbook_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("runbook_documents.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(300))  # the section path, e.g. "Database timeouts > Diagnostic steps"
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped[RunbookDocument] = relationship(back_populates="chunks")


class IndexState(Base):
    """Remembers what the on-disk vector index was built from, so it is not rebuilt for nothing."""

    __tablename__ = "index_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    backend: Mapped[str] = mapped_column(String(60), default="")
    vector_store: Mapped[str] = mapped_column(String(20), default="")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    built_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
