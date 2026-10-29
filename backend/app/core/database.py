"""Engine, session factory and safe database initialisation."""
from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.models.tables import Base

logger = logging.getLogger("triage")

# Bump this when a table or column changes. See init_db for what happens on a mismatch.
SCHEMA_VERSION = 1


def new_id(prefix: str) -> str:
    """Public ids: a short prefix and 16 random hex characters, e.g. 'inc_9f2c41d0a7b3e655'."""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def make_engine(database_url: str) -> Engine:
    """Create the engine. For SQLite, allow use from worker threads and enforce foreign keys."""
    is_sqlite = database_url.startswith("sqlite")
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
        pool_pre_ping=True,
    )
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """
    Create the tables if they are missing, so the app starts from a clean checkout.

    This only ADDS tables. For SQLite the schema version is stored in the file; if an existing
    database was made by a different version we stop with a clear message instead of running
    against a mismatched schema (real deployments should use a migration tool such as Alembic).
    """
    existing = set(inspect(engine).get_table_names())
    is_sqlite = engine.dialect.name == "sqlite"

    if is_sqlite and existing:
        with engine.connect() as connection:
            version = connection.execute(text("PRAGMA user_version")).scalar_one()
        if version != SCHEMA_VERSION:
            raise RuntimeError(
                f"The database has schema version {version} but this app expects {SCHEMA_VERSION}. "
                "Back up and delete storage/triage.db (the app will create a new one), or migrate it."
            )

    Base.metadata.create_all(engine)

    if is_sqlite and not existing:
        with engine.begin() as connection:
            connection.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
    logger.info("Database ready (%s)", engine.dialect.name)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    with request.app.state.session_factory() as session:
        yield session
