"""Light-weight records used by the grouping and detection code (no database objects)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.ingestion.normalize import LEVEL_RANK


@dataclass(slots=True)
class Rec:
    """The few fields of a log record that grouping and incident detection need."""

    id: int
    line_no: int
    ts: datetime | None
    level: str
    service: str
    exception_type: str | None
    template: str  # the masked message
    message: str
    http_status: int | None = None
    latency_ms: float | None = None
    request_id: str | None = None

    @property
    def rank(self) -> int:
        return LEVEL_RANK.get(self.level, 1)

    @property
    def is_error(self) -> bool:
        """Error-level: ERROR or CRITICAL, or an HTTP 5xx response, whatever the log level says."""
        return self.rank >= LEVEL_RANK["ERROR"] or (self.http_status is not None and self.http_status >= 500)

    @property
    def is_problem(self) -> bool:
        """Worth grouping: WARNING or worse, or an HTTP 5xx."""
        return self.rank >= LEVEL_RANK["WARNING"] or (self.http_status is not None and self.http_status >= 500)


@dataclass
class Group:
    """A set of related problem records."""

    key: str
    title: str
    template: str
    services: list[str]
    exception_types: list[str]
    method: str  # "exact" or "similarity"
    explanation: str
    member_templates: list[dict]
    records: list[Rec]
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    max_level: str = "WARNING"
    id: str = ""

    @property
    def count(self) -> int:
        return len(self.records)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.records if r.is_error)


@dataclass
class DetectionParams:
    similarity_threshold: float = 0.6
    gap_minutes: int = 10
    min_errors: int = 5
    merge_across_services: bool = False
    lead_minutes: int = 10  # how far before the first error related warnings are still attached
    lag_minutes: int = 2
    concentration: float = 0.4  # a warning pattern is attached when this share of it falls inside the window


@dataclass
class TimelineEvent:
    time: datetime | None
    kind: str
    title: str
    detail: str
    origin: str  # "observed" (read directly from log records) or "inferred" (concluded from the records)
    evidence_ids: list[int] = field(default_factory=list)


@dataclass
class IncidentDraft:
    number: int
    title: str
    severity: str
    first_seen: datetime | None
    last_seen: datetime | None
    records: list[Rec]
    error_count: int
    services: list[str]
    groups: list[Group]
    timeline: list[TimelineEvent]
    detection: dict
    explanation: str
    top_patterns: list[dict]
    related_numbers: list[int] = field(default_factory=list)
