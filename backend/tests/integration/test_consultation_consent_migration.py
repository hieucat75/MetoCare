"""Integration tests for the consultation-consent migration on REAL PostgreSQL.

The behavioural suite runs on SQLite, which cannot see the things that actually
break a deploy here: JSON vs JSONB, and whether the one-consent-per-consultation
rule is enforced by the database or only by the service that happens to write it.
This repo has already shipped a migration that passed on SQLite and failed on
Postgres, so the rehearsal is part of the change, not an optional extra.

Usage (local):
    POSTGRES_TEST_URL="postgresql://mcp@127.0.0.1:5544/mcp_test" \
    pytest tests/integration/test_consultation_consent_migration.py -v -m integration
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")
CONSENT_HEAD = "mkt_c1_consult_consent"
PRE_CONSENT_REV = "j3_m7_sched_lifecycle"
TABLE = "consultation_data_consents"

pytestmark = pytest.mark.integration


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


def test_upgrade_creates_the_consent_table(pg_engine: sa.Engine, cfg: Config):
    command.upgrade(cfg, CONSENT_HEAD)
    assert sa.inspect(pg_engine).has_table(TABLE)


def test_categories_is_jsonb_on_postgres(pg_engine: sa.Engine, cfg: Config):
    """JSON().with_variant(JSONB) must actually render as JSONB here."""
    command.upgrade(cfg, CONSENT_HEAD)
    cols = {c["name"]: c for c in sa.inspect(pg_engine).get_columns(TABLE)}
    assert cols["categories"]["type"].__class__.__name__.upper().startswith("JSONB")
    assert cols["categories"]["nullable"] is False


def test_one_consent_per_consultation_is_a_database_constraint(
    pg_engine: sa.Engine, cfg: Config
):
    """The single-consent invariant must not rest on service discipline.

    Two concurrent bookings racing on the same consultation id would otherwise
    each insert a consent row, leaving two records disagreeing about what was
    granted — and revocation would flip only one of them.
    """
    command.upgrade(cfg, CONSENT_HEAD)
    uniques = {u["name"] for u in sa.inspect(pg_engine).get_unique_constraints(TABLE)}
    assert "uq_consultation_data_consent_consultation" in uniques


def test_consent_is_foreign_keyed_to_consultation_patient_and_doctor(
    pg_engine: sa.Engine, cfg: Config
):
    """A consent row pointing at a consultation/patient/doctor that does not
    exist is not evidence of anything — the database must refuse it."""
    command.upgrade(cfg, CONSENT_HEAD)
    fks = sa.inspect(pg_engine).get_foreign_keys(TABLE)
    referred = {(tuple(fk["constrained_columns"]), fk["referred_table"]) for fk in fks}
    assert (("consultation_id",), "consultations") in referred
    assert (("patient_id",), "patient_profiles") in referred
    assert (("doctor_id",), "doctors") in referred


def test_not_null_columns_cannot_record_a_consent_without_provenance(
    pg_engine: sa.Engine, cfg: Config
):
    """purpose, both versions, categories and granted_at are what make the row
    a defensible record. None may be NULL."""
    command.upgrade(cfg, CONSENT_HEAD)
    cols = {c["name"]: c for c in sa.inspect(pg_engine).get_columns(TABLE)}
    for name in (
        "consultation_id",
        "patient_id",
        "doctor_id",
        "purpose",
        "consent_version",
        "policy_version",
        "categories",
        "granted_at",
    ):
        assert cols[name]["nullable"] is False, f"{name} must be NOT NULL"
    # revoked_at must be nullable — an active consent has not been revoked.
    assert cols["revoked_at"]["nullable"] is True


def test_downgrade_then_reupgrade_roundtrip(pg_engine: sa.Engine, cfg: Config):
    command.upgrade(cfg, CONSENT_HEAD)
    command.downgrade(cfg, PRE_CONSENT_REV)
    assert not sa.inspect(pg_engine).has_table(TABLE), "table survived downgrade"

    command.upgrade(cfg, CONSENT_HEAD)
    assert sa.inspect(pg_engine).has_table(TABLE)
