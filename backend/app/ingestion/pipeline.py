"""
The ingestion pipeline: bytes in, clean records and a data-quality report out.

    check file  ->  decode  ->  parse (CSV / JSON / text)  ->  clean each record  ->  report

Nothing is silently dropped. Every line that is skipped, rejected or repaired is counted in the report,
and a few examples of rejected lines are kept so the user can see what was wrong.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import ALLOWED_LOG_EXTENSIONS
from app.incident.templates import mask_message
from app.ingestion.extract import extract_fields
from app.ingestion.normalize import normalize_level, parse_timestamp, to_naive_utc
from app.ingestion.parsers import (
    MAX_MESSAGE_CHARS, FormatError, ParseOutcome, RawRecord, parse_csv, parse_json, parse_text,
)

MAX_REJECTED_EXAMPLES = 20


class IngestError(Exception):
    """The whole file is unusable. `code` is stable for the API, `message` is safe to show to a person."""

    def __init__(self, code: str, message: str, details: Any = None, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code


@dataclass
class IngestResult:
    filename: str
    format: str
    content_hash: str
    size_bytes: int
    records: list[dict[str, Any]]
    quality: dict[str, Any]


def safe_display_name(filename: str | None) -> str:
    """Only a plain file name is ever kept (no folders, no control characters). It is never used as a path."""
    name = Path((filename or "upload").replace("\\", "/")).name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return (name or "upload")[:120]


def _decode(data: bytes) -> tuple[str, str]:
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def _detect_format(extension: str, text: str) -> str:
    if extension == ".csv":
        return "csv"
    if extension in {".json", ".jsonl", ".ndjson"}:
        return "json"
    first = next((line for line in text.splitlines() if line.strip()), "")
    if first.lstrip().startswith("{"):  # a .log / .txt file that actually holds JSON Lines
        return "json"
    return "txt"


def _warning(code: str, message: str, count: int, severity: str = "warning") -> dict[str, Any]:
    """severity is "info" for notes that are normal for many files, "warning" for real data problems."""
    return {"code": code, "message": message, "count": count, "severity": severity}


def ingest_bytes(
    data: bytes,
    filename: str | None,
    *,
    max_bytes: int,
    max_records: int,
    column_mapping: dict[str, str] | None = None,
) -> IngestResult:
    display_name = safe_display_name(filename)
    extension = Path(display_name).suffix.lower()
    if extension not in ALLOWED_LOG_EXTENSIONS:
        raise IngestError(
            "unsupported_file_type",
            f"'{extension or 'no extension'}' files are not supported. Upload one of: {', '.join(ALLOWED_LOG_EXTENSIONS)}.",
        )
    if not data:
        raise IngestError("empty_file", "The file is empty.")
    if len(data) > max_bytes:
        raise IngestError("file_too_large", f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.", status_code=413)
    if b"\x00" in data[:8192]:
        raise IngestError("binary_file", "The file looks like a binary file, not a text log.")

    text, encoding = _decode(data)
    fmt = _detect_format(extension, text)
    try:
        outcome: ParseOutcome = (
            parse_csv(text, column_mapping) if fmt == "csv"
            else parse_json(text, column_mapping) if fmt == "json"
            else parse_text(text)
        )
    except FormatError as exc:
        raise IngestError(exc.code, exc.message, exc.details) from None

    if not outcome.records:
        raise IngestError(
            "no_records",
            "No log records could be read from the file. Check that each line starts with a timestamp and a level, "
            "or upload a CSV/JSON file with a 'message' column.",
            {"rejected": len(outcome.rejected), "examples": [r.__dict__ for r in outcome.rejected[:5]]},
        )
    if len(outcome.records) > max_records:
        raise IngestError(
            "too_many_records",
            f"The file has {len(outcome.records):,} records. The limit is {max_records:,}. Split the file or filter it first.",
            status_code=413,
        )

    records, counters = _clean_records(outcome.records)
    quality = _build_quality(outcome, records, counters, fmt, encoding)
    return IngestResult(
        filename=display_name,
        format=fmt,
        content_hash=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        records=records,
        quality=quality,
    )


def _clean_records(raw_records: list[RawRecord]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counters = {
        "missing_timestamp": 0, "unparseable_timestamp": 0, "naive_timestamp": 0, "level_inferred": 0,
        "unknown_level": 0, "duplicates": 0, "bad_status": 0, "bad_latency": 0, "no_service": 0,
    }
    cleaned: list[dict[str, Any]] = []
    seen_keys: set[tuple[Any, ...]] = set()

    for raw in raw_records:
        f = raw.fields
        message = str(f.get("message") or f.get("exception_type") or "")[:MAX_MESSAGE_CHARS]
        stack = f.get("stack_trace")

        # Fill gaps from the text itself, but never overwrite a value the file provided.
        found = extract_fields(f"{message}\n{(stack or '')[:1500]}")
        merged = {k: f.get(k) for k in (
            "host", "environment", "request_id", "trace_id", "route_id", "endpoint", "exception_type")}
        for key in merged:
            if merged[key] is None and key in found:
                merged[key] = found[key]
        extra = dict(raw.extra)
        if "packet_loss_pct" in found:
            extra["packet_loss_pct"] = found["packet_loss_pct"]

        # HTTP status and latency: a value from a column must be a sensible number.
        status = _to_int(f.get("http_status"))
        if f.get("http_status") is not None and not (status and 100 <= status <= 599):
            counters["bad_status"] += 1
            status = None
        if status is None:
            status = found.get("http_status")
        latency = _to_float(f.get("latency_ms"))
        if f.get("latency_ms") is not None:
            if latency is None or latency < 0:
                counters["bad_latency"] += 1
                latency = None
            elif raw.converted_from_seconds:
                latency *= 1000
        if latency is None:
            latency = found.get("latency_ms")

        # Timestamp
        timestamp = None
        if f.get("timestamp") is None:
            counters["missing_timestamp"] += 1
        else:
            parsed, assumed_utc = parse_timestamp(f["timestamp"])
            if parsed is None:
                counters["unparseable_timestamp"] += 1
            else:
                timestamp = to_naive_utc(parsed)
                counters["naive_timestamp"] += int(assumed_utc)

        # Severity: normalise what the file says; infer only when it says nothing.
        level = normalize_level(f.get("level"))
        if level is None:
            if f.get("level") is not None:
                counters["unknown_level"] += 1
            level = "ERROR" if (status and status >= 500) or merged["exception_type"] else "WARNING" if (status and status >= 400) else "INFO"
            extra["level_inferred"] = True
            counters["level_inferred"] += 1

        service = (f.get("service") or "").strip()[:120]
        if not service:
            service = "unknown"
            counters["no_service"] += 1

        if not merged["exception_type"] and stack:
            tail = extract_fields(stack.splitlines()[-1] if stack.splitlines() else "")
            merged["exception_type"] = tail.get("exception_type")

        # A repeated record is only a "duplicate" when it carries its own request or trace id.
        # Identical lines without an id may be a genuine burst of the same error, so they are kept.
        correlation = merged["request_id"] or merged["trace_id"]
        if correlation:
            key = (timestamp, level, service, message, correlation)
            if key in seen_keys:
                counters["duplicates"] += 1
                continue
            seen_keys.add(key)

        cleaned.append({
            "line_no": raw.line_no,
            "timestamp": timestamp,
            "level": level,
            "service": service,
            "host": _trim(merged["host"], 120),
            "environment": _trim(merged["environment"], 60),
            "request_id": _trim(merged["request_id"], 80),
            "trace_id": _trim(merged["trace_id"], 80),
            "route_id": _trim(merged["route_id"], 60),
            "endpoint": _trim(merged["endpoint"], 300),
            "http_status": status,
            "latency_ms": latency,
            "exception_type": _trim(merged["exception_type"], 200),
            "message": message,
            "normalized_message": mask_message(message),
            "stack_trace": stack,
            "raw_line": raw.raw,
            "extra": extra,
        })
    return cleaned, counters


def _build_quality(
    outcome: ParseOutcome, records: list[dict[str, Any]], c: dict[str, int], fmt: str, encoding: str
) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    if encoding != "utf-8":
        warnings.append(_warning("decoded_latin1", "The file is not valid UTF-8, so it was read as Latin-1. Some characters may look wrong.", 1))
    if outcome.rejected:
        warnings.append(_warning("rejected_lines", "Some lines could not be understood and were left out. Examples are listed below.", len(outcome.rejected)))
    if c["duplicates"]:
        warnings.append(_warning("duplicates_removed", "Exact duplicate records (same time, message and request id) were removed.", c["duplicates"]))
    if c["missing_timestamp"]:
        warnings.append(_warning("missing_timestamp", "Records with no timestamp were kept but cannot be placed on a timeline.", c["missing_timestamp"]))
    if c["unparseable_timestamp"]:
        warnings.append(_warning("unparseable_timestamp", "The timestamp could not be understood, so these records have no time.", c["unparseable_timestamp"]))
    if c["naive_timestamp"]:
        warnings.append(_warning("timestamps_assumed_utc", "These timestamps had no time zone, so UTC was assumed.", c["naive_timestamp"], "info"))
    if c["level_inferred"]:
        warnings.append(_warning("level_inferred", "These records had no usable severity. It was inferred from the status code or exception.", c["level_inferred"], "info"))
    if c["bad_status"]:
        warnings.append(_warning("invalid_status", "The HTTP status was not a valid code (100-599) and was ignored.", c["bad_status"]))
    if c["bad_latency"]:
        warnings.append(_warning("invalid_latency", "The latency was not a valid non-negative number and was ignored.", c["bad_latency"]))
    if outcome.truncated_messages:
        warnings.append(_warning("long_messages_truncated", f"Messages longer than {MAX_MESSAGE_CHARS} characters were cut.", outcome.truncated_messages))
    if c["no_service"]:
        warnings.append(_warning("no_service", "No service name was found, so these records are labelled 'unknown'.", c["no_service"]))

    n = len(records) or 1
    return {
        "format": fmt,
        "encoding": encoding,
        "total_lines": outcome.total_lines,
        "blank_lines": outcome.blank_lines,
        "parsed_records": len(outcome.records),
        "stored_records": len(records),
        "rejected_count": len(outcome.rejected),
        "duplicates_removed": c["duplicates"],
        "missing_timestamp": c["missing_timestamp"] + c["unparseable_timestamp"],
        "level_inferred": c["level_inferred"],
        "coverage": {  # share of stored records that have each field
            name: round(sum(1 for r in records if r.get(name) not in (None, "")) / n, 3)
            for name in ("timestamp", "service", "host", "request_id", "trace_id", "route_id", "http_status", "latency_ms", "exception_type")
        },
        "column_mapping": outcome.column_mapping,
        "detected_columns": outcome.detected_columns[:100],
        "warnings": warnings,
        "rejected_examples": [r.__dict__ for r in outcome.rejected[:MAX_REJECTED_EXAMPLES]],
    }


def _to_int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip().rstrip("msMS").strip())
        return number if number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _trim(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None
