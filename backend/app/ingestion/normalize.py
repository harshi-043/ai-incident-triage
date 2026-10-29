"""
Small, safe converters: severity levels and timestamps.

Both functions return None when the value cannot be understood. They never guess and never raise,
so a bad value becomes a data-quality warning instead of a crash.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LEVEL_RANK = {level: rank for rank, level in enumerate(LEVELS)}

_LEVEL_ALIASES = {
    "trace": "DEBUG", "debug": "DEBUG", "dbg": "DEBUG", "verbose": "DEBUG",
    "info": "INFO", "information": "INFO", "informational": "INFO", "notice": "INFO", "inf": "INFO",
    "warn": "WARNING", "warning": "WARNING", "wrn": "WARNING",
    "err": "ERROR", "error": "ERROR", "severe": "ERROR", "fail": "ERROR", "failure": "ERROR",
    "crit": "CRITICAL", "critical": "CRITICAL", "fatal": "CRITICAL", "emerg": "CRITICAL",
    "emergency": "CRITICAL", "alert": "CRITICAL", "panic": "CRITICAL",
}


def normalize_level(value: Any) -> str | None:
    """'warn' -> 'WARNING', 'FATAL' -> 'CRITICAL', anything unknown -> None."""
    if value is None:
        return None
    return _LEVEL_ALIASES.get(str(value).strip().strip("[]").lower())


_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S",
    "%d/%b/%Y:%H:%M:%S %z",  # web-server access logs: 10/Mar/2026:08:15:03 +0000
    "%d/%m/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%d-%b-%Y %H:%M:%S",
)
_EPOCH = re.compile(r"^\d{10}(\.\d+)?$|^\d{13}$")


def parse_timestamp(value: Any) -> tuple[datetime | None, bool]:
    """
    Parse a timestamp. Returns (value_in_UTC, assumed_utc).

    `assumed_utc` is True when the text had no time zone, so UTC was assumed (the caller reports this
    as a warning). Returns (None, False) when the text is not a timestamp at all.
    """
    if value is None:
        return None, False
    text = str(value).strip().strip("[]")
    if not text or text.lower() in {"nan", "nat", "none", "null", "-"}:
        return None, False

    if _EPOCH.match(text):  # unix seconds (10 digits) or milliseconds (13 digits)
        number = float(text)
        number = number / 1000 if len(text.split(".")[0]) == 13 else number
        try:
            return datetime.fromtimestamp(number, UTC), False
        except (OverflowError, OSError, ValueError):
            return None, False

    candidate = text.replace(",", ".")  # Java style 10:15:03,123
    candidate = re.sub(r"Z$", "+00:00", candidate, flags=re.IGNORECASE)
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in _FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None, False
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC), True
    return parsed.astimezone(UTC), False


def to_naive_utc(value: datetime | None) -> datetime | None:
    """The database stores naive UTC."""
    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def iso_z(value: datetime | None) -> str | None:
    """Naive UTC from the database -> '2026-03-10T08:15:03Z' for the API."""
    if value is None:
        return None
    return value.isoformat(timespec="seconds" if value.microsecond == 0 else "milliseconds") + "Z"
