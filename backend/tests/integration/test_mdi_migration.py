"""Integration tests for the MDI Slice 0 migration on REAL PostgreSQL.

Verifies (Master Plan §3): real-Postgres upgrade/downgrade/re-upgrade roundtrip,
JSONB column parity (JSON on SQLite → JSONB on Postgres), and that the idempotency
unique constraints exist at the DB layer. SQLite behavioural coverage lives in
tests/api/test_documents_api.py + tests/test_mdi_storage.py.

Usage (local):
    POSTGRES_TEST_URL="postgresql://mcp:mcp_dev_only@127.0.0.1:5544/mcp_test" \
    pytest tests/integration/test_mdi_migration.py -v -m integration
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")
MDI_HEAD = "mdi_s0_medical_documents"
PRE_MDI_REV = "k2_s0_round3_hardening"

pytestmark = pytest.mark.integration

MDI_TABLES = (
    "medical_documents",
    "document_pages",
    "document_extractions",
    "extraction_candidates",
    "promotion_links",
)


def _require_postgres() -> None:
    if not POSTGRES_TEST_URL:
        pytest.skip("POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests.")


def _make_alembic_config(db_url: str) -> Config:
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
    return _make_alembic_config(pg_engine.url.render_as_string(hide_password=False))


def test_upgrade_creates_all_mdi_tables(pg_engine: sa.Engine, cfg: Config):
    command.upgrade(cfg, MDI_HEAD)
    insp = sa.inspect(pg_engine)
    for table in MDI_TABLES:
        assert insp.has_table(table), f"missing table after upgrade: {table}"


def test_jsonb_parity_on_postgres(pg_engine: sa.Engine, cfg: Config):
    command.upgrade(cfg, MDI_HEAD)
    insp = sa.inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("extraction_candidates")}
    # JSON().with_variant(JSONB) must render as JSONB on Postgres.
    assert cols["fields_json"]["type"].__class__.__name__.upper().startswith("JSONB")


def test_idempotency_unique_constraints_exist(pg_engine: sa.Engine, cfg: Config):
    command.upgrade(cfg, MDI_HEAD)
    insp = sa.inspect(pg_engine)
    cand_uqs = {u["name"] for u in insp.get_unique_constraints("extraction_candidates")}
    link_uqs = {u["name"] for u in insp.get_unique_constraints("promotion_links")}
    page_uqs = {u["name"] for u in insp.get_unique_constraints("document_pages")}
    assert "uq_extraction_dedupe_key" in cand_uqs
    assert "uq_promotion_candidate_once" in link_uqs
    assert "uq_document_page_no" in page_uqs


def test_downgrade_then_reupgrade_roundtrip(pg_engine: sa.Engine, cfg: Config):
    command.upgrade(cfg, MDI_HEAD)
    command.downgrade(cfg, PRE_MDI_REV)
    insp = sa.inspect(pg_engine)
    for table in MDI_TABLES:
        assert not insp.has_table(table), f"table survived downgrade: {table}"
    # Re-upgrade must succeed and restore every table (additive, reversible).
    command.upgrade(cfg, MDI_HEAD)
    insp = sa.inspect(pg_engine)
    for table in MDI_TABLES:
        assert insp.has_table(table)
    # Leave the DB at the pre-MDI revision for any later test module.
    command.downgrade(cfg, PRE_MDI_REV)
