"""Upload, sample loading and deletion of log sources."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import new_id
from app.core.errors import AppError
from app.ingestion.pipeline import IngestError, ingest_bytes
from app.models.tables import LogSource
from app.repositories import logs as repo
from app.utils.sample_logs import generate

SAMPLES = {
    "application": {
        "title": "Application logs (synthetic web shop)",
        "description": "8 hours of services such as api-gateway, orders-service and payments-service. Five injected incidents.",
        "default_file": "application.log",
        "files": ["application.log", "application.csv", "application.jsonl"],
    },
    "routing": {
        "title": "Routing logs (synthetic)",
        "description": "4 hours of routing-engine, link-monitor and bgp-agent logs. Two injected incidents. CSV with non-standard column names.",
        "default_file": "routing.csv",
        "files": ["routing.csv"],
    },
}


def parse_column_mapping(raw: str | None) -> dict[str, str] | None:
    if not raw or not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise AppError(422, "invalid_column_mapping", "The column mapping must be valid JSON, for example {\"message\": \"msg\"}.") from None
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise AppError(422, "invalid_column_mapping", "The column mapping must be an object of text values.")
    return value


def ingest_upload(
    session: Session, settings: Settings, data: bytes, filename: str | None, *,
    kind: str = "upload", column_mapping: dict[str, str] | None = None, force: bool = False,
) -> tuple[LogSource, dict[str, Any], bool]:
    """
    Parse, validate and store a log file. Returns (source, quality_report, created).

    Uploading the same bytes twice returns the existing source (`created` is False) instead of storing the
    records again, unless `force` is set.
    """
    try:
        result = ingest_bytes(
            data, filename, max_bytes=settings.max_upload_bytes, max_records=settings.max_log_records,
            column_mapping=column_mapping,
        )
    except IngestError as exc:
        raise AppError(exc.status_code, exc.code, exc.message, exc.details) from None

    existing = repo.find_source_by_hash(session, result.content_hash)
    if existing is not None and not force:
        return existing, existing.quality, False

    source = LogSource(
        id=new_id("src"), name=result.filename, original_filename=result.filename, kind=kind, format=result.format,
        content_hash=result.content_hash, size_bytes=result.size_bytes, record_count=len(result.records),
        quality=result.quality,
    )
    repo.create_source(session, source, result.records)
    return source, result.quality, True


def load_sample(
    session: Session, settings: Settings, name: str, filename: str | None = None, *, force: bool = False,
) -> tuple[LogSource, dict[str, Any], bool]:
    info = SAMPLES.get(name)
    if info is None:
        raise AppError(422, "unknown_sample", f"Unknown sample '{name}'. Choose one of: {', '.join(SAMPLES)}.")
    chosen = filename or info["default_file"]
    if chosen not in info["files"]:
        raise AppError(422, "unknown_sample_file", f"Sample '{name}' has no file '{chosen}'. Choose one of: {', '.join(info['files'])}.")
    dataset = generate(name)
    return ingest_upload(session, settings, dataset.files[chosen].encode("utf-8"), chosen, kind="sample", force=force)
