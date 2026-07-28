"""SQLite migration tests for the K2 Slice 0 chain:

    k2_s1_widen_evidence_level
        -> k2_s0_knowledge_origin        (add `origin` to the 5 knowledge tables)
        -> k2_s0_ai_generation_history   (create knowledge_ai_generations)
        -> k2_s0_lifecycle_transitions   (create knowledge_lifecycle_transitions)
        -> k2_s0_add_rejected_status     (widen status CHECK to include 'rejected'; head)

Not integration-marked, no POSTGRES_TEST_URL — every test builds its own
throwaway SQLite database FILE (never `:memory:`, never the shared
session-scoped file tests/conftest.py wires up for the rest of the unit
suite) via `tempfile.TemporaryDirectory`, so each test runs the full
migration chain from a clean base rather than against an
already-fully-migrated app schema.

Dialect divergence (empirically observed 2026-07-27, see
tests/integration/test_medication_k2_widen_evidence_level_migration.py's
`TestDowngradeSafety` docstring for the Postgres side of this):

Alembic logs "Will assume transactional DDL" on PostgreSQL and wraps an
entire multi-step `command.downgrade()`/`command.upgrade()` call in ONE
transaction — a refusal anywhere in a multi-step chain rolls the WHOLE
chain back to the revision the DB started at, leaving it byte-for-byte
unchanged.

On SQLite, Alembic instead logs "Will assume non-transactional DDL" and
commits each migration step's DDL independently (SQLite's
`batch_alter_table` table-rebuild dance and its general lack of
transactional `ALTER TABLE`/`DROP CONSTRAINT` support are exactly why
these migrations use `op.batch_alter_table` in the first place). A
refusal partway through a multi-step downgrade chain therefore leaves
every step attempted BEFORE the failing one already committed — the
database lands at the revision immediately preceding the one whose
`downgrade()` raised, NOT at the revision it started the call from.
`TestSqliteMultiStepDowngradeRefusalLandingBehavior` below demonstrates
this directly: downgrading from head with a blocking row present in
`knowledge_ai_generations`* lands the SQLite DB at
`k2_s0_lifecycle_transitions` (the revision immediately above the one
whose downgrade refused), never at head — the opposite of what the
equivalent Postgres scenario proves in the sibling integration test file.
Do not port the Postgres file's "unchanged from before" assertion here —
it is not true on this dialect.

*Chosen because it is the first migration hit walking down from head
(k2_s0_add_rejected_status -> k2_s0_lifecycle_transitions ->
k2_s0_ai_generation_history is where the refusal fires), giving the
clearest 2-step-committed-then-refused demonstration.

Synthetic fixtures only — never real clinical content.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import tempfile
import uuid
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

# Revision markers, in chain order (see module docstring).
SPECIALTY_SEED_REV = "k1_a1b_f2_specialty_seed"
PRE_ORIGIN_REV = "k2_s1_widen_evidence_level"
ORIGIN_REV = "k2_s0_knowledge_origin"
AI_GEN_REV = "k2_s0_ai_generation_history"
LIFECYCLE_REV = "k2_s0_lifecycle_transitions"
REJECTED_REV = "k2_s0_add_rejected_status"

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)

_ORIGIN_VALUES = ("source_extracted", "rule_derived", "ai_synthesized", "human_authored")
_ORIGIN_DEFAULT = "human_authored"


def _make_alembic_config(db_url: str) -> Config:
    os.environ["MCP_DATABASE_URL"] = db_url
    from app.core.config import get_settings

    get_settings.cache_clear()

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    return cfg


@pytest.fixture()
def sqlite_db() -> Generator[tuple[sa.Engine, Config], None, None]:
    """Fresh temp-file SQLite database per test, cleaned up (dir + file) on
    exit regardless of pass/fail — `TemporaryDirectory` as a context
    manager, per this file's own docstring convention."""
    # This process's other tests (tests/conftest.py) rely on a fixed
    # MCP_DATABASE_URL pointing at the shared session-scoped SQLite file —
    # `_make_alembic_config` mutates that env var (and the get_settings
    # LRU cache) process-wide with no built-in restore. Left unrestored,
    # every test collected after this one in the same `pytest -m "not
    # integration"` run would silently pick up this test's already-deleted
    # temp-file URL via `get_settings()`, breaking unrelated tests whose
    # fixtures depend on app settings (empirically reproduced 2026-07-27:
    # tests/test_observability.py::test_access_log_is_json_with_no_phi
    # failed only when this file ran earlier in the same suite, passed in
    # isolation). Capture and restore both on the way out, always.
    original_db_url = os.environ.get("MCP_DATABASE_URL")
    logging_snapshot = _snapshot_logging_state()
    with tempfile.TemporaryDirectory(prefix="k2_s0_sqlite_migration_test_") as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db_url = f"sqlite:///{db_path}"
        cfg = _make_alembic_config(db_url)
        engine = sa.create_engine(db_url, echo=False, future=True)
        with engine.connect() as conn:
            assert conn.dialect.name == "sqlite"
        try:
            yield engine, cfg
        finally:
            engine.dispose()
            from app.core.config import get_settings

            if original_db_url is None:
                os.environ.pop("MCP_DATABASE_URL", None)
            else:
                os.environ["MCP_DATABASE_URL"] = original_db_url
            get_settings.cache_clear()
            _restore_logging_state(logging_snapshot)


def _snapshot_logging_state() -> dict:
    """Root-cause workaround for a real, pre-existing landmine in
    alembic/env.py: it calls `logging.config.fileConfig(config.config_file_name)`
    on every `command.upgrade`/`downgrade`. stdlib `fileConfig()` defaults to
    `disable_existing_loggers=True` (sets `.disabled = True` on every
    pre-existing Logger not named in alembic.ini's `[loggers]` section —
    e.g. this app's own `mcp.access` logger) AND reconfigures the root
    logger's level/handlers per alembic.ini's `[logger_root]` section
    (`level = WARNING` here) — which alone silently suppresses this app's
    INFO-level access-log records site-wide for the rest of the process,
    even after `.disabled` is corrected, since the effective-level check
    happens before any handler (including one a test attaches directly to
    `mcp.access`) ever sees the record. Reproduced empirically (2026-07-27):
    tests/test_observability.py::test_access_log_is_json_with_no_phi fails
    with an empty log buffer whenever collected after this file runs in the
    same `pytest -m "not integration"` session, passes in isolation. Out of
    scope to fix alembic/env.py itself (test-file-only change per this
    task's scope) — no app code anywhere intentionally disables a logger or
    depends on WARNING-level root filtering (verified via grep), so
    snapshotting every registered logger's (level, disabled) plus root's
    (level, handlers, propagate) before the first Alembic call in a test
    and restoring exactly afterward fully undoes the side effect without
    touching production code."""
    snapshot = {
        None: (logging.root.level, list(logging.root.handlers), logging.root.propagate),
    }
    for name, logger in logging.Logger.manager.loggerDict.items():
        if isinstance(logger, logging.Logger):
            snapshot[name] = (logger.level, logger.disabled)
    return snapshot


def _restore_logging_state(snapshot: dict) -> None:
    root_level, root_handlers, root_propagate = snapshot[None]
    logging.root.setLevel(root_level)
    logging.root.handlers[:] = root_handlers
    logging.root.propagate = root_propagate
    for name, logger in logging.Logger.manager.loggerDict.items():
        if not isinstance(logger, logging.Logger):
            continue
        if name in snapshot:
            level, disabled = snapshot[name]
            logger.setLevel(level)
            logger.disabled = disabled
        else:
            # A logger created during this test's Alembic calls (e.g.
            # alembic.*, sqlalchemy.engine) — didn't exist before, so
            # there's nothing of this app's to restore; just ensure it
            # isn't left disabled for any later test that happens to touch
            # the same logger name.
            logger.disabled = False


def _current_revision(engine: sa.Engine) -> str | None:
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()


# --------------------------------------------------------------------- #
# Generic introspection helpers (SQLite has no information_schema)
# --------------------------------------------------------------------- #


def _table_exists(engine: sa.Engine, table: str) -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(
                sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table},
            ).first()
        )


def _column_info(engine: sa.Engine, table: str, column: str) -> dict | None:
    with engine.connect() as conn:
        rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).mappings().all()
    for row in rows:
        if row["name"] == column:
            return dict(row)
    return None


def _index_names(engine: sa.Engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t"),
            {"t": table},
        ).scalars().all()
    return set(rows)


def _fk_list(engine: sa.Engine, table: str) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(sa.text(f"PRAGMA foreign_key_list({table})")).mappings().all()]


# --------------------------------------------------------------------- #
# Fixture seeding helpers
# --------------------------------------------------------------------- #


def _seed_ingredient(conn: sa.Connection) -> str:
    class_id, ingredient_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    conn.execute(
        sa.text(
            "INSERT INTO drug_classes (id, name, required_specialties, created_at, updated_at) "
            "VALUES (:id, :name, :specialties, :now, :now)"
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


def _insert_side_effect_draft(
    conn: sa.Connection,
    ingredient_id: str,
    *,
    concept_code: str,
    status: str = "draft",
    origin: str | None = None,
) -> str:
    """Raw INSERT into drug_side_effects, tolerant of which columns exist
    at the current revision — same idiom as the Postgres sibling file's
    helper of the same name."""
    row_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    columns: dict[str, object] = {
        "id": row_id,
        "drug_ingredient_id": ingredient_id,
        "concept_code": concept_code,
        "label": "Nausea",
        "frequency": "common",
        "action_level": "self_monitor",
        "description": "synthetic test description",
        "status": status,
        "status_changed_at": now,
        "status_changed_by": "tester",
        "authored_by": "tester",
        "created_at": now,
        "updated_at": now,
    }
    if origin is not None:
        columns["origin"] = origin
    if status == "approved":
        columns["reviewed_by"] = "reviewer-tester"
        columns["evidence_level"] = "expert_opinion"
        columns["source"] = "Synthetic Test Source"
        columns["version"] = "1.0"
        columns["last_reviewed_at"] = now
    col_names = ", ".join(columns)
    placeholders = ", ".join(f":{k}" for k in columns)
    conn.execute(
        sa.text(f"INSERT INTO drug_side_effects ({col_names}) VALUES ({placeholders})"),
        columns,
    )
    conn.commit()
    return row_id


def _insert_ai_generation(conn: sa.Connection) -> str:
    row_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    conn.execute(
        sa.text(
            "INSERT INTO knowledge_ai_generations "
            "(id, knowledge_table, target_row_id, model_provider, model_identifier, "
            "prompt_template_id, prompt_template_version, input_source_ids, input_hash, "
            "generation_status, origin, review_status, created_by, created_at, updated_at) "
            "VALUES (:id, 'drug_side_effects', NULL, 'openrouter', 'test-model', "
            "'tmpl-1', '1.0', :input_source_ids, :input_hash, "
            "'succeeded', 'ai_synthesized', 'pending', 'system:test', :now, :now)"
        ),
        {"id": row_id, "input_source_ids": "[]", "input_hash": "a" * 64, "now": now},
    )
    conn.commit()
    return row_id


def _insert_lifecycle_transition(conn: sa.Connection, ingredient_id: str) -> str:
    row_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    conn.execute(
        sa.text(
            "INSERT INTO knowledge_lifecycle_transitions "
            "(id, knowledge_table, knowledge_row_id, from_status, to_status, actor_id, "
            "actor_role, reason_code, rationale, transitioned_at, created_at, updated_at) "
            "VALUES (:id, 'drug_side_effects', :row_id, 'draft', 'clinical_review', 'tester', "
            "NULL, 'standard_transition', 'synthetic test transition', :now, :now, :now)"
        ),
        {"id": row_id, "row_id": ingredient_id, "now": now},
    )
    conn.commit()
    return row_id


# --------------------------------------------------------------------- #
# k2_s0_knowledge_origin
# --------------------------------------------------------------------- #


class TestKnowledgeOriginMigrationSQLite:
    def test_origin_column_absent_before_migration(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, PRE_ORIGIN_REV)
        for table in _KNOWLEDGE_TABLES:
            assert _column_info(engine, table, "origin") is None, table

    def test_upgrade_adds_origin_column_with_default_and_check(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, ORIGIN_REV)
        for table in _KNOWLEDGE_TABLES:
            info = _column_info(engine, table, "origin")
            assert info is not None, table
            assert info["notnull"] == 1, table
            assert info["dflt_value"] is not None and _ORIGIN_DEFAULT in info["dflt_value"], table

        # CHECK enforcement: an out-of-vocabulary origin must be rejected.
        with engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            with pytest.raises(sa.exc.IntegrityError):
                _insert_side_effect_draft(
                    conn, ingredient_id, concept_code="bad-origin", origin="not_a_real_origin"
                )

    def test_backfill_classifies_legacy_rows_as_human_authored(self, sqlite_db):
        """Seeds a row at k1_a1b_f2_specialty_seed (before artifact_hash AND
        origin exist), then upgrades through k1_a1b_artifact_hash ->
        k2_s1_widen_evidence_level -> k2_s0_knowledge_origin — the
        server_default backfill (not a separate UPDATE) must classify it
        'human_authored', surviving SQLite's batch_alter_table table-rebuild
        dance with every other column untouched."""
        engine, cfg = sqlite_db
        command.upgrade(cfg, SPECIALTY_SEED_REV)
        with engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            row_id = _insert_side_effect_draft(conn, ingredient_id, concept_code="legacy-concept")

        command.upgrade(cfg, ORIGIN_REV)

        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT origin, concept_code, label, frequency, action_level, "
                    "description, status, authored_by FROM drug_side_effects WHERE id = :id"
                ),
                {"id": row_id},
            ).mappings().first()
        assert row is not None
        assert row["origin"] == _ORIGIN_DEFAULT
        assert row["origin"] not in ("ai_synthesized", "source_extracted")
        assert row["concept_code"] == "legacy-concept"
        assert row["label"] == "Nausea"
        assert row["frequency"] == "common"
        assert row["action_level"] == "self_monitor"
        assert row["description"] == "synthetic test description"
        assert row["status"] == "draft"
        assert row["authored_by"] == "tester"

    def test_downgrade_succeeds_when_all_rows_default(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, ORIGIN_REV)
        with engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            _insert_side_effect_draft(conn, ingredient_id, concept_code="default-origin")

        command.downgrade(cfg, PRE_ORIGIN_REV)
        for table in _KNOWLEDGE_TABLES:
            assert _column_info(engine, table, "origin") is None, table

    def test_downgrade_refuses_when_row_reclassified(self, sqlite_db):
        """Single-step downgrade (ORIGIN_REV -> PRE_ORIGIN_REV directly, no
        other migration in between) — the refusal happens on the very first
        and only step attempted, so SQLite's non-transactional-per-step
        commit behavior can't leave any *earlier* step half-done here (there
        isn't one). The DB simply stays at ORIGIN_REV, same outward result
        as Postgres would show for this single-step case — the dialect
        divergence only becomes visible across a MULTI-step chain, which
        TestSqliteMultiStepDowngradeRefusalLandingBehavior demonstrates
        below."""
        engine, cfg = sqlite_db
        command.upgrade(cfg, ORIGIN_REV)
        with engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            row_id = _insert_side_effect_draft(
                conn, ingredient_id, concept_code="reclassified", origin="ai_synthesized", status="draft"
            )

        with pytest.raises(RuntimeError, match="Refusing to downgrade"):
            command.downgrade(cfg, PRE_ORIGIN_REV)

        assert _current_revision(engine) == ORIGIN_REV
        for table in _KNOWLEDGE_TABLES:
            assert _column_info(engine, table, "origin") is not None, table

        with engine.connect() as conn:
            still_there = conn.execute(
                sa.text("SELECT origin FROM drug_side_effects WHERE id = :id"), {"id": row_id}
            ).scalar()
        assert still_there == "ai_synthesized"

        # Not a permanent wedge: remediate, then the same downgrade succeeds.
        with engine.connect() as conn:
            conn.execute(sa.text("DELETE FROM drug_side_effects WHERE id = :id"), {"id": row_id})
            conn.commit()
        command.downgrade(cfg, PRE_ORIGIN_REV)
        for table in _KNOWLEDGE_TABLES:
            assert _column_info(engine, table, "origin") is None, table

        # No partial/corrupted state: a normal re-upgrade to head still works.
        command.upgrade(cfg, "head")
        assert _current_revision(engine) == REJECTED_REV


# --------------------------------------------------------------------- #
# k2_s0_ai_generation_history
# --------------------------------------------------------------------- #


class TestAIGenerationHistoryMigrationSQLite:
    def test_table_absent_before_migration(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, ORIGIN_REV)
        assert _table_exists(engine, "knowledge_ai_generations") is False

    def test_upgrade_creates_table_with_expected_columns_and_indexes(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, AI_GEN_REV)
        assert _table_exists(engine, "knowledge_ai_generations") is True

        for column in ("id", "knowledge_table", "model_provider", "model_identifier",
                       "prompt_template_id", "prompt_template_version", "input_hash",
                       "generation_status", "origin", "review_status", "created_by"):
            info = _column_info(engine, "knowledge_ai_generations", column)
            assert info is not None, column
            assert info["notnull"] == 1, column

        for column in ("target_row_id", "model_version_snapshot", "output_hash", "failure_reason",
                       "superseded_by_generation_id"):
            info = _column_info(engine, "knowledge_ai_generations", column)
            assert info is not None, column
            assert info["notnull"] == 0, column

        indexes = _index_names(engine, "knowledge_ai_generations")
        assert "ix_knowledge_ai_generations_row" in indexes
        assert "ix_knowledge_ai_generations_review_status" in indexes

    def test_check_constraints_reject_out_of_vocabulary_values(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, AI_GEN_REV)
        now = dt.datetime.now(dt.UTC)
        with engine.connect() as conn:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(
                    sa.text(
                        "INSERT INTO knowledge_ai_generations "
                        "(id, knowledge_table, model_provider, model_identifier, prompt_template_id, "
                        "prompt_template_version, input_source_ids, input_hash, generation_status, "
                        "origin, review_status, created_by, created_at, updated_at) "
                        "VALUES (:id, 'not_a_real_table', 'openrouter', 'm', 't', '1', '[]', "
                        "'h', 'succeeded', 'ai_synthesized', 'pending', 'system:test', :now, :now)"
                    ),
                    {"id": str(uuid.uuid4()), "now": now},
                )

    def test_self_referential_fk_declared(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, AI_GEN_REV)
        fks = _fk_list(engine, "knowledge_ai_generations")
        matching = [
            fk for fk in fks
            if fk["table"] == "knowledge_ai_generations" and fk["from"] == "superseded_by_generation_id"
        ]
        assert len(matching) == 1, fks
        assert matching[0]["to"] == "id"
        assert matching[0]["on_delete"] == "RESTRICT"

    def test_downgrade_succeeds_when_empty(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, AI_GEN_REV)
        command.downgrade(cfg, ORIGIN_REV)
        assert _table_exists(engine, "knowledge_ai_generations") is False

    def test_downgrade_refuses_when_nonempty(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, AI_GEN_REV)
        with engine.connect() as conn:
            row_id = _insert_ai_generation(conn)

        with pytest.raises(RuntimeError, match="Refusing to downgrade"):
            command.downgrade(cfg, ORIGIN_REV)
        assert _current_revision(engine) == AI_GEN_REV
        assert _table_exists(engine, "knowledge_ai_generations") is True

        with engine.connect() as conn:
            conn.execute(sa.text("DELETE FROM knowledge_ai_generations WHERE id = :id"), {"id": row_id})
            conn.commit()
        command.downgrade(cfg, ORIGIN_REV)
        assert _table_exists(engine, "knowledge_ai_generations") is False


# --------------------------------------------------------------------- #
# k2_s0_lifecycle_transitions
# --------------------------------------------------------------------- #


class TestLifecycleTransitionsMigrationSQLite:
    def test_table_absent_before_migration(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, AI_GEN_REV)
        assert _table_exists(engine, "knowledge_lifecycle_transitions") is False

    def test_upgrade_creates_table_with_expected_columns_and_index(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, LIFECYCLE_REV)
        assert _table_exists(engine, "knowledge_lifecycle_transitions") is True

        for column in ("id", "knowledge_table", "knowledge_row_id", "from_status", "to_status",
                       "actor_id", "reason_code", "rationale", "transitioned_at"):
            info = _column_info(engine, "knowledge_lifecycle_transitions", column)
            assert info is not None, column
            assert info["notnull"] == 1, column

        info = _column_info(engine, "knowledge_lifecycle_transitions", "actor_role")
        assert info is not None
        assert info["notnull"] == 0

        indexes = _index_names(engine, "knowledge_lifecycle_transitions")
        assert "ix_knowledge_lifecycle_transitions_row" in indexes

    def test_check_constraints_reject_out_of_vocabulary_status(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, LIFECYCLE_REV)
        now = dt.datetime.now(dt.UTC)
        with engine.connect() as conn:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(
                    sa.text(
                        "INSERT INTO knowledge_lifecycle_transitions "
                        "(id, knowledge_table, knowledge_row_id, from_status, to_status, actor_id, "
                        "reason_code, rationale, transitioned_at, created_at, updated_at) "
                        "VALUES (:id, 'drug_side_effects', :row_id, 'draft', 'not_a_real_status', "
                        "'tester', 'standard_transition', 'r', :now, :now, :now)"
                    ),
                    {"id": str(uuid.uuid4()), "row_id": str(uuid.uuid4()), "now": now},
                )

    def test_downgrade_succeeds_when_empty(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, LIFECYCLE_REV)
        command.downgrade(cfg, AI_GEN_REV)
        assert _table_exists(engine, "knowledge_lifecycle_transitions") is False

    def test_downgrade_refuses_when_nonempty(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, LIFECYCLE_REV)
        with engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            transition_id = _insert_lifecycle_transition(conn, ingredient_id)

        with pytest.raises(RuntimeError, match="Refusing to downgrade"):
            command.downgrade(cfg, AI_GEN_REV)
        assert _current_revision(engine) == LIFECYCLE_REV
        assert _table_exists(engine, "knowledge_lifecycle_transitions") is True

        with engine.connect() as conn:
            conn.execute(
                sa.text("DELETE FROM knowledge_lifecycle_transitions WHERE id = :id"),
                {"id": transition_id},
            )
            conn.commit()
        command.downgrade(cfg, AI_GEN_REV)
        assert _table_exists(engine, "knowledge_lifecycle_transitions") is False


# --------------------------------------------------------------------- #
# k2_s0_add_rejected_status
# --------------------------------------------------------------------- #


class TestAddRejectedStatusMigrationSQLite:
    def test_rejected_status_rejected_by_check_before_migration(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, LIFECYCLE_REV)
        with engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            with pytest.raises(sa.exc.IntegrityError):
                _insert_side_effect_draft(
                    conn, ingredient_id, concept_code="pre-migration-rejected", status="rejected"
                )

    def test_upgrade_allows_rejected_status(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, REJECTED_REV)
        with engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            row_id = _insert_side_effect_draft(
                conn, ingredient_id, concept_code="post-migration-rejected", status="rejected"
            )
        with engine.connect() as conn:
            status = conn.execute(
                sa.text("SELECT status FROM drug_side_effects WHERE id = :id"), {"id": row_id}
            ).scalar()
        assert status == "rejected"

    def test_downgrade_succeeds_when_no_rejected_rows(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, REJECTED_REV)
        with engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            _insert_side_effect_draft(conn, ingredient_id, concept_code="approved-status-ok", status="approved")

        command.downgrade(cfg, LIFECYCLE_REV)
        with engine.connect() as conn:
            with pytest.raises(sa.exc.IntegrityError):
                _insert_side_effect_draft(
                    conn, ingredient_id, concept_code="rejected-after-downgrade", status="rejected"
                )

    def test_downgrade_refuses_when_rejected_row_exists(self, sqlite_db):
        engine, cfg = sqlite_db
        command.upgrade(cfg, REJECTED_REV)
        with engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
            row_id = _insert_side_effect_draft(
                conn, ingredient_id, concept_code="blocking-rejected", status="rejected"
            )

        with pytest.raises(RuntimeError, match="Refusing to downgrade"):
            command.downgrade(cfg, LIFECYCLE_REV)
        assert _current_revision(engine) == REJECTED_REV

        with engine.connect() as conn:
            still_there = conn.execute(
                sa.text("SELECT status FROM drug_side_effects WHERE id = :id"), {"id": row_id}
            ).scalar()
        assert still_there == "rejected"

        with engine.connect() as conn:
            conn.execute(sa.text("DELETE FROM drug_side_effects WHERE id = :id"), {"id": row_id})
            conn.commit()
        command.downgrade(cfg, LIFECYCLE_REV)
        with engine.connect() as conn:
            with pytest.raises(sa.exc.IntegrityError):
                _insert_side_effect_draft(
                    conn, ingredient_id, concept_code="rejected-after-remediated-downgrade", status="rejected"
                )


# --------------------------------------------------------------------- #
# Dialect-divergence demonstration (see module docstring)
# --------------------------------------------------------------------- #


class TestSqliteMultiStepDowngradeRefusalLandingBehavior:
    def test_multistep_downgrade_refusal_lands_one_step_above_the_failure_not_at_head(self, sqlite_db):
        """From head (k2_s0_add_rejected_status), request a downgrade all
        the way down to AI_GEN_REV. That's a 2-step chain:
        k2_s0_add_rejected_status -> k2_s0_lifecycle_transitions (step 1,
        no blocking data, commits) -> k2_s0_ai_generation_history (step 2,
        this is the target — never entered because
        knowledge_ai_generations is non-empty, so its own downgrade would
        be entered next but the chain stops at the boundary we ask for).
        To actually exercise a REFUSAL mid-chain, request a downgrade past
        AI_GEN_REV's own migration (to ORIGIN_REV): step 1
        (add_rejected_status -> lifecycle_transitions) commits, step 2
        (lifecycle_transitions -> ai_generation_history) commits, step 3
        (ai_generation_history -> knowledge_origin) is where
        knowledge_ai_generations' non-empty guard raises.

        On Postgres the equivalent 3-step call would leave the DB
        unchanged at head (the whole call is one transaction). On SQLite,
        steps 1 and 2 are already committed independently by the time step
        3 raises — the DB lands at AI_GEN_REV (the revision immediately
        above the one whose downgrade refused), not at head."""
        engine, cfg = sqlite_db
        command.upgrade(cfg, "head")
        assert _current_revision(engine) == REJECTED_REV

        with engine.connect() as conn:
            generation_id = _insert_ai_generation(conn)

        with pytest.raises(RuntimeError, match="Refusing to downgrade"):
            command.downgrade(cfg, ORIGIN_REV)

        landed_at = _current_revision(engine)
        assert landed_at == AI_GEN_REV, (
            "SQLite's non-transactional-per-step DDL means a mid-chain "
            "refusal leaves earlier steps committed — expected to land at "
            f"{AI_GEN_REV!r} (one step above the failure), got {landed_at!r}. "
            "This is NOT the same invariant the Postgres integration file "
            "asserts (there, the same scenario leaves the DB unchanged at "
            "whatever revision the call started from)."
        )
        assert landed_at != REJECTED_REV, (
            "if this ever equals head again, the SQLite/Postgres divergence "
            "this test exists to document has disappeared or Alembic's "
            "SQLite transaction handling changed — investigate before "
            "assuming this test is simply flaky"
        )

        # Confirm the two earlier steps really did commit: lifecycle
        # transitions history table (dropped by the step-1 downgrade) is
        # gone, but knowledge_ai_generations (the blocking table) is not.
        assert _table_exists(engine, "knowledge_lifecycle_transitions") is False
        assert _table_exists(engine, "knowledge_ai_generations") is True

        # Not a permanent wedge: remediate, then the interrupted downgrade
        # can be completed, and a subsequent upgrade back to head succeeds
        # without error (no partial/corrupted state).
        with engine.connect() as conn:
            conn.execute(
                sa.text("DELETE FROM knowledge_ai_generations WHERE id = :id"), {"id": generation_id}
            )
            conn.commit()
        command.downgrade(cfg, ORIGIN_REV)
        assert _current_revision(engine) == ORIGIN_REV
        assert _table_exists(engine, "knowledge_ai_generations") is False

        command.upgrade(cfg, "head")
        assert _current_revision(engine) == REJECTED_REV
