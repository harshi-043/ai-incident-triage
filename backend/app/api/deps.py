"""Shared request helpers: settings, id checks and the pagination limits."""
from __future__ import annotations

from fastapi import Request

from app.core.config import Settings
from app.core.errors import ID_PATTERN, bad_id

MAX_PAGE_SIZE = 200


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def check_id(value: str, what: str) -> str:
    """Reject malformed ids with a 422 before touching the database."""
    if not ID_PATTERN.match(value or ""):
        raise bad_id(what, value or "")
    return value
