"""
Parsers for the three supported log formats: CSV, JSON / JSON Lines and plain text.

A parser only SPLITS the file into raw records (field name -> text) and counts what it could not read.
Cleaning (timestamps, levels, extracting ids from messages) happens afterwards in `pipeline.py`.

Uploaded text is treated purely as data: it is read with the standard `csv` and `json` modules and with
regular expressions. It is never executed or evaluated.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.ingestion.normalize import normalize_level

# The fields a log record can have, in the order the UI shows them.
FIELDS = (
    "timestamp", "level", "service", "host", "environment", "request_id", "trace_id", "route_id",
    "endpoint", "http_status", "latency_ms", "exception_type", "message", "stack_trace",
)

# Column names (lower-case, letters and digits only) that are recognised automatically.
ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "ts", "datetime", "date", "asctime", "eventtime", "loggedat", "createdat"),
    "level": ("level", "severity", "loglevel", "lvl", "levelname", "priority"),
    "service": ("service", "servicename", "component", "app", "application", "logger", "module"),
    "host": ("host", "hostname", "node", "server", "instance", "pod"),
    "environment": ("environment", "env", "stage"),
    "request_id": ("requestid", "reqid", "correlationid", "xrequestid"),
    "trace_id": ("traceid",),
    "route_id": ("routeid", "route"),
    "endpoint": ("endpoint", "path", "url", "uri"),
    "http_status": ("httpstatus", "statuscode", "status", "responsecode"),
    "latency_ms": ("latencyms", "latency", "durationms", "duration", "responsetime", "elapsedms", "elapsed",
                   "latencyseconds", "latencys", "durationseconds", "durations", "elapsedseconds"),
    "exception_type": ("exceptiontype", "exception", "errortype", "errorclass", "errorname", "exceptionclass"),
    "message": ("message", "msg", "text", "log", "logmessage", "errormessage", "description", "event", "detail"),
    "stack_trace": ("stacktrace", "stack", "traceback", "errorstack", "exceptiontrace"),
}
# A latency column whose name says "seconds" is converted to milliseconds.
SECONDS_COLUMNS = {"latencyseconds", "latencys", "durationseconds", "durations", "elapsedseconds"}

MISSING_TEXT = {"", "null", "none", "nan", "n/a", "na", "-", "undefined"}
MAX_MESSAGE_CHARS = 5000
MAX_STACK_CHARS = 6000
MAX_RAW_CHARS = 2000
MAX_EXTRA_COLUMNS = 20


class FormatError(Exception):
    """The file is not in a readable shape (for example, a CSV with no message column)."""

    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass
class RawRecord:
    line_no: int
    fields: dict[str, Any]
    raw: str
    extra: dict[str, Any] = field(default_factory=dict)
    converted_from_seconds: bool = False


@dataclass
class Rejection:
    line_no: int
    reason: str
    snippet: str


@dataclass
class ParseOutcome:
    records: list[RawRecord]
    total_lines: int
    blank_lines: int
    rejected: list[Rejection]
    detected_columns: list[str]
    column_mapping: dict[str, str]
    truncated_messages: int = 0


def _key(name: str) -> str:
    """'Request-ID' -> 'requestid' so that spelling and case differences do not matter."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return None if stripped.lower() in MISSING_TEXT else stripped
    return value


def _snippet(text: str) -> str:
    return text.strip().replace("\n", " ")[:80]


def resolve_columns(headers: list[str], override: dict[str, str] | None = None) -> dict[str, str]:
    """
    Decide which file column feeds which log field.

    `override` maps a field name to a column name chosen by the user and wins over automatic detection.
    Returns {field: column_name_as_written_in_the_file}.
    """
    by_key: dict[str, str] = {}
    for header in headers:
        by_key.setdefault(_key(header), header)

    mapping: dict[str, str] = {}
    used: set[str] = set()

    for fld, column in (override or {}).items():
        if fld not in FIELDS:
            raise FormatError("invalid_column_mapping", f"'{fld}' is not a log field. Choose one of: {', '.join(FIELDS)}.")
        match = by_key.get(_key(column))
        if match is None:
            raise FormatError("invalid_column_mapping", f"The file has no column named '{column}'.", {"columns": headers[:50]})
        mapping[fld] = match
        used.add(match)

    for fld, names in ALIASES.items():
        if fld in mapping:
            continue
        for alias in names:
            candidate = by_key.get(alias)
            if candidate is not None and candidate not in used:
                mapping[fld] = candidate
                used.add(candidate)
                break
    return mapping


def _row_to_record(
    line_no: int, row: dict[str, Any], mapping: dict[str, str], raw: str, headers: list[str]
) -> RawRecord:
    fields: dict[str, Any] = {}
    seconds = False
    for fld, column in mapping.items():
        fields[fld] = _clean(row.get(column))
        if fld == "latency_ms" and _key(column) in SECONDS_COLUMNS:
            seconds = True
    mapped_columns = set(mapping.values())
    extra = {}
    for column in headers:
        if column in mapped_columns or len(extra) >= MAX_EXTRA_COLUMNS:
            continue
        value = _clean(row.get(column))
        if value is not None:
            extra[str(column)[:60]] = value if not isinstance(value, str) else value[:500]
    return RawRecord(line_no=line_no, fields=fields, raw=raw[:MAX_RAW_CHARS], extra=extra, converted_from_seconds=seconds)


# ---------------------------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------------------------
def parse_csv(text: str, column_mapping: dict[str, str] | None = None) -> ParseOutcome:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    csv.field_size_limit(1_000_000)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)

    try:
        headers = [h.strip() for h in next(reader)]
    except StopIteration:
        raise FormatError("empty_file", "The CSV file has no header row.") from None
    except csv.Error as exc:
        raise FormatError("malformed_csv", f"The CSV file could not be read: {exc}") from None

    mapping = resolve_columns(headers, column_mapping)
    if "message" not in mapping and "exception_type" not in mapping:
        raise FormatError(
            "missing_required_columns",
            "No message column was found. Add a column called 'message' (or map one of your columns to it).",
            {"columns": headers[:50], "recognised": mapping},
        )

    records: list[RawRecord] = []
    rejected: list[Rejection] = []
    blank = 0
    truncated = 0
    index_of = {name: i for i, name in enumerate(headers)}
    while True:
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            rejected.append(Rejection(reader.line_num, f"unreadable CSV row ({exc})", ""))
            continue
        line_no = reader.line_num
        if not row or all(not cell.strip() for cell in row):
            blank += 1
            continue
        if len(row) > len(headers):
            rejected.append(Rejection(line_no, f"row has {len(row)} fields but the header has {len(headers)}", _snippet(",".join(row))))
            continue
        padded = row + [""] * (len(headers) - len(row))
        values = {name: padded[index_of[name]] for name in headers}
        record = _row_to_record(line_no, values, mapping, delimiter.join(row), headers)
        message = record.fields.get("message") or record.fields.get("exception_type")
        if not message:
            rejected.append(Rejection(line_no, "the message is empty", _snippet(delimiter.join(row))))
            continue
        if len(str(message)) > MAX_MESSAGE_CHARS:
            truncated += 1
        records.append(record)

    return ParseOutcome(records, reader.line_num, blank, rejected, headers, mapping, truncated)


# ---------------------------------------------------------------------------------------------
# JSON and JSON Lines
# ---------------------------------------------------------------------------------------------
def _flatten(obj: dict[str, Any], prefix: str = "", depth: int = 0) -> dict[str, Any]:
    """{'error': {'type': 'X'}} -> {'error.type': 'X'} (two levels deep at most)."""
    flat: dict[str, Any] = {}
    for key, value in obj.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict) and depth < 2:
            flat.update(_flatten(value, f"{name}.", depth + 1))
        elif isinstance(value, (list, dict)):
            flat[name] = json.dumps(value, default=str)[:1000]
        else:
            flat[name] = value
    return flat


def parse_json(text: str, column_mapping: dict[str, str] | None = None) -> ParseOutcome:
    stripped = text.lstrip()
    items: list[tuple[int, Any, str]] = []  # (line number, parsed value, raw text)
    rejected: list[Rejection] = []
    blank = 0
    total = 0

    if stripped.startswith("["):  # a single JSON array of objects
        try:
            data = json.loads(stripped)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise FormatError("malformed_json", f"The JSON file could not be read: {str(exc)[:120]}") from None
        for number, element in enumerate(data, start=1):
            items.append((number, element, json.dumps(element, default=str)[:MAX_RAW_CHARS]))
        total = len(data)
    else:  # one JSON object per line
        for number, line in enumerate(text.splitlines(), start=1):
            total = number
            if not line.strip():
                blank += 1
                continue
            try:
                items.append((number, json.loads(line), line))
            except (json.JSONDecodeError, RecursionError):
                rejected.append(Rejection(number, "not valid JSON", _snippet(line)))

    flat_rows: list[tuple[int, dict[str, Any], str]] = []
    headers: list[str] = []
    seen: set[str] = set()
    for number, value, raw in items:
        if not isinstance(value, dict):
            rejected.append(Rejection(number, "the JSON value is not an object", _snippet(raw)))
            continue
        flat = _flatten(value)
        flat_rows.append((number, flat, raw))
        for key in flat:
            if key not in seen and len(seen) < 500:
                seen.add(key)
                headers.append(key)

    if not flat_rows:
        raise FormatError("no_records", "No JSON objects could be read from the file.", {"rejected": len(rejected)})

    mapping = resolve_columns(headers, column_mapping)
    # Nested names such as "error.message" are matched by their last part when the full name is unknown.
    if "message" not in mapping:
        for header in headers:
            tail = header.split(".")[-1]
            if _key(tail) in ALIASES["message"]:
                mapping["message"] = header
                break
    if "message" not in mapping and "exception_type" not in mapping:
        raise FormatError(
            "missing_required_columns",
            "No message field was found in the JSON records. Use a key called 'message' (or map one to it).",
            {"columns": headers[:50]},
        )

    records: list[RawRecord] = []
    truncated = 0
    for number, flat, raw in flat_rows:
        record = _row_to_record(number, flat, mapping, raw, headers)
        message = record.fields.get("message") or record.fields.get("exception_type")
        if not message:
            rejected.append(Rejection(number, "the message is empty", _snippet(raw)))
            continue
        if len(str(message)) > MAX_MESSAGE_CHARS:
            truncated += 1
        records.append(record)
    return ParseOutcome(records, total, blank, rejected, headers, mapping, truncated)


# ---------------------------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------------------------
_TS = r"\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
# 2026-03-10 08:15:03,123 ERROR [orders-service] message      (service in brackets)
# 2026-03-10T08:15:03Z ERROR orders-service: message          (service before a colon)
_WITH_SERVICE = re.compile(
    rf"^\[?(?P<ts>{_TS})\]?\s+\[?(?P<level>[A-Za-z]+)\]?\s+(?:\[(?P<svc>[^\]]+)\]|(?P<svc2>[A-Za-z0-9_.\-/]+):)\s*(?P<msg>.*)$"
)
# 2026-03-10 08:15:03 ERROR message                           (no service)
_NO_SERVICE = re.compile(rf"^\[?(?P<ts>{_TS})\]?\s+\[?(?P<level>[A-Za-z]+)\]?\s+(?P<msg>.*)$")
# Web-server access log: 10.0.0.5 - - [10/Mar/2026:08:15:03 +0000] "GET /orders HTTP/1.1" 503 512
_ACCESS = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>[A-Z]+) (?P<path>\S+)[^"]*" (?P<status>\d{3}) (?P<size>\S+)'
)
_LOGFMT_PAIR = re.compile(r'(\w[\w.\-]*)=("(?:[^"\\]|\\.)*"|\S*)')
_CONTINUATION = re.compile(r"^(\s+\S|Traceback \(most recent call last\)|Caused by:|\.\.\. \d+ more|[A-Za-z_.]+(?:Exception|Error)\b)")


def _logfmt(line: str) -> dict[str, str] | None:
    pairs = {k.lower(): v.strip('"') for k, v in _LOGFMT_PAIR.findall(line)}
    has_time = any(k in pairs for k in ("time", "ts", "timestamp", "t"))
    has_level = any(k in pairs for k in ("level", "lvl", "severity"))
    has_text = any(k in pairs for k in ("msg", "message"))
    if len(pairs) >= 3 and has_text and (has_time or has_level):
        return pairs
    return None


def _status_level(status: int) -> str:
    return "ERROR" if status >= 500 else "WARNING" if status >= 400 else "INFO"


def parse_text(text: str) -> ParseOutcome:
    records: list[RawRecord] = []
    rejected: list[Rejection] = []
    blank = 0
    truncated = 0
    total = 0
    previous: RawRecord | None = None

    for number, line in enumerate(text.splitlines(), start=1):
        total = number
        if not line.strip():
            blank += 1
            continue

        fields: dict[str, Any] | None = None
        extra: dict[str, Any] = {}

        m = _WITH_SERVICE.match(line)
        if m and normalize_level(m.group("level")):
            fields = {"timestamp": m.group("ts"), "level": m.group("level"),
                      "service": m.group("svc") or m.group("svc2"), "message": m.group("msg")}
        if fields is None:
            m = _NO_SERVICE.match(line)
            if m and normalize_level(m.group("level")):
                fields = {"timestamp": m.group("ts"), "level": m.group("level"), "message": m.group("msg")}
        if fields is None and (m := _ACCESS.match(line)):
            status = int(m.group("status"))
            fields = {
                "timestamp": m.group("ts"), "level": _status_level(status), "service": "web-server",
                "message": f"{m.group('method')} {m.group('path')} returned {status}",
                "http_status": status, "endpoint": m.group("path"),
            }
            extra["client_ip"] = m.group("ip")
        if fields is None and (pairs := _logfmt(line)):
            fields = {
                "timestamp": pairs.get("time") or pairs.get("ts") or pairs.get("timestamp") or pairs.get("t"),
                "level": pairs.get("level") or pairs.get("lvl") or pairs.get("severity"),
                "service": pairs.get("service") or pairs.get("component") or pairs.get("app"),
                "message": pairs.get("msg") or pairs.get("message"),
                "request_id": pairs.get("request_id") or pairs.get("req_id"),
                "host": pairs.get("host"),
            }
            extra = {k: v[:200] for k, v in pairs.items() if k not in {"time", "ts", "timestamp", "t", "level", "lvl",
                     "severity", "service", "component", "app", "msg", "message", "request_id", "req_id", "host"}}
            extra = dict(list(extra.items())[:MAX_EXTRA_COLUMNS])

        if fields is not None:
            fields = {k: _clean(v) for k, v in fields.items()}
            if not fields.get("message"):
                rejected.append(Rejection(number, "the message is empty", _snippet(line)))
                previous = None
                continue
            if len(str(fields["message"])) > MAX_MESSAGE_CHARS:
                truncated += 1
            previous = RawRecord(line_no=number, fields=fields, raw=line[:MAX_RAW_CHARS], extra=extra)
            records.append(previous)
            continue

        # Not a new record: stack traces and wrapped lines belong to the record above them.
        if previous is not None and _CONTINUATION.match(line):
            current = previous.fields.get("stack_trace") or ""
            if len(current) < MAX_STACK_CHARS:
                previous.fields["stack_trace"] = (current + "\n" + line.rstrip())[:MAX_STACK_CHARS].lstrip("\n")
            continue

        rejected.append(Rejection(number, "the line does not match a known log pattern", _snippet(line)))

    return ParseOutcome(records, total, blank, rejected, [], {}, truncated)
