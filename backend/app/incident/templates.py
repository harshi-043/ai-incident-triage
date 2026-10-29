"""
Message masking: turn a log message into a "template" by hiding the parts that change from line to line
(ids, numbers, addresses, times). Two lines with the same template are the same kind of event.

    "Timeout waiting for connection (pool=orders-db, waiting=14, req-9f3a1c)"
    -> "Timeout waiting for connection (pool=orders-db, waiting=<NUM>, <ID>)"

The original message is never changed. The template is stored next to it and used only for grouping.
"""
from __future__ import annotations

import re

# Order matters: the most specific patterns run first.
_MASKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"), "<TS>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{2,5})?\b"), "<IP>"),
    (re.compile(r"\b(?:req|request|trace|span|txn|tx|sess|session)[-_][A-Za-z0-9]{4,}\b", re.IGNORECASE), "<ID>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b[0-9a-f]{8,}\b"), "<HEX>"),
    # Numbers, also inside words like "node-12" or "1234ms". Not inside names like "utf8" or "ipv4".
    (re.compile(r"(?<![A-Za-z_])\d+(?:\.\d+)?"), "<NUM>"),
)
_SPACES = re.compile(r"\s+")


def mask_message(message: str) -> str:
    """Return the masked template of a message (see module docstring)."""
    text = message or ""
    for pattern, replacement in _MASKS:
        text = pattern.sub(replacement, text)
    return _SPACES.sub(" ", text).strip()[:500]
