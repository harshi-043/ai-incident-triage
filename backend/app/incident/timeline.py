"""
Build the chronological timeline of one incident from its real log records.

Every event is either:
  observed  a fact read directly from one or more log records (it lists their ids as evidence), or
  inferred  a conclusion drawn from the records (for example "no more errors after 09:27").
Inferred events say so in their text. Records without a timestamp cannot be placed on a timeline.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter

from app.incident.types import Group, Rec, TimelineEvent

CONTEXT_WORDS = re.compile(
    r"\b(deploy\w*|rollback|restart\w*|shut(?:ting)?[ -]?down|config\w*|scal(?:e|ed|ing)\w*|migrat\w*|failover|"
    r"recover\w*|maintenance|started version|upgrad\w*)\b", re.IGNORECASE)
LATENCY_FLOOR_MS = 2000.0
MAX_EVIDENCE_PER_EVENT = 5
MAX_PATTERN_EVENTS = 8


def is_context_event(record: Rec) -> bool:
    """An INFO/DEBUG line about a deployment, restart, failover, recovery and the like."""
    return record.rank <= 1 and bool(CONTEXT_WORDS.search(record.message))


def _clip(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _hhmm(record: Rec) -> str:
    return record.ts.strftime("%H:%M:%S") if record.ts else "?"


def build_timeline(
    errors: list[Rec], warnings: list[Rec], context: list[Rec], groups: list[Group], baseline_latency_ms: float | None,
) -> list[TimelineEvent]:
    """`errors` are the error-level records of the incident, `warnings` the attached warning records, `context` the INFO events."""
    timed_errors = sorted((r for r in errors if r.ts), key=lambda r: (r.ts, r.id))
    if not timed_errors:
        return []
    first, last = timed_errors[0], timed_errors[-1]
    events: list[TimelineEvent] = []

    # Warnings that started before the first error: an early sign, reported as a correlation only.
    early = sorted((r for r in warnings if r.ts and r.ts < first.ts), key=lambda r: (r.ts, r.id))
    if early:
        minutes = (first.ts - early[0].ts).total_seconds() / 60
        events.append(TimelineEvent(
            early[0].ts, "early_warning", f"Warnings began {minutes:.0f} min before the first error",
            f"{early[0].service}: {_clip(early[0].message)}. This is an observed sequence, not proof that the warnings caused the errors.",
            "observed", [r.id for r in early[:MAX_EVIDENCE_PER_EVENT]]))

    for record in sorted(context, key=lambda r: (r.ts or first.ts, r.id)):
        if record.ts:
            events.append(TimelineEvent(
                record.ts, "context_event", f"Operational event: {_clip(record.message, 100)}",
                f"{record.service} logged this near the incident. It is shown for context; being close in time does not show it was the cause.",
                "observed", [record.id]))

    events.append(TimelineEvent(
        first.ts, "first_error", f"First error: {first.service}",
        _clip(first.message), "observed", [first.id]))

    # First appearance of each pattern, in time order.
    error_ids = {r.id for r in timed_errors}
    ranked = sorted(groups, key=lambda g: -sum(1 for r in g.records if r.id in error_ids))
    seen_service: set[str] = {first.service}
    for group in ranked[:MAX_PATTERN_EVENTS]:
        members = sorted((r for r in group.records if r.ts and first.ts <= r.ts <= last.ts and r.is_error), key=lambda r: (r.ts, r.id))
        if not members or members[0].id == first.id:
            continue
        events.append(TimelineEvent(
            members[0].ts, "pattern_first_seen", f"New error pattern in {members[0].service}",
            f"{_clip(group.template)} ({len(members)} occurrence(s) during the incident).", "observed", [members[0].id]))
    for record in timed_errors:  # the first error of each further service
        if record.service not in seen_service:
            seen_service.add(record.service)
            events.append(TimelineEvent(
                record.ts, "service_affected", f"{record.service} started reporting errors",
                _clip(record.message), "observed", [record.id]))

    five_xx = [r for r in timed_errors if r.http_status and r.http_status >= 500]
    if five_xx:
        statuses = Counter(r.http_status for r in five_xx)
        code, _ = statuses.most_common(1)[0]
        events.append(TimelineEvent(
            five_xx[0].ts, "http_5xx", f"First HTTP {five_xx[0].http_status} response",
            f"{len(five_xx)} server-error responses in the incident; most common status {code}.", "observed", [five_xx[0].id]))

    slow = _first_slow(timed_errors + [r for r in warnings if r.ts], baseline_latency_ms)
    if slow:
        threshold, record = slow
        events.append(TimelineEvent(
            record.ts, "latency_threshold", f"A reported duration first exceeded {threshold:,.0f} ms",
            f"{record.service} reported {record.latency_ms:,.0f} ms (a latency or a timeout, as written in the message): {_clip(record.message, 100)}", "observed", [record.id]))

    # Busiest minute.
    per_minute = Counter(r.ts.replace(second=0, microsecond=0) for r in timed_errors)
    minute, count = per_minute.most_common(1)[0]
    events.append(TimelineEvent(
        minute, "peak", f"Busiest minute: {count} error-level records",
        f"Between {minute:%H:%M} and {minute:%H:%M}:59.", "observed",
        [r.id for r in timed_errors if r.ts.replace(second=0, microsecond=0) == minute][:MAX_EVIDENCE_PER_EVENT]))

    events.append(TimelineEvent(
        last.ts, "last_error", f"Last error: {last.service}", _clip(last.message), "observed", [last.id]))
    events.append(TimelineEvent(
        last.ts, "quiet_after", f"No more error-level records after {_hhmm(last)}",
        "Inferred from the absence of errors in this file. It suggests the incident ended, but the logs alone cannot confirm recovery.",
        "inferred", [last.id]))  # the last error is the evidence that the quiet period started after it

    order = {"early_warning": 0, "context_event": 1, "first_error": 2, "service_affected": 3, "pattern_first_seen": 4,
            "http_5xx": 5, "latency_threshold": 6, "peak": 7, "last_error": 8, "quiet_after": 9}
    events.sort(key=lambda e: (e.time, order.get(e.kind, 5)))
    return events


def _first_slow(records: list[Rec], baseline: float | None) -> tuple[float, Rec] | None:
    threshold = max(LATENCY_FLOOR_MS, 5 * baseline) if baseline else LATENCY_FLOOR_MS
    slow = sorted((r for r in records if r.latency_ms and r.latency_ms >= threshold and r.ts), key=lambda r: (r.ts, r.id))
    return (threshold, slow[0]) if slow else None


def median_latency(records: list[Rec]) -> float | None:
    values = [r.latency_ms for r in records if r.latency_ms]
    return statistics.median(values) if values else None
