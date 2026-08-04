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


# Connection-pool sizing (PROD-F12). The ASGI worker runs sync route handlers on
# anyio's 40-thread pool, so a 5+10 default pool starves it under load. 20+10
# covers the threadpool with headroom while staying well inside the Postgres
# `max_connections` budget for the single replica we deploy.
_POOL_SIZE = 20
_MAX_OVERFLOW = 10
# Azure Container Apps / Azure PG silently drop idle TCP; pre-ping turns a dead
# pooled connection into a transparent reconnect instead of a 500.
_POOL_RECYCLE_SECONDS = 1800


def _make_engine(url: str):
    connect_args = {}
    # WS4-F8: never let SQLAlchemy stringify bound parameters into exception
    # text. `StatementError.__str__` otherwise appends `[parameters: (...)]`,
    # and any call site that interpolates the exception into a log message
    # would push raw PHI into the log stream, bypassing the `extra` allow-list.
    kwargs: dict = {"future": True, "hide_parameters": True}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Ensure the parent dir for a file-based sqlite db exists.
        if ":///" in url and not url.endswith(":memory:"):
            path = url.split(":///", 1)[1]
            if path and path not in (":memory:",):
                os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    else:
        # SQLite uses SingletonThreadPool/StaticPool, which accepts none of these.
        kwargs.update(
            pool_size=_POOL_SIZE,
            max_overflow=_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=_POOL_RECYCLE_SECONDS,
        )
    return create_engine(url, connect_args=connect_args, **kwargs)


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
