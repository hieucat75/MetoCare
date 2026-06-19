"""Database engine / session setup (SQLAlchemy 2.x).

Dev/test default to SQLite (see config). Production uses PostgreSQL + TimescaleDB
via `MCP_DATABASE_URL`. The model layer is written to be portable; TimescaleDB
hypertable creation for `health_metric` is a P1 migration concern (Alembic).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _make_engine(url: str):
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Ensure the parent dir for a file-based sqlite db exists.
        if ":///" in url and not url.endswith(":memory:"):
            path = url.split(":///", 1)[1]
            if path and path not in (":memory:",):
                os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    return create_engine(url, connect_args=connect_args, future=True)


_settings = get_settings()
engine = _make_engine(_settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def create_all() -> None:
    """Create tables for dev/test. Production uses Alembic migrations.

    WARNING: This function must NOT be called in production environments.
    Production schema is managed exclusively by Alembic (`alembic upgrade head`
    runs in CI/CD before container restart). Calling create_all() in production
    would bypass migrations, miss TimescaleDB hypertable setup, and risk
    schema drift. This function is safe for SQLite dev/test only.
    """
    import warnings

    from .config import get_settings as _get_settings

    if _get_settings().is_prod:
        warnings.warn(
            "create_all() called in production mode! This bypasses Alembic migrations. "
            "In production, schema is managed by 'alembic upgrade head' in CI/CD. "
            "Skipping create_all() to avoid schema drift.",
            RuntimeWarning,
            stacklevel=2,
        )
        return

    # Import models so they register with Base.metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine, checkfirst=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
