"""Shared test setup. Every test gets its own temporary storage folder and database."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    # _env_file=None: a developer's local .env must never change test behaviour.
    return Settings(
        _env_file=None,
        storage_dir=tmp_path / "storage",
        sample_runbook_dir=tmp_path / "runbooks",
        max_upload_mb=1,
        max_log_records=5000,
        ai_provider="none",
    )


@pytest.fixture
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:  # the context manager runs startup, which creates the tables
        yield test_client
