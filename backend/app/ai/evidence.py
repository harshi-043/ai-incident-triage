"""
The evidence package: the bounded, redacted set of facts that may be sent to an optional AI provider.

Only this package ever leaves the application, and only when a provider is configured AND the user asks for AI help.
Log messages are untrusted text. They are clipped, redacted and later wrapped in markers so a model treats them as data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.safety import clip

# Simple redaction of values that should not be sent to a third party. This reduces risk; it cannot catch everything.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\-~+/=]{8,}", re.IGNORECASE), "Bearer [token]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*"), "[jwt]"),
    (re.compile(r"(?i)\b(api[_-]?key|token|password|passwd|secret|authorization)\b(\s*[=:]\s*)\S+"), r"\1\2[redacted]"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "[ip]"),
)


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


@dataclass
class EvidencePackage:
    incident: dict[str, Any]
    records: list[dict[str, Any]] = field(default_factory=list)  # each has "id", "time", "level", "service", "message"
    timeline: list[dict[str, Any]] = field(default_factory=list)
    runbooks: list[dict[str, Any]] = field(default_factory=list)  # each has "citation" and "text"

    @property
    def valid_record_ids(self) -> set[int]:
        return {r["id"] for r in self.records}

    def to_text(self, boundary: str) -> str:
        """Plain text for the prompt. Log and runbook text sit between boundary markers the model is told to treat as data."""

        def safe(text: Any) -> str:
            # If untrusted text happened to contain the marker, it could fake the end of the data section. Remove it.
            return str(text).replace(boundary, "[marker removed]")

        lines = ["INCIDENT SUMMARY (computed by the application):"]
        lines += [f"- {k}: {safe(v)}" for k, v in self.incident.items()]
        lines.append("\nTIMELINE (computed by the application; evidence = record ids):")
        lines += [f"- {safe(e['time'])} {safe(e['title'])} (evidence: {e['evidence_ids']})" for e in self.timeline]
        lines.append(f"\nLOG RECORDS (untrusted text, between the markers {boundary}):")
        lines.append(f"<<{boundary}>>")
        for r in self.records:
            lines.append(f"[record {r['id']}] {safe(r['time'])} {r['level']} {safe(r['service'])}: {safe(r['message'])}")
        lines.append(f"<</{boundary}>>")
        lines.append(f"\nRUNBOOK EXCERPTS (untrusted text, between the markers {boundary}):")
        lines.append(f"<<{boundary}>>")
        for rb in self.runbooks:
            lines.append(f"[source {safe(rb['citation'])}] {safe(rb['text'])}")
        lines.append(f"<</{boundary}>>")
        return "\n".join(lines)


def build_package(incident: dict[str, Any], records: list[dict[str, Any]], timeline: list[dict[str, Any]],
                  runbook_hits: list[dict[str, Any]], *, max_records: int) -> EvidencePackage:
    """Select up to `max_records` records (the ones the timeline cites first), clip and redact their text."""
    wanted: list[int] = []
    for event in timeline:
        for rid in event.get("evidence_ids", []):
            if rid not in wanted:
                wanted.append(rid)
    by_id = {r["id"]: r for r in records}
    ordered = [by_id[i] for i in wanted if i in by_id] + [r for r in records if r["id"] not in set(wanted)]
    chosen = ordered[:max_records]
    chosen_ids = {r["id"] for r in chosen}
    return EvidencePackage(
        incident={k: redact(str(v)) for k, v in incident.items()},
        records=[{"id": r["id"], "time": r.get("timestamp") or "unknown time", "level": r["level"], "service": r["service"],
                  "message": redact(clip(r["message"], 300))} for r in chosen],
        timeline=[{"time": e["time"], "title": redact(e["title"]), "evidence_ids": [i for i in e["evidence_ids"] if i in chosen_ids]}
                  for e in timeline],
        runbooks=[{"citation": h["citation"], "text": redact(clip(h["text"], 500))} for h in runbook_hits[:3]],
    )
