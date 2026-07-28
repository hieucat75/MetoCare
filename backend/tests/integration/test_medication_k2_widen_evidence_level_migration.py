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
def _restore_head(pg_engine: sa.Engine, cfg: Config) -> Generator[None, None, None]:
    """Leaves the shared mcp_test database at head after this module's
    tests run — regardless of which revision an individual test below
    exercised or left it at, including after a test failure (pytest always
    runs a module-scoped fixture's finalizer once the last test using it
    completes, pass or fail).

    Historically this restored to a fixed "SHARED_BASELINE" revision
    (k1_a1b_f2_specialty_seed) instead, on the premise that every
    integration test file agreed to leave mcp_test there between runs.
    That premise doesn't need to hold for correctness: every other
    integration test file's own `migrated_schema`-style fixture
    unconditionally re-normalizes to head at ITS OWN start (see e.g.
    test_medication_k1_5_approval_workflow_postgres.py's
    `command.upgrade(cfg, "head")`), so landing at head here is a
    consistent, safe resting point too — a pure upgrade from wherever a
    test left the DB, with no downgrade (and therefore none of that
    downgrade's own data-dependent refusal guards) required to get there.
    """
    yield
    command.upgrade(cfg, "head")


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


def _cleanup_seeded_ingredient(conn: sa.Connection, ingredient_id: str) -> None:
    """FK-safe, ID-scoped teardown for everything `_seed_ingredient` (and
    any drug_side_effects rows created against it) can have left behind.
    `_seed_ingredient` creates both a drug_classes row and a
    drug_ingredients row referencing it — earlier versions of this file's
    tests only ever deleted the ingredient, silently leaking a
    `class-<id>` row on every run. Looks up the class id via the
    ingredient's own FK rather than requiring callers to track it
    separately."""
    class_id = conn.execute(
        sa.text("SELECT drug_class_id FROM drug_ingredients WHERE id = :id"),
        {"id": ingredient_id},
    ).scalar()
    conn.execute(
        sa.text("DELETE FROM drug_side_effects WHERE drug_ingredient_id = :id"),
        {"id": ingredient_id},
    )
    conn.execute(sa.text("DELETE FROM drug_ingredients WHERE id = :id"), {"id": ingredient_id})
    if class_id is not None:
        conn.execute(sa.text("DELETE FROM drug_classes WHERE id = :id"), {"id": class_id})
    conn.commit()


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
            try:
                row_ids = {}
                for i, value in enumerate(_LONG_VALUES):
                    assert len(value) > 16, (
                        f"{value!r} must exceed the old 16-char limit to be a real test"
                    )
                    row_ids[value] = _insert_side_effect(
                        conn, ingredient_id, value, concept_code=f"concept-{i}"
                    )

                for value, row_id in row_ids.items():
                    round_tripped = conn.execute(
                        sa.text("SELECT evidence_level FROM drug_side_effects WHERE id = :id"),
                        {"id": row_id},
                    ).scalar()
                    assert round_tripped == value, (
                        f"expected exact round-trip of {value!r}, got {round_tripped!r}"
                    )
            finally:
                # Runs even if an assertion above failed — deletes both
                # the drug_side_effects rows AND the drug_classes row
                # _seed_ingredient created (previously leaked every run).
                _cleanup_seeded_ingredient(conn, ingredient_id)


class TestDowngradeSafety:
    """Empirically verified (2026-07-27, reproduced live against both
    dialects while fixing this suite): on PostgreSQL, Alembic wraps an
    ENTIRE multi-step `command.downgrade()`/`command.upgrade()` call in
    ONE transaction — `alembic/env.py`'s `context.begin_transaction()`
    wraps the whole `run_migrations()` call and `transaction_per_migration`
    is never set, confirmed live by Alembic's own "Will assume
    transactional DDL" log line on Postgres. When any migration in the
    requested chain raises, every step attempted in that same command
    call — not just the one whose guard fired — rolls back, leaving the
    database byte-for-byte identical to whatever it was immediately
    BEFORE the call. It is never left at "the revision just before the
    one that failed."

    This is dialect-specific, not a general Alembic guarantee: on SQLite,
    Alembic logs "Will assume non-transactional DDL" and commits each
    migration step's DDL independently, so an equivalent refusal partway
    through a chain WOULD leave every prior step committed and land the
    database at the revision immediately preceding the one that raised
    (reproduced live against a throwaway SQLite file while diagnosing
    this). This module's own tests never exercise SQLite — gated on
    `POSTGRES_TEST_URL` via `_require_postgres` — so this divergence
    doesn't affect them, but it is exactly why the original version of
    the test below asserted "must still be at WIDEN_REVISION": that was
    only ever true by coincidence, because WIDEN_REVISION was itself head
    at the time this test was written, making "immediately before the
    call" and "one step above the failure" the same value. Slice 0
    stacking 4 more revisions on top broke that coincidence, not this
    migration's actual behavior — so the assertion below captures "before"
    dynamically instead of hardcoding a revision name that stops being
    the right answer every time another migration lands on top.
    """

    def test_downgrade_refuses_when_a_long_value_exists(self, pg_engine, cfg):
        _reset_to_head(cfg)
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
        try:
            with pg_engine.connect() as conn:
                row_id = _insert_side_effect(conn, ingredient_id, "peer_reviewed_literature")

            with pg_engine.connect() as conn:
                before = conn.execute(
                    sa.text("SELECT version_num FROM alembic_version")
                ).scalar()

            with pytest.raises(RuntimeError, match="Refusing to downgrade"):
                command.downgrade(cfg, PRE_WIDEN_REVISION)

            # The refusal must be all-or-nothing for the ENTIRE requested
            # multi-step chain: on Postgres this means the revision is
            # left byte-for-byte where it started — not "at the widen
            # revision" as a hardcoded assumption, but at whatever `before`
            # actually was, dynamically captured immediately above.
            with pg_engine.connect() as conn:
                after = conn.execute(
                    sa.text("SELECT version_num FROM alembic_version")
                ).scalar()
            assert after == before, (
                "a refused downgrade must never move the revision at all on "
                f"Postgres (single-transaction command) — was {before!r}, now {after!r}"
            )
            for table in _KNOWLEDGE_TABLES:
                assert _column_max_length(pg_engine, table, "evidence_level") == 32, table

            # No partial migration state: schema/revision must still be
            # mutually consistent enough that a normal upgrade to head
            # succeeds without error (the refusal never actually moved us
            # off head, so this is a no-op upgrade — but it must not raise).
            command.upgrade(cfg, "head")
            with pg_engine.connect() as conn:
                still_at = conn.execute(
                    sa.text("SELECT version_num FROM alembic_version")
                ).scalar()
            assert still_at == before

            # Data must be untouched — byte-for-byte, not just "truthy
            # equal" — and no silent narrowing occurred (e.g. a truncated
            # prefix that happened to compare equal to a shorter string).
            with pg_engine.connect() as conn:
                still_there = conn.execute(
                    sa.text("SELECT evidence_level FROM drug_side_effects WHERE id = :id"),
                    {"id": row_id},
                ).scalar()
            assert still_there == "peer_reviewed_literature"
            assert len(still_there) == len("peer_reviewed_literature") == 24, (
                "value length changed — silent narrowing must never happen even "
                "on a refused downgrade"
            )

            # Remediate the blocking data, then prove the SAME downgrade
            # this test just refused now genuinely succeeds once the data
            # condition that blocked it is gone: the refusal is
            # data-conditional, never a permanent wedge.
            with pg_engine.connect() as conn:
                conn.execute(
                    sa.text("DELETE FROM drug_side_effects WHERE id = :id"), {"id": row_id}
                )
                conn.commit()
            command.downgrade(cfg, PRE_WIDEN_REVISION)
            for table in _KNOWLEDGE_TABLES:
                assert _column_max_length(pg_engine, table, "evidence_level") == 16, (
                    f"{table}: downgrade should have succeeded once the blocking "
                    "row was remediated"
                )
        finally:
            # Runs even if an assertion above failed. Safe regardless of
            # which schema position the test is currently at — none of
            # these tables/columns are touched by the widen migration.
            with pg_engine.connect() as conn:
                _cleanup_seeded_ingredient(conn, ingredient_id)
            command.upgrade(cfg, "head")

    def test_downgrade_succeeds_when_no_long_values_exist(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, PRE_WIDEN_REVISION)
        for table in _KNOWLEDGE_TABLES:
            assert _column_max_length(pg_engine, table, "evidence_level") == 16, table
        command.upgrade(cfg, "head")


class TestApprovalPathRegressionOnPostgres:
    """Proves the existing K1.5 write path (repo.create_draft ->
    submit_for_review -> approve_row) — not a raw INSERT — accepts both
    long ADR-15 §D values end-to-end on real Postgres, post-migration."""

    def test_approve_row_accepts_both_long_evidence_level_values(self, pg_engine, cfg):
        # Deterministic starting position regardless of what a previous
        # test in this module left the DB at (was `command.upgrade(cfg,
        # WIDEN_REVISION)`, which silently no-ops once the DB is already
        # past that revision — true for every run since Slice 0 stacked
        # more revisions on top of it).
        _reset_to_head(cfg)

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

            try:
                for i, value in enumerate(_LONG_VALUES):
                    # reviewed_by deliberately omitted (fix round 1,
                    # 2026-07-28, Codex Round 1 finding #6): build_draft
                    # now rejects an explicit reviewed_by= kwarg — it is
                    # bound to the approving actor inside approve_row.
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
                        last_reviewed_at=dt.datetime.now(dt.UTC),
                    )
                    row = repo.create_draft(db, DrugSideEffect, authored_by="author-1", **fields)
                    repo.submit_for_review(db, row, actor_user_id="author-1")
                    approved = repo.approve_row(
                        db, row, actor_user_id="reviewer-1", actor_role="internal_admin"
                    )
                    assert approved.status == "approved"
                    assert approved.evidence_level == value
            finally:
                # Test-isolation fix (2026-07-27): submit_for_review/approve_row
                # above each append a row to knowledge_lifecycle_transitions
                # (Slice 0, real append-only history — its migration's
                # downgrade() refuses to run while any row exists). Deleting
                # it here, scoped strictly to this test's own ingredient.id
                # (never table-wide), and inside this finally (so it runs even
                # if an assertion above failed) — same pattern as the K1.5
                # approval-workflow test's `ingredient` fixture teardown —
                # keeps the shared disposable mcp_test database clean enough
                # for a subsequent downgrade past k2_s0_lifecycle_transitions
                # to succeed.
                # k2_s0_integrity_guards' append-only trigger (fix round 1,
                # 2026-07-28) blocks this DELETE outright — temporarily
                # disabled for exactly this test-only cleanup statement,
                # same escape-hatch pattern as the K1.5/K1.6 integration
                # files.
                db.execute(sa.text("ALTER TABLE knowledge_lifecycle_transitions DISABLE TRIGGER trg_knowledge_lifecycle_transitions_append_only"))
                try:
                    db.execute(
                        sa.text(
                            "DELETE FROM knowledge_lifecycle_transitions "
                            "WHERE knowledge_table = 'drug_side_effects' "
                            "AND knowledge_row_id IN "
                            "(SELECT id FROM drug_side_effects WHERE drug_ingredient_id = :ingredient_id)"
                        ),
                        {"ingredient_id": ingredient.id},
                    )
                finally:
                    db.execute(sa.text("ALTER TABLE knowledge_lifecycle_transitions ENABLE TRIGGER trg_knowledge_lifecycle_transitions_append_only"))
                db.query(DrugSideEffect).filter(DrugSideEffect.drug_ingredient_id == ingredient.id).delete()
                db.query(DrugIngredient).filter(DrugIngredient.id == ingredient.id).delete()
                db.query(DrugClass).filter(DrugClass.id == drug_class.id).delete()
                db.commit()
        finally:
            db.close()
