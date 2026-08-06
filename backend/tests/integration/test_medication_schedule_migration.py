"""Integration tests for the J3/M5 medication-scheduling migration on REAL
PostgreSQL (Master Plan §3): upgrade/downgrade/re-upgrade roundtrip, JSONB parity,
and the dose idempotency unique constraint.

Usage (local):
    POSTGRES_TEST_URL="postgresql://mcp:mcp_dev_only@127.0.0.1:5544/mcp_test" \
    pytest tests/integration/test_medication_schedule_migration.py -v -m integration
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")
HEAD = "j3_m5_medication_schedule"
PRE = "mdi_s0_medical_documents"
TABLES = ("medication_schedules", "dose_occurrences")

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if not POSTGRES_TEST_URL:
        pytest.skip("POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests.")


def _cfg(db_url: str) -> Config:
    os.environ["MCP_DATABASE_URL"] = db_url
    from app.core.config import get_settings

    get_settings.cache_clear()
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Generator[sa.Engine, None, None]:
    _require_postgres()
    engine = sa.create_engine(POSTGRES_TEST_URL, echo=False, future=True)
    with engine.connect() as conn:
        assert conn.dialect.name == "postgresql"
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def cfg(pg_engine: sa.Engine) -> Config:
    return _cfg(pg_engine.url.render_as_string(hide_password=False))


def test_upgrade_creates_tables_and_jsonb(pg_engine: sa.Engine, cfg: Config):
    command.upgrade(cfg, HEAD)
    insp = sa.inspect(pg_engine)
    for t in TABLES:
        assert insp.has_table(t)
    cols = {c["name"]: c for c in insp.get_columns("medication_schedules")}
    assert cols["local_dose_times"]["type"].__class__.__name__.upper().startswith("JSONB")


def test_dose_idempotency_unique_constraint(pg_engine: sa.Engine, cfg: Config):
    command.upgrade(cfg, HEAD)
    insp = sa.inspect(pg_engine)
    uqs = {u["name"] for u in insp.get_unique_constraints("dose_occurrences")}
    assert "uq_dose_idempotency_key" in uqs


def test_downgrade_reupgrade_roundtrip(pg_engine: sa.Engine, cfg: Config):
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, PRE)
    insp = sa.inspect(pg_engine)
    for t in TABLES:
        assert not insp.has_table(t)
    command.upgrade(cfg, HEAD)
    insp = sa.inspect(pg_engine)
    for t in TABLES:
        assert insp.has_table(t)
    command.downgrade(cfg, PRE)
