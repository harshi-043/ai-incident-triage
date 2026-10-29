"""
Application settings, read from environment variables (or a local .env file).

Nothing secret is needed to run the app. The AI provider is OFF by default ("none").
Relative paths are resolved against the backend folder, so it does not matter
which folder you start the server from.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Upload formats the ingestion layer understands.
ALLOWED_LOG_EXTENSIONS = (".csv", ".txt", ".log", ".json", ".jsonl", ".ndjson")
ALLOWED_RUNBOOK_EXTENSIONS = (".md", ".markdown", ".txt", ".pdf")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "AI Log/Incident Triage Assistant API"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # Comma-separated list of browser origins allowed to call the API.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Local files: the SQLite database and the runbook vector index.
    storage_dir: Path = BACKEND_DIR / "storage"
    database_url: str | None = None  # default: SQLite file inside storage_dir

    # Folder with the bundled synthetic runbooks (loaded on request, never executed).
    sample_runbook_dir: Path = BACKEND_DIR / "data" / "sample_runbooks"

    # Upload limits.
    max_upload_mb: int = Field(10, ge=1, le=100)
    max_log_records: int = Field(200_000, ge=100)
    max_runbook_mb: int = Field(5, ge=1, le=50)

    # Incident detection defaults (can be changed per analysis in the UI).
    similarity_threshold: float = Field(0.6, ge=0.1, le=0.99)
    incident_gap_minutes: int = Field(10, ge=1, le=240)
    incident_min_errors: int = Field(5, ge=2, le=10_000)

    # Retrieval defaults.
    chunk_size_chars: int = Field(900, ge=200, le=4000)
    chunk_overlap_chars: int = Field(120, ge=0, le=1000)
    # 0.16 was chosen from scripts/evaluate_retrieval.py (small synthetic set): see the README for the trade-off.
    min_relevance: float = Field(0.16, ge=0.0, le=1.0)

    # ---- optional AI provider (OFF by default) ------------------------------------
    # "none" keeps everything deterministic. "anthropic", "openai" and "openai_compatible"
    # send a bounded evidence package to that service. See the README privacy note.
    ai_provider: str = "none"
    ai_api_key: str | None = None  # read from the environment, never stored or logged
    ai_model: str | None = None
    ai_base_url: str | None = None  # needed for "openai_compatible"
    ai_timeout_seconds: float = Field(30.0, ge=1.0, le=300.0)
    ai_max_evidence_records: int = Field(25, ge=3, le=100)

    # "tfidf" always works. "sentence_transformers" needs the optional package and a model download.
    embedding_backend: str = "tfidf"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    @field_validator("storage_dir", "sample_runbook_dir", mode="after")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    @field_validator("ai_provider", "embedding_backend", mode="after")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()

    # ---- derived values --------------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_runbook_bytes(self) -> int:
        return self.max_runbook_mb * 1024 * 1024

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.storage_dir / 'triage.db').as_posix()}"

    @property
    def index_dir(self) -> Path:
        return self.storage_dir / "index"

    def ensure_directories(self) -> None:
        """Create the storage folders. Called at server start, not at import."""
        for folder in (self.storage_dir, self.index_dir):
            folder.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
