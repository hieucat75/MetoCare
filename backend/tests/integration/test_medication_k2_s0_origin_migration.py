"""Integration tests for the K2 Slice 0 migration chain:

    k2_s1_widen_evidence_level
        -> k2_s0_knowledge_origin        (add `origin` to the 5 knowledge tables)
        -> k2_s0_ai_generation_history   (create knowledge_ai_generations)
        -> k2_s0_lifecycle_transitions   (create knowledge_lifecycle_transitions)
        -> k2_s0_add_rejected_status     (widen status CHECK to include 'rejected'; head)

Run against a REAL PostgreSQL instance — CHECK constraint enforcement and
`information_schema`/`pg_constraint` introspection are the whole point of
this file. Mirrors the conventions of
tests/integration/test_medication_k2_widen_evidence_level_migration.py
(read in full before this file was written) — same `_reset_to_head`/
`_restore_head`/`_make_alembic_config` idioms, same "capture revision
immediately before a refused downgrade, assert equality after" pattern
instead of hardcoding an expected landing revision.

Usage (local):
    POSTGRES_TEST_URL="postgresql+psycopg://mcp:mcp@localhost:5432/mcp_test" \
    pytest tests/integration/test_medication_k2_s0_origin_migration.py -v -m integration

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

# Revision markers, in chain order (see module docstring).
SPECIALTY_SEED_REV = "k1_a1b_f2_specialty_seed"
PRE_ORIGIN_REV = "k2_s1_widen_evidence_level"
ORIGIN_REV = "k2_s0_knowledge_origin"
AI_GEN_REV = "k2_s0_ai_generation_history"
LIFECYCLE_REV = "k2_s0_lifecycle_transitions"
REJECTED_REV = "k2_s0_add_rejected_status"

pytestmark = pytest.mark.integration

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)

_ORIGIN_VALUES = ("source_extracted", "rule_derived", "ai_synthesized", "human_authored")
_ORIGIN_DEFAULT = "human_authored"
_OLD_STATUS_VALUES = ("draft", "clinical_review", "approved", "deprecated", "retired")
_NEW_STATUS_VALUES = ("draft", "clinical_review", "approved", "rejected", "deprecated", "retired")


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
    """Leaves the shared mcp_test database at head after this module's tests
    run, regardless of which revision an individual test left it at — same
    convention as test_medication_k2_widen_evidence_level_migration.py's
    `_restore_head` (module-scoped autouse, restores to head not a fixed
    "shared baseline" revision)."""
    yield
    command.upgrade(cfg, "head")


def _reset_to_head(cfg: Config) -> None:
    """Every test starts from a deterministic, known position regardless of
    what a previous test (or a manual `alembic` invocation earlier in the
    same session) left the shared mcp_test DB at."""
    command.upgrade(cfg, "head")


# --------------------------------------------------------------------- #
# Generic introspection helpers
# --------------------------------------------------------------------- #


def _column_info(pg_engine: sa.Engine, table: str, column: str) -> dict | None:
    with pg_engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT data_type, character_maximum_length, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).mappings().first()
    return dict(row) if row else None


def _table_exists(pg_engine: sa.Engine, table: str) -> bool:
    with pg_engine.connect() as conn:
        return bool(
            conn.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = :table)"
                ),
                {"table": table},
            ).scalar()
        )


def _constraint_def(pg_engine: sa.Engine, name: str) -> str | None:
    with pg_engine.connect() as conn:
        return conn.execute(
            sa.text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :name"),
            {"name": name},
        ).scalar()


def _index_names(pg_engine: sa.Engine, table: str) -> set[str]:
    with pg_engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT indexname FROM pg_indexes WHERE tablename = :table"),
            {"table": table},
        ).scalars().all()
    return set(rows)


def _current_revision(pg_engine: sa.Engine) -> str:
    with pg_engine.connect() as conn:
        return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()


def _count(pg_engine: sa.Engine, sql: str, params: dict | None = None) -> int:
    with pg_engine.connect() as conn:
        return conn.execute(sa.text(sql), params or {}).scalar()


# --------------------------------------------------------------------- #
# Fixture seeding helpers
# --------------------------------------------------------------------- #


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


def _trigger_exists(conn: sa.Connection, table: str, trigger_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM pg_trigger "
                "WHERE tgname = :name AND tgrelid = CAST(:table AS regclass))"
            ),
            {"name": trigger_name, "table": table},
        ).scalar()
    )


def _force_delete(conn: sa.Connection, table: str, trigger_name: str, where_sql: str, params: dict) -> None:
    """Test-only escape hatch (fix round 1, 2026-07-28): k2_s0_integrity_guards'
    append-only triggers correctly block EVERY delete against
    knowledge_lifecycle_transitions/knowledge_ai_generations in real usage
    — but this test file's own synthetic-fixture teardown still needs to
    remove rows it created, both for isolation between tests and to keep
    the shared mcp_test database at zero residue for other tests'
    "downgrade succeeds when empty" assertions. Temporarily disabling the
    one specific append-only trigger for the duration of this DELETE is a
    test-harness-only privilege — nothing in application code ever does
    this, and the trigger is unconditionally re-enabled before this
    function returns, success or failure, so it can never leak into a
    later statement on the same connection.

    This file's own tests exercise many intermediate revisions BEFORE
    k2_s0_integrity_guards was ever applied (e.g. cleanup running while
    the DB sits at a pre-remediation revision), where the trigger does
    not exist yet — `_trigger_exists` makes the disable/enable dance
    conditional so this helper works unmodified at any revision from the
    table's own creation onward, not just at head."""
    guarded = _trigger_exists(conn, table, trigger_name)
    if guarded:
        conn.execute(sa.text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger_name}"))
    try:
        conn.execute(sa.text(f"DELETE FROM {table} WHERE {where_sql}"), params)
    finally:
        if guarded:
            conn.execute(sa.text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger_name}"))
    conn.commit()


def _cleanup_seeded_ingredient(conn: sa.Connection, ingredient_id: str) -> None:
    """FK-safe, ID-scoped teardown for everything `_seed_ingredient` (and any
    drug_side_effects rows created against it) can have left behind —
    including any row it caused to be written to
    knowledge_lifecycle_transitions, since that table's own migration
    refuses to downgrade while non-empty. Never a table-wide DELETE."""
    class_id = conn.execute(
        sa.text("SELECT drug_class_id FROM drug_ingredients WHERE id = :id"),
        {"id": ingredient_id},
    ).scalar()
    if _table_exists_sync(conn, "knowledge_lifecycle_transitions"):
        _force_delete(
            conn,
            "knowledge_lifecycle_transitions",
            "trg_knowledge_lifecycle_transitions_append_only",
            "knowledge_table = 'drug_side_effects' AND knowledge_row_id IN "
            "(SELECT id FROM drug_side_effects WHERE drug_ingredient_id = :id)",
            {"id": ingredient_id},
        )
    conn.execute(
        sa.text("DELETE FROM drug_side_effects WHERE drug_ingredient_id = :id"),
        {"id": ingredient_id},
    )
    conn.execute(sa.text("DELETE FROM drug_ingredients WHERE id = :id"), {"id": ingredient_id})
    if class_id is not None:
        conn.execute(sa.text("DELETE FROM drug_classes WHERE id = :id"), {"id": class_id})
    conn.commit()


def _table_exists_sync(conn: sa.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :table)"
            ),
            {"table": table},
        ).scalar()
    )


def _insert_side_effect_draft(
    conn: sa.Connection,
    ingredient_id: str,
    *,
    concept_code: str,
    status: str = "draft",
    origin: str | None = None,
    artifact_hash: str | None = "not-included",
    row_id: str | None = None,
) -> str:
    """Raw INSERT into drug_side_effects, tolerant of which columns exist
    at the current revision. `origin`/`artifact_hash` are only included in
    the statement when a non-sentinel value is supplied — pass `origin=None`
    (the default) when running against a revision where the column doesn't
    exist yet. `artifact_hash` defaults to being OMITTED entirely (its own
    sentinel "not-included") since it's nullable everywhere it exists and
    irrelevant to these tests; pass an explicit value only if needed."""
    resolved_id = row_id or str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    columns: dict[str, object] = {
        "id": resolved_id,
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
    if artifact_hash != "not-included":
        columns["artifact_hash"] = artifact_hash
    if status == "approved":
        # ck_drug_side_effects_approved_invariants requires all five of
        # these to be non-null on any row with status='approved'.
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
    return resolved_id


def _insert_ai_generation(conn: sa.Connection, *, review_status: str = "pending") -> str:
    row_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    conn.execute(
        sa.text(
            "INSERT INTO knowledge_ai_generations "
            "(id, knowledge_table, target_row_id, model_provider, model_identifier, "
            "prompt_template_id, prompt_template_version, input_source_ids, input_hash, "
            "generation_status, origin, review_status, created_by, created_at, updated_at) "
            "VALUES (:id, 'drug_side_effects', NULL, 'openrouter', 'test-model', "
            "'tmpl-1', '1.0', cast(:input_source_ids as json), :input_hash, "
            "'succeeded', 'ai_synthesized', :review_status, :created_by, :now, :now)"
        ),
        {
            "id": row_id,
            "input_source_ids": "[]",
            "input_hash": "a" * 64,
            "review_status": review_status,
            # Fix round 1, 2026-07-28 (Codex Round 1 finding #4): must be a
            # registered SystemActor — k2_s0_integrity_guards' CHECK
            # constraint now rejects an unregistered "system:*" value like
            # the "system:test" this used to hardcode.
            "created_by": "system:medication-ai-synthesis",
            "now": now,
        },
    )
    conn.commit()
    return row_id


def _cleanup_ai_generation(conn: sa.Connection, row_id: str) -> None:
    _force_delete(
        conn,
        "knowledge_ai_generations",
        "trg_knowledge_ai_generations_append_only",
        "id = :id",
        {"id": row_id},
    )


def _insert_lifecycle_transition(
    conn: sa.Connection, ingredient_id: str, *, to_status: str = "clinical_review"
) -> str:
    """`ingredient_id` is used only to seed a REAL target row (a
    drug_side_effects draft against that ingredient) that the transition
    can legitimately reference — fix round 1, 2026-07-28 (Codex Round 1
    finding #7): this used to record `ingredient_id` itself as
    `knowledge_row_id` while declaring `knowledge_table='drug_side_effects'`,
    which is exactly the mismatched-table repro Codex demonstrated;
    k2_s0_integrity_guards' polymorphic-target-exists trigger now rejects
    it outright. The caller's existing cleanup path
    (`_cleanup_seeded_ingredient`) already deletes every drug_side_effects
    row for a given ingredient_id, so this new row needs no separate
    teardown of its own."""
    target_row_id = _insert_side_effect_draft(
        conn, ingredient_id, concept_code=f"lifecycle-transition-target-{uuid.uuid4().hex[:8]}"
    )
    row_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.UTC)
    conn.execute(
        sa.text(
            "INSERT INTO knowledge_lifecycle_transitions "
            "(id, knowledge_table, knowledge_row_id, from_status, to_status, actor_id, "
            "actor_role, reason_code, rationale, transitioned_at, created_at, updated_at) "
            "VALUES (:id, 'drug_side_effects', :row_id, 'draft', :to_status, 'tester', NULL, "
            "'standard_transition', 'synthetic test transition', :now, :now, :now)"
        ),
        {"id": row_id, "row_id": target_row_id, "to_status": to_status, "now": now},
    )
    conn.commit()
    return row_id


def _cleanup_lifecycle_transition(conn: sa.Connection, row_id: str) -> None:
    _force_delete(
        conn,
        "knowledge_lifecycle_transitions",
        "trg_knowledge_lifecycle_transitions_append_only",
        "id = :id",
        {"id": row_id},
    )


# --------------------------------------------------------------------- #
# k2_s0_knowledge_origin
# --------------------------------------------------------------------- #


class TestKnowledgeOriginMigration:
    def test_origin_column_absent_before_migration(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, PRE_ORIGIN_REV)
        for table in _KNOWLEDGE_TABLES:
            assert _column_info(pg_engine, table, "origin") is None, table
        command.upgrade(cfg, "head")

    def test_upgrade_adds_origin_column_with_check_and_default(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, PRE_ORIGIN_REV)
        command.upgrade(cfg, ORIGIN_REV)
        for table in _KNOWLEDGE_TABLES:
            info = _column_info(pg_engine, table, "origin")
            assert info is not None, table
            assert info["data_type"] == "character varying", table
            assert info["character_maximum_length"] == 24, table
            assert info["is_nullable"] == "NO", table
            assert info["column_default"] == f"'{_ORIGIN_DEFAULT}'::character varying", table

            defn = _constraint_def(pg_engine, f"ck_{table}_origin")
            assert defn is not None, table
            for value in _ORIGIN_VALUES:
                assert f"'{value}'::character varying" in defn, (table, value, defn)
        command.upgrade(cfg, "head")

    def test_backfill_classifies_legacy_rows_as_human_authored(self, pg_engine, cfg):
        """Seeds a row before k1_a1b_f2_specialty_seed's own down_revision
        (i.e. at a revision predating both artifact_hash and origin), then
        upgrades through k1_a1b_artifact_hash -> k2_s1_widen_evidence_level
        -> k2_s0_knowledge_origin, proving the server_default backfill
        (not a separate UPDATE — confirmed absent from the migration's own
        upgrade()) classifies it 'human_authored', and that no row is ever
        misclassified as 'ai_synthesized'/'source_extracted'."""
        _reset_to_head(cfg)
        command.downgrade(cfg, SPECIALTY_SEED_REV)
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
        try:
            with pg_engine.connect() as conn:
                row_id = _insert_side_effect_draft(
                    conn, ingredient_id, concept_code="legacy-concept", artifact_hash="not-included"
                )

            command.upgrade(cfg, ORIGIN_REV)

            with pg_engine.connect() as conn:
                row = conn.execute(
                    sa.text(
                        "SELECT origin, concept_code, label, frequency, action_level, "
                        "description, status, status_changed_by, authored_by "
                        "FROM drug_side_effects WHERE id = :id"
                    ),
                    {"id": row_id},
                ).mappings().first()
            assert row is not None
            assert row["origin"] == _ORIGIN_DEFAULT
            assert row["origin"] not in ("ai_synthesized", "source_extracted")
            # Every other column survives the multi-migration upgrade unchanged.
            assert row["concept_code"] == "legacy-concept"
            assert row["label"] == "Nausea"
            assert row["frequency"] == "common"
            assert row["action_level"] == "self_monitor"
            assert row["description"] == "synthetic test description"
            assert row["status"] == "draft"
            assert row["status_changed_by"] == "tester"
            assert row["authored_by"] == "tester"

            command.upgrade(cfg, "head")
        finally:
            with pg_engine.connect() as conn:
                _cleanup_seeded_ingredient(conn, ingredient_id)
            command.upgrade(cfg, "head")

    def test_downgrade_succeeds_when_all_rows_default(self, pg_engine, cfg):
        _reset_to_head(cfg)
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
        try:
            with pg_engine.connect() as conn:
                _insert_side_effect_draft(conn, ingredient_id, concept_code="default-origin")

            command.downgrade(cfg, PRE_ORIGIN_REV)
            for table in _KNOWLEDGE_TABLES:
                assert _column_info(pg_engine, table, "origin") is None, table
            command.upgrade(cfg, "head")
        finally:
            with pg_engine.connect() as conn:
                _cleanup_seeded_ingredient(conn, ingredient_id)
            command.upgrade(cfg, "head")

    def test_populated_row_survives_full_downgrade_reupgrade_round_trip(self, pg_engine, cfg):
        """Codex Round 1 finding #9: a populated migration round-trip test
        must actually reload the row and assert every preexisting field
        survived, not just that the schema shape (column presence/CHECK
        text) came back correctly. Downgrades all the way to PRE_ORIGIN_REV
        (dropping origin + the two Slice 0 history tables + narrowing the
        status CHECK back to 5 values), then re-upgrades to head, then
        reloads the SAME row by id and compares every field against a
        snapshot captured before the round trip — not just origin."""
        _reset_to_head(cfg)
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
        try:
            with pg_engine.connect() as conn:
                row_id = _insert_side_effect_draft(
                    conn,
                    ingredient_id,
                    concept_code="round-trip-survivor",
                    status="draft",
                    origin="human_authored",
                )
            with pg_engine.connect() as conn:
                # Codex Round 2 finding (fix round 2, 2026-07-28): SELECT *
                # (not a hand-picked subset) so no column — including
                # updated_at/artifact_hash/source/version/evidence_level/
                # reviewed_by/last_reviewed_at — is silently excluded from
                # the survival comparison. Only DDL runs during this
                # round trip (Postgres batch_alter_table is a plain ALTER
                # TABLE, never a row rewrite), so every column, including
                # updated_at, is expected to be bit-for-bit identical.
                before = conn.execute(
                    sa.text("SELECT * FROM drug_side_effects WHERE id = :id"),
                    {"id": row_id},
                ).mappings().first()
            assert before is not None

            command.downgrade(cfg, PRE_ORIGIN_REV)
            for table in _KNOWLEDGE_TABLES:
                assert _column_info(pg_engine, table, "origin") is None, table
            assert _table_exists(pg_engine, "knowledge_lifecycle_transitions") is False
            assert _table_exists(pg_engine, "knowledge_ai_generations") is False

            command.upgrade(cfg, "head")
            assert _table_exists(pg_engine, "knowledge_lifecycle_transitions") is True
            assert _table_exists(pg_engine, "knowledge_ai_generations") is True

            with pg_engine.connect() as conn:
                after = conn.execute(
                    sa.text("SELECT * FROM drug_side_effects WHERE id = :id"),
                    {"id": row_id},
                ).mappings().first()
            assert after is not None
            assert dict(after) == dict(before), (
                "every field on the row must survive a full downgrade-to-"
                "PRE_ORIGIN_REV-and-back-to-head round trip unchanged, not "
                "just the schema shape"
            )
        finally:
            with pg_engine.connect() as conn:
                _cleanup_seeded_ingredient(conn, ingredient_id)
            command.upgrade(cfg, "head")

    def test_downgrade_refuses_when_row_reclassified(self, pg_engine, cfg):
        """Origin values other than the default cannot silently be dropped
        by a downgrade. 'ai_synthesized' + status='draft' is a legal
        combination per the model's own construction-time guard
        (`_AI_SYNTHESIZED_FORBIDDEN_STATUSES` excludes 'draft')."""
        _reset_to_head(cfg)
        with pg_engine.connect() as conn:
            initial_ingredients = conn.execute(sa.text("SELECT COUNT(*) FROM drug_ingredients")).scalar()
            initial_classes = conn.execute(sa.text("SELECT COUNT(*) FROM drug_classes")).scalar()
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
        try:
            with pg_engine.connect() as conn:
                row_id = _insert_side_effect_draft(
                    conn, ingredient_id, concept_code="reclassified", origin="ai_synthesized", status="draft"
                )

            before = _current_revision(pg_engine)
            with pytest.raises(RuntimeError, match="Refusing to downgrade"):
                command.downgrade(cfg, PRE_ORIGIN_REV)
            after = _current_revision(pg_engine)
            assert after == before, (
                "a refused downgrade must never move the revision at all on "
                f"Postgres (single-transaction command) — was {before!r}, now {after!r}"
            )
            for table in _KNOWLEDGE_TABLES:
                assert _column_info(pg_engine, table, "origin") is not None, table

            # No partial state: a subsequent normal upgrade to head still
            # succeeds without error.
            command.upgrade(cfg, "head")
            assert _current_revision(pg_engine) == before

            with pg_engine.connect() as conn:
                still_there = conn.execute(
                    sa.text("SELECT origin FROM drug_side_effects WHERE id = :id"), {"id": row_id}
                ).scalar()
            assert still_there == "ai_synthesized"

            # Remediate, then prove the same downgrade now succeeds.
            with pg_engine.connect() as conn:
                conn.execute(sa.text("DELETE FROM drug_side_effects WHERE id = :id"), {"id": row_id})
                conn.commit()
            command.downgrade(cfg, PRE_ORIGIN_REV)
            for table in _KNOWLEDGE_TABLES:
                assert _column_info(pg_engine, table, "origin") is None, table
        finally:
            with pg_engine.connect() as conn:
                _cleanup_seeded_ingredient(conn, ingredient_id)
            command.upgrade(cfg, "head")
            with pg_engine.connect() as conn:
                final_ingredients = conn.execute(sa.text("SELECT COUNT(*) FROM drug_ingredients")).scalar()
                final_classes = conn.execute(sa.text("SELECT COUNT(*) FROM drug_classes")).scalar()
            assert final_ingredients == initial_ingredients, "zero residue: drug_ingredients"
            assert final_classes == initial_classes, "zero residue: drug_classes"


# --------------------------------------------------------------------- #
# k2_s0_ai_generation_history
# --------------------------------------------------------------------- #


class TestAIGenerationHistoryMigration:
    def test_table_absent_before_migration(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, ORIGIN_REV)
        assert _table_exists(pg_engine, "knowledge_ai_generations") is False
        command.upgrade(cfg, "head")

    def test_upgrade_creates_table_with_expected_columns(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, ORIGIN_REV)
        command.upgrade(cfg, AI_GEN_REV)
        assert _table_exists(pg_engine, "knowledge_ai_generations") is True

        expected_not_null = {
            "id": (36, None),
            "knowledge_table": (32, None),
            "model_provider": (32, None),
            "model_identifier": (64, None),
            "prompt_template_id": (64, None),
            "prompt_template_version": (32, None),
            "input_hash": (64, None),
            "generation_status": (16, None),
            "origin": (24, "'ai_synthesized'::character varying"),
            "review_status": (16, "'pending'::character varying"),
            "created_by": (255, None),
        }
        for column, (max_len, default) in expected_not_null.items():
            info = _column_info(pg_engine, "knowledge_ai_generations", column)
            assert info is not None, column
            assert info["character_maximum_length"] == max_len, column
            assert info["is_nullable"] == "NO", column
            if default is not None:
                assert info["column_default"] == default, column

        expected_nullable = ("target_row_id", "model_version_snapshot", "normalization_pipeline_version", "output_hash", "failure_reason", "superseded_by_generation_id")
        for column in expected_nullable:
            info = _column_info(pg_engine, "knowledge_ai_generations", column)
            assert info is not None, column
            assert info["is_nullable"] == "YES", column
        command.upgrade(cfg, "head")

    def test_check_constraints_match_migration(self, pg_engine, cfg):
        _reset_to_head(cfg)
        expected = {
            "ck_knowledge_ai_generations_table": _KNOWLEDGE_TABLES,
            "ck_knowledge_ai_generations_status": ("succeeded", "failed"),
            "ck_knowledge_ai_generations_review_status": ("pending", "promoted", "rejected", "superseded"),
            "ck_knowledge_ai_generations_origin": _ORIGIN_VALUES,
        }
        for name, values in expected.items():
            defn = _constraint_def(pg_engine, name)
            assert defn is not None, name
            for value in values:
                assert f"'{value}'::character varying" in defn, (name, value, defn)

    def test_indexes_present(self, pg_engine, cfg):
        _reset_to_head(cfg)
        indexes = _index_names(pg_engine, "knowledge_ai_generations")
        assert "ix_knowledge_ai_generations_row" in indexes
        assert "ix_knowledge_ai_generations_review_status" in indexes

    def test_self_referential_fk(self, pg_engine, cfg):
        _reset_to_head(cfg)
        defn = _constraint_def(pg_engine, "fk_knowledge_ai_generations_superseded_by")
        assert defn is not None
        assert "FOREIGN KEY (superseded_by_generation_id)" in defn
        assert "REFERENCES knowledge_ai_generations(id)" in defn
        assert "ON DELETE RESTRICT" in defn

    def test_downgrade_succeeds_when_empty(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, ORIGIN_REV)
        assert _table_exists(pg_engine, "knowledge_ai_generations") is False
        command.upgrade(cfg, "head")

    def test_downgrade_refuses_when_nonempty(self, pg_engine, cfg):
        _reset_to_head(cfg)
        row_id = None
        try:
            with pg_engine.connect() as conn:
                row_id = _insert_ai_generation(conn)

            before = _current_revision(pg_engine)
            with pytest.raises(RuntimeError, match="Refusing to downgrade"):
                command.downgrade(cfg, ORIGIN_REV)
            after = _current_revision(pg_engine)
            assert after == before
            assert _table_exists(pg_engine, "knowledge_ai_generations") is True

            command.upgrade(cfg, "head")
            assert _current_revision(pg_engine) == before

            with pg_engine.connect() as conn:
                still_there = conn.execute(
                    sa.text("SELECT id FROM knowledge_ai_generations WHERE id = :id"), {"id": row_id}
                ).scalar()
            assert still_there == row_id

            with pg_engine.connect() as conn:
                _cleanup_ai_generation(conn, row_id)
            row_id = None
            command.downgrade(cfg, ORIGIN_REV)
            assert _table_exists(pg_engine, "knowledge_ai_generations") is False

            residue = _count(pg_engine, "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'knowledge_ai_generations'")
            assert residue == 0, "zero residue: knowledge_ai_generations table itself must be gone"
        finally:
            if row_id is not None:
                with pg_engine.connect() as conn:
                    _cleanup_ai_generation(conn, row_id)
            command.upgrade(cfg, "head")


# --------------------------------------------------------------------- #
# k2_s0_lifecycle_transitions
# --------------------------------------------------------------------- #


class TestLifecycleTransitionsMigration:
    def test_table_absent_before_migration(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, AI_GEN_REV)
        assert _table_exists(pg_engine, "knowledge_lifecycle_transitions") is False
        command.upgrade(cfg, "head")

    def test_upgrade_creates_table_with_expected_columns(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, AI_GEN_REV)
        command.upgrade(cfg, LIFECYCLE_REV)
        assert _table_exists(pg_engine, "knowledge_lifecycle_transitions") is True

        expected_not_null = {
            "id": 36,
            "knowledge_table": 32,
            "knowledge_row_id": 36,
            "from_status": 16,
            "to_status": 16,
            "actor_id": 255,
            "reason_code": 64,
        }
        for column, max_len in expected_not_null.items():
            info = _column_info(pg_engine, "knowledge_lifecycle_transitions", column)
            assert info is not None, column
            assert info["character_maximum_length"] == max_len, column
            assert info["is_nullable"] == "NO", column

        for column in ("actor_role", "rationale", "transitioned_at"):
            info = _column_info(pg_engine, "knowledge_lifecycle_transitions", column)
            assert info is not None, column
        assert _column_info(pg_engine, "knowledge_lifecycle_transitions", "actor_role")["is_nullable"] == "YES"
        assert _column_info(pg_engine, "knowledge_lifecycle_transitions", "rationale")["is_nullable"] == "NO"
        assert _column_info(pg_engine, "knowledge_lifecycle_transitions", "transitioned_at")["is_nullable"] == "NO"
        command.upgrade(cfg, "head")

    def test_check_constraints_match_migration(self, pg_engine, cfg):
        _reset_to_head(cfg)
        # Both from_status and to_status are NOT NULL, constrained
        # unconditionally to all 6 canonical STATUS_VALUES (migration's own
        # comment: no row has ever recorded a null "creation" transition).
        status_values = ("draft", "clinical_review", "approved", "rejected", "deprecated", "retired")
        expected = {
            "ck_knowledge_lifecycle_transitions_table": _KNOWLEDGE_TABLES,
            "ck_knowledge_lifecycle_transitions_from_status": status_values,
            "ck_knowledge_lifecycle_transitions_to_status": status_values,
        }
        for name, values in expected.items():
            defn = _constraint_def(pg_engine, name)
            assert defn is not None, name
            for value in values:
                assert f"'{value}'::character varying" in defn, (name, value, defn)

    def test_index_present(self, pg_engine, cfg):
        _reset_to_head(cfg)
        indexes = _index_names(pg_engine, "knowledge_lifecycle_transitions")
        assert "ix_knowledge_lifecycle_transitions_row" in indexes

    def test_downgrade_succeeds_when_empty(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, AI_GEN_REV)
        assert _table_exists(pg_engine, "knowledge_lifecycle_transitions") is False
        command.upgrade(cfg, "head")

    def test_downgrade_refuses_when_nonempty(self, pg_engine, cfg):
        _reset_to_head(cfg)
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
        transition_id = None
        try:
            with pg_engine.connect() as conn:
                transition_id = _insert_lifecycle_transition(conn, ingredient_id)

            before = _current_revision(pg_engine)
            with pytest.raises(RuntimeError, match="Refusing to downgrade"):
                command.downgrade(cfg, AI_GEN_REV)
            after = _current_revision(pg_engine)
            assert after == before
            assert _table_exists(pg_engine, "knowledge_lifecycle_transitions") is True

            command.upgrade(cfg, "head")
            assert _current_revision(pg_engine) == before

            with pg_engine.connect() as conn:
                still_there = conn.execute(
                    sa.text("SELECT id FROM knowledge_lifecycle_transitions WHERE id = :id"),
                    {"id": transition_id},
                ).scalar()
            assert still_there == transition_id

            with pg_engine.connect() as conn:
                _cleanup_lifecycle_transition(conn, transition_id)
            transition_id = None
            command.downgrade(cfg, AI_GEN_REV)
            assert _table_exists(pg_engine, "knowledge_lifecycle_transitions") is False
        finally:
            if transition_id is not None:
                with pg_engine.connect() as conn:
                    _cleanup_lifecycle_transition(conn, transition_id)
            with pg_engine.connect() as conn:
                _cleanup_seeded_ingredient(conn, ingredient_id)
            command.upgrade(cfg, "head")


# --------------------------------------------------------------------- #
# k2_s0_add_rejected_status
# --------------------------------------------------------------------- #


class TestAddRejectedStatusMigration:
    def test_rejected_status_rejected_by_check_before_migration(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, LIFECYCLE_REV)
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
        try:
            with pg_engine.connect() as conn:
                with pytest.raises(sa.exc.IntegrityError):
                    _insert_side_effect_draft(
                        conn, ingredient_id, concept_code="pre-migration-rejected", status="rejected"
                    )
        finally:
            with pg_engine.connect() as conn:
                # The failed INSERT above never committed, so only the
                # ingredient/class rows from _seed_ingredient need cleanup.
                _cleanup_seeded_ingredient(conn, ingredient_id)
            command.upgrade(cfg, "head")

    def test_upgrade_widens_check_constraint_to_allow_rejected(self, pg_engine, cfg):
        _reset_to_head(cfg)
        command.downgrade(cfg, LIFECYCLE_REV)
        command.upgrade(cfg, REJECTED_REV)
        for table in _KNOWLEDGE_TABLES:
            defn = _constraint_def(pg_engine, f"ck_{table}_status")
            assert defn is not None, table
            for value in _NEW_STATUS_VALUES:
                assert f"'{value}'::character varying" in defn, (table, value, defn)

        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
        try:
            with pg_engine.connect() as conn:
                row_id = _insert_side_effect_draft(
                    conn, ingredient_id, concept_code="post-migration-rejected", status="rejected"
                )
            with pg_engine.connect() as conn:
                status = conn.execute(
                    sa.text("SELECT status FROM drug_side_effects WHERE id = :id"), {"id": row_id}
                ).scalar()
            assert status == "rejected"
        finally:
            with pg_engine.connect() as conn:
                _cleanup_seeded_ingredient(conn, ingredient_id)
            command.upgrade(cfg, "head")

    def test_downgrade_succeeds_when_no_rejected_rows(self, pg_engine, cfg):
        _reset_to_head(cfg)
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
        try:
            with pg_engine.connect() as conn:
                _insert_side_effect_draft(conn, ingredient_id, concept_code="approved-status-ok", status="approved")

            command.downgrade(cfg, LIFECYCLE_REV)
            for table in _KNOWLEDGE_TABLES:
                defn = _constraint_def(pg_engine, f"ck_{table}_status")
                assert defn is not None, table
                assert "'rejected'::character varying" not in defn, table
                for value in _OLD_STATUS_VALUES:
                    assert f"'{value}'::character varying" in defn, (table, value, defn)
            command.upgrade(cfg, "head")
        finally:
            with pg_engine.connect() as conn:
                _cleanup_seeded_ingredient(conn, ingredient_id)
            command.upgrade(cfg, "head")

    def test_downgrade_refuses_when_rejected_row_exists(self, pg_engine, cfg):
        _reset_to_head(cfg)
        with pg_engine.connect() as conn:
            initial_ingredients = conn.execute(sa.text("SELECT COUNT(*) FROM drug_ingredients")).scalar()
            initial_classes = conn.execute(sa.text("SELECT COUNT(*) FROM drug_classes")).scalar()
        with pg_engine.connect() as conn:
            ingredient_id = _seed_ingredient(conn)
        try:
            with pg_engine.connect() as conn:
                row_id = _insert_side_effect_draft(
                    conn, ingredient_id, concept_code="blocking-rejected", status="rejected"
                )

            before = _current_revision(pg_engine)
            with pytest.raises(RuntimeError, match="Refusing to downgrade"):
                command.downgrade(cfg, LIFECYCLE_REV)
            after = _current_revision(pg_engine)
            assert after == before, (
                "a refused downgrade must never move the revision at all on "
                f"Postgres (single-transaction command) — was {before!r}, now {after!r}"
            )
            for table in _KNOWLEDGE_TABLES:
                defn = _constraint_def(pg_engine, f"ck_{table}_status")
                assert "'rejected'::character varying" in defn, table

            command.upgrade(cfg, "head")
            assert _current_revision(pg_engine) == before

            with pg_engine.connect() as conn:
                still_there = conn.execute(
                    sa.text("SELECT status FROM drug_side_effects WHERE id = :id"), {"id": row_id}
                ).scalar()
            assert still_there == "rejected"

            with pg_engine.connect() as conn:
                conn.execute(sa.text("DELETE FROM drug_side_effects WHERE id = :id"), {"id": row_id})
                conn.commit()
            command.downgrade(cfg, LIFECYCLE_REV)
            for table in _KNOWLEDGE_TABLES:
                defn = _constraint_def(pg_engine, f"ck_{table}_status")
                assert "'rejected'::character varying" not in defn, table
        finally:
            with pg_engine.connect() as conn:
                _cleanup_seeded_ingredient(conn, ingredient_id)
            command.upgrade(cfg, "head")
            with pg_engine.connect() as conn:
                final_ingredients = conn.execute(sa.text("SELECT COUNT(*) FROM drug_ingredients")).scalar()
                final_classes = conn.execute(sa.text("SELECT COUNT(*) FROM drug_classes")).scalar()
            assert final_ingredients == initial_ingredients, "zero residue: drug_ingredients"
            assert final_classes == initial_classes, "zero residue: drug_classes"
