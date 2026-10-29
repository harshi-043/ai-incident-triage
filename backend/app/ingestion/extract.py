"""
Pull common fields out of a free-text log message when the file has no separate column for them
(request id, HTTP status, latency, route, exception type ...).

Everything here is a plain regular expression over text. Nothing is executed or evaluated.
"""
from __future__ import annotations

import re
from typing import Any

_REQUEST_ID = (
    re.compile(r"(?:request[_-]?id|req[_-]?id|x-request-id)[=:\s\"']+([A-Za-z0-9_\-]{6,64})", re.IGNORECASE),
    re.compile(r"\b(req-[A-Za-z0-9]{6,})\b", re.IGNORECASE),
)
_TRACE_ID = re.compile(r"trace[_-]?id[=:\s\"']+([A-Za-z0-9_\-]{8,64})", re.IGNORECASE)
_STATUS = (
    re.compile(r"\bstatus(?:[_ ]code)?[=:\s]+([1-5]\d{2})\b", re.IGNORECASE),
    re.compile(r"\bHTTP/\d(?:\.\d)?\"?\s+([1-5]\d{2})\b"),
    re.compile(r"\b(?:returned|responded with|response)\s+(?:HTTP\s+)?([1-5]\d{2})\b", re.IGNORECASE),
    re.compile(r"\bHTTP\s+([1-5]\d{2})\b"),
)
_LATENCY = (
    re.compile(r"\b(?:latency|duration|elapsed|response[_ ]time)(?:_ms)?[=:\s]+(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds)?\b", re.IGNORECASE),
    re.compile(r"\b(?:took|after)\s+(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds)\b", re.IGNORECASE),
)
_ROUTE = (
    re.compile(r"\b(RT-\d{1,4})\b"),
    re.compile(r"\broute[_-]?id[=:\s\"']+([A-Za-z0-9_\-]{2,30})", re.IGNORECASE),
)
_ENDPOINT = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH|HEAD)\s+(/[^\s\"']*)")
_HOST = re.compile(r"\bhost[=:\s\"']+([A-Za-z0-9_.\-]{2,80})", re.IGNORECASE)
# "java.sql.SQLTransientConnectionException", "ConnectionRefusedError", "NullPointerException", "ReadTimeout"
_EXCEPTION = re.compile(r"\b((?:[A-Za-z_][\w]*\.)*[A-Z][A-Za-z0-9]*(?:Exception|Error|Timeout|Failure|Refused))\b")
_PACKET_LOSS = re.compile(r"packet[_ ]loss[=:\s]+(\d+(?:\.\d+)?)\s*%?", re.IGNORECASE)


def _first(patterns: tuple[re.Pattern[str], ...] | re.Pattern[str], text: str) -> re.Match[str] | None:
    for pattern in patterns if isinstance(patterns, tuple) else (patterns,):
        match = pattern.search(text)
        if match:
            return match
    return None


def extract_fields(text: str) -> dict[str, Any]:
    """Return only the fields that were found. Missing ones are simply absent."""
    found: dict[str, Any] = {}
    if not text:
        return found

    if m := _first(_REQUEST_ID, text):
        found["request_id"] = m.group(1)
    if m := _first(_TRACE_ID, text):
        found["trace_id"] = m.group(1)
    if m := _first(_STATUS, text):
        found["http_status"] = int(m.group(1))
    if m := _first(_LATENCY, text):
        value = float(m.group(1))
        unit = (m.group(2) or "ms").lower()
        found["latency_ms"] = value * 1000 if unit in {"s", "sec", "seconds"} else value
    if m := _first(_ROUTE, text):
        found["route_id"] = m.group(1)
    if m := _ENDPOINT.search(text):
        found["endpoint"] = m.group(2)[:300]
    if m := _HOST.search(text):
        found["host"] = m.group(1)
    if m := _EXCEPTION.search(text):
        found["exception_type"] = m.group(1)[:200]
    if m := _PACKET_LOSS.search(text):
        found["packet_loss_pct"] = float(m.group(1))
    return found
