"""Integration tests for the k2_s1_widen_evidence_level migration.

Run against a REAL PostgreSQL instance — VARCHAR length enforcement, and
therefore this migration's entire reason for existing, is invisible on
SQLite (see the migration's own docstring and
tests/integration/test_medication_k2_slice1_postgres.py's
TestPostgresSchemaDefectEvidenceLevelColumnWidth for the original
reproduction). Self-contained — matches this test package's existing
one-file-per-migration convention (test_medication_k1_knowledge_migration.py).

Usage (local):
    POSTGRES_TEST_URL="postgresql+psycopg://mcp:mcp@localhost:5432/mcp_test" \
    pytest tests/integration/test_medication_k2_widen_evidence_level_migration.py -v -m integration

All rows synthetic test fixtures — never real clinical content.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")
PRE_WIDEN_REVISION = "k1_a1b_artifact_hash"
WIDEN_REVISION = "k2_s1_widen_evidence_level"
SHARED_BASELINE = "k1_a1b_f2_specialty_seed"  # what every other integration test file leaves mcp_test at

pytestmark = pytest.mark.integration

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)

# The two ADR-15 §D canonical values that motivated this migration.
_LONG_VALUES = ("clinical_guideline", "peer_reviewed_literature")


def _require_postgres() -> None:
    if not POSTGRES_TEST_URL:
        pytest.skip(
            "POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests. "
            "Set POSTGRES_TEST_URL to a throw-away Postgres database to run these tests."
        )


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


@pytest.fixture(scope="module", autouse=True)
def _restore_shared_baseline(pg_engine: sa.Engine, cfg: Config) -> Generator[None, None, None]:
    """Every other integration test file leaves the shared mcp_test DB at
    SHARED_BASELINE between runs — restore it at the end of this module
    too, regardless of which revision individual tests below leave it at."""
    yield
    command.upgrade(cfg, "head")  # ensure a clean, known state before downgrading
    command.downgrade(cfg, SHARED_BASELINE)


def _column_max_length(pg_engine: sa.Engine, table: str, column: str) -> int | None:
    with pg_engine.connect() as conn:
        return conn.execute(
            sa.text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).scalar()


def _seed_ingredient(conn: sa.Connection) -> str:
    class_id, ingredient_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    conn.execute(
        sa.text(
            "INSERT INTO drug_classes (id, name, required_specialties, created_at, updated_at) "
            "VALUES (:id, :name, cast(:specialties as json), :now, :now)"
        ),
        {"id": class_id, "name": f"class-{class_id[:8]}", "specialties": "[]", "now": now},
    )
    conn.execute(
        sa.text(
            "INSERT INTO drug_ingredients (id, name_inn, drug_class_id, created_at, updated_at) "
            "VALUES (:id, :name, :class_id, :now, :now)"
        ),
        {"id": ingredient_id, "name": f"ingredient-{ingredient_id[:8]}", "class_id": class_id, "now": now},
    )
    conn.commit()
    return ingredient_id


def _insert_side_effect(
    conn: sa.Connection, ingredient_id: str, evidence_level: str, *, concept_code: str = "nausea"
) -> str:
    # concept_code must be distinct per row inserted for the SAME ingredient
    # while status='approved' — it's part of the partial unique index
    # (uq_drug_side_effects_approved_key on (drug_ingredient_id,
    # concept_code) WHERE status='approved'); reusing 'nausea' across two
    # inserts for one ingredient raises a real UniqueViolation, not a bug
    # in the migration under test.
    row_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    conn.execute(
        sa.text(
            "INSERT INTO drug_side_effects "
            "(id, drug_ingredient_id, concept_code, label, frequency, action_level, description, "
            "source, version, evidence_level, reviewed_by, last_reviewed_at, status, "
            "status_changed_at, status_changed_by, authored_by, created_at, updated_at) "
            "VALUES (:id, :ingredient_id, :concept_code, 'Nausea', 'common', 'self_monitor', 'desc', "
            "'src', '1.0', :evidence_level, 'reviewer', :now, 'approved', :now, 'reviewer', "
            "'author', :now, :now)"
        ),
        {
            "id": row_id,
            "ingredient_id": ingredient_id,
            "concept_code": concept_code,
            "evidence_level": evidence_level,
            "now": now,
        },
    )
    conn.commit()
    return row_id


def _reset_to_head(cfg: Config) -> None:
    """Every test in this module starts from a deterministic, known
    position, regardless of what a previous test (or a manual `alembic`
    invocation earlier in the same session) left the shared mcp_test DB at.
    `command.upgrade`/`command.downgrade` only move in one direction each
    and raise `CommandError` if asked to move the "wrong" way from the
    current position — always normalizing to head first, then moving to
    wherever an individual test actually needs, avoids that entirely."""
    command.upgrade(cfg, "head")


class TestUpgradeWidensColumn:
    def test_column_is_varchar_16_before_this_migration(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, PRE_WIDEN_REVISION)
        for table in _KNOWLEDGE_TABLES:
            assert _column_max_length(pg_engine, table, "evidence_level") == 16, table

    def test_upgrade_widens_all_5_tables_to_varchar_32(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, PRE_WIDEN_REVISION)
        command.upgrade(cfg, WIDEN_REVISION)
        for table in _KNOWLEDGE_TABLES:
            assert _column_max_length(pg_engine, table, "evidence_level") == 32, table


class TestLongCanonicalValuesRoundTrip:
    def test_both_long_adr15_values_persist_and_round_trip(self, pg_engine, cfg):
        _reset_to_head(cfg)
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            row_ids = {}
            for i, value in enumerate(_LONG_VALUES):
                assert len(value) > 16, f"{value!r} must exceed the old 16-char limit to be a real test"
                row_ids[value] = _insert_side_effect(
                    conn, ingredient_id, value, concept_code=f"concept-{i}"
                )

            for value, row_id in row_ids.items():
                round_tripped = conn.execute(
                    sa.text("SELECT evidence_level FROM drug_side_effects WHERE id = :id"),
                    {"id": row_id},
                ).scalar()
                assert round_tripped == value, f"expected exact round-trip of {value!r}, got {round_tripped!r}"

            for row_id in row_ids.values():
                conn.execute(sa.text("DELETE FROM drug_side_effects WHERE id = :id"), {"id": row_id})
            conn.execute(
                sa.text("DELETE FROM drug_ingredients WHERE id = :id"), {"id": ingredient_id}
            )
            conn.commit()


class TestDowngradeSafety:
    def test_downgrade_refuses_when_a_long_value_exists(self, pg_engine, cfg):
        _reset_to_head(cfg)
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            row_id = _insert_side_effect(conn, ingredient_id, "peer_reviewed_literature")

        with pytest.raises(RuntimeError, match="Refusing to downgrade"):
            command.downgrade(cfg, PRE_WIDEN_REVISION)

        # DB must still be at the widen revision — the refusal must be
        # all-or-nothing, not a partial downgrade of some tables.
        with pg_engine.connect() as conn:
            current = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert current == WIDEN_REVISION
        for table in _KNOWLEDGE_TABLES:
            assert _column_max_length(pg_engine, table, "evidence_level") == 32, table

        # Data must be untouched by the refused attempt.
        with pg_engine.connect() as conn:
            still_there = conn.execute(
                sa.text("SELECT evidence_level FROM drug_side_effects WHERE id = :id"), {"id": row_id}
            ).scalar()
            assert still_there == "peer_reviewed_literature"
            conn.execute(sa.text("DELETE FROM drug_side_effects WHERE id = :id"), {"id": row_id})
            conn.execute(sa.text("DELETE FROM drug_ingredients WHERE id = :id"), {"id": ingredient_id})
            conn.commit()

    def test_downgrade_succeeds_when_no_long_values_exist(self, pg_engine, cfg):
        command.upgrade(cfg, WIDEN_REVISION)
        command.downgrade(cfg, PRE_WIDEN_REVISION)
        for table in _KNOWLEDGE_TABLES:
            assert _column_max_length(pg_engine, table, "evidence_level") == 16, table
        command.upgrade(cfg, WIDEN_REVISION)  # restore for any later test in this module


class TestApprovalPathRegressionOnPostgres:
    """Proves the existing K1.5 write path (repo.create_draft ->
    submit_for_review -> approve_row) — not a raw INSERT — accepts both
    long ADR-15 §D values end-to-end on real Postgres, post-migration."""

    def test_approve_row_accepts_both_long_evidence_level_values(self, pg_engine, cfg):
        command.upgrade(cfg, WIDEN_REVISION)

        os.environ["MCP_DATABASE_URL"] = pg_engine.url.render_as_string(hide_password=False)
        from app.core.config import get_settings

        get_settings.cache_clear()

        from app.models.drug_knowledge_content import DrugSideEffect
        from app.models.drug_knowledge_core import DrugClass, DrugIngredient
        from app.services import knowledge_repository as repo
        from sqlalchemy.orm import sessionmaker

        session_factory = sessionmaker(bind=pg_engine, autoflush=False, autocommit=False, future=True)
        db = session_factory()
        try:
            suffix = uuid.uuid4().hex[:8]
            drug_class = DrugClass(name=f"approve-test-class-{suffix}", required_specialties=[])
            db.add(drug_class)
            db.flush()
            ingredient = DrugIngredient(
                name_inn=f"approve-test-ingredient-{suffix}", drug_class_id=drug_class.id
            )
            db.add(ingredient)
            db.commit()

            for i, value in enumerate(_LONG_VALUES):
                fields = dict(
                    drug_ingredient_id=ingredient.id,
                    concept_code=f"concept-{i}",
                    label="Test label",
                    frequency="common",
                    action_level="self_monitor",
                    description="synthetic test description",
                    source="Synthetic Test Source",
                    version="1.0",
                    evidence_level=value,
                    reviewed_by="reviewer-1",
                    last_reviewed_at=dt.datetime.now(dt.UTC),
                )
                row = repo.create_draft(db, DrugSideEffect, authored_by="author-1", **fields)
                repo.submit_for_review(db, row, actor_user_id="author-1")
                approved = repo.approve_row(
                    db, row, actor_user_id="reviewer-1", actor_role="internal_admin"
                )
                assert approved.status == "approved"
                assert approved.evidence_level == value

            db.query(DrugSideEffect).filter(DrugSideEffect.drug_ingredient_id == ingredient.id).delete()
            db.query(DrugIngredient).filter(DrugIngredient.id == ingredient.id).delete()
            db.query(DrugClass).filter(DrugClass.id == drug_class.id).delete()
            db.commit()
        finally:
            db.close()
