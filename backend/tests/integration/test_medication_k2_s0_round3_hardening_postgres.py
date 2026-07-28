"""PostgreSQL integration tests for `k2_s0_round3_hardening`: deterministic
AI-generation ordering (`sequence_number`) and full content immutability
(BEFORE DELETE guard triggers on the 5 ADR-13 content tables).

Neither behavior is meaningfully provable on SQLite alone:
- `sequence_number` assignment must stay unique and gap-free under
  Postgres's real concurrent-connection/MVCC model — SQLite's serialized
  single-writer model makes an equivalent race trivially impossible to
  construct.
- The no-hard-delete triggers exist on both dialects (see
  tests/test_medication_k2_s0_migrations_sqlite.py for the SQLite side),
  but proving they hold under transaction rollback and the sanctioned
  lifecycle-retirement path against a production-shaped engine belongs
  here.

Runs only when POSTGRES_TEST_URL is set — same convention as
tests/integration/test_medication_k1_5_approval_workflow_postgres.py.

All rows synthetic test fixtures — never real clinical content.
"""

from __future__ import annotations

import datetime as dt
import os
import threading
import uuid
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.core.system_actors import SystemActor
from app.models.drug_knowledge_ai_generation import KnowledgeAIGeneration
from app.models.drug_knowledge_content import DrugUsage
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.services import knowledge_repository as repo
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")

pytestmark = pytest.mark.integration

_ROLE = "internal_admin"


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
    alembic_ini = os.path.join(backend_dir, "alembic.ini")
    cfg = Config(alembic_ini)
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Generator[sa.Engine, None, None]:
    _require_postgres()
    engine = sa.create_engine(POSTGRES_TEST_URL, echo=False, future=True)
    with engine.connect() as _conn:
        assert _conn.dialect.name == "postgresql"
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated_schema(pg_engine: sa.Engine) -> Generator[sa.Engine, None, None]:
    db_url = pg_engine.url.render_as_string(hide_password=False)
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, "head")
    yield pg_engine
    command.downgrade(cfg, "k1_a1b_f2_specialty_seed")


@pytest.fixture()
def session_factory(migrated_schema: sa.Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_schema, expire_on_commit=False)


def _delete_content_rows(db: Session, table: str, where_sql: str, params: dict) -> None:
    """Test-only escape hatch: k2_s0_round3_hardening's content-immutability
    trigger blocks every DELETE against the 5 knowledge tables in real
    usage. Temporarily disabling the one specific table's guard trigger for
    the duration of this DELETE is a test-harness-only privilege; always
    re-enabled before returning."""
    trigger_name = f"trg_{table}_no_hard_delete"
    db.execute(sa.text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger_name}"))
    try:
        db.execute(sa.text(f"DELETE FROM {table} WHERE {where_sql}"), params)
    finally:
        db.execute(sa.text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger_name}"))


def _delete_lifecycle_transitions_for_ingredient(db: Session, ingredient_id: str) -> None:
    db.execute(
        sa.text(
            "ALTER TABLE knowledge_lifecycle_transitions "
            "DISABLE TRIGGER trg_knowledge_lifecycle_transitions_append_only"
        )
    )
    try:
        db.execute(
            sa.text(
                "DELETE FROM knowledge_lifecycle_transitions "
                "WHERE knowledge_table = 'drug_usage' "
                "AND knowledge_row_id IN "
                "(SELECT id FROM drug_usage WHERE drug_ingredient_id = :ingredient_id)"
            ),
            {"ingredient_id": ingredient_id},
        )
    finally:
        db.execute(
            sa.text(
                "ALTER TABLE knowledge_lifecycle_transitions "
                "ENABLE TRIGGER trg_knowledge_lifecycle_transitions_append_only"
            )
        )


def _delete_ai_generations_for_ingredient(db: Session, ingredient_id: str) -> None:
    db.execute(
        sa.text("ALTER TABLE knowledge_ai_generations DISABLE TRIGGER trg_knowledge_ai_generations_append_only")
    )
    try:
        db.execute(
            sa.text(
                "DELETE FROM knowledge_ai_generations "
                "WHERE knowledge_table = 'drug_usage' AND target_row_id IN "
                "(SELECT id FROM drug_usage WHERE drug_ingredient_id = :ingredient_id)"
            ),
            {"ingredient_id": ingredient_id},
        )
    finally:
        db.execute(
            sa.text("ALTER TABLE knowledge_ai_generations ENABLE TRIGGER trg_knowledge_ai_generations_append_only")
        )


@pytest.fixture()
def ingredient(session_factory: sessionmaker[Session]) -> Generator[dict, None, None]:
    suffix = uuid.uuid4().hex[:8]
    db = session_factory()
    try:
        drug_class = DrugClass(name=f"test-class-{suffix}", required_specialties=[])
        db.add(drug_class)
        db.flush()
        ingredient_row = DrugIngredient(name_inn=f"test-ingredient-{suffix}", drug_class_id=drug_class.id)
        db.add(ingredient_row)
        db.commit()
        ids = {"id": ingredient_row.id, "drug_class_id": drug_class.id}
    finally:
        db.close()

    try:
        yield ids
    finally:
        cleanup_db = session_factory()
        try:
            _delete_ai_generations_for_ingredient(cleanup_db, ids["id"])
            _delete_lifecycle_transitions_for_ingredient(cleanup_db, ids["id"])
            _delete_content_rows(
                cleanup_db, "drug_usage", "drug_ingredient_id = :ingredient_id", {"ingredient_id": ids["id"]}
            )
            cleanup_db.execute(
                sa.text("DELETE FROM drug_ingredients WHERE id = :ingredient_id"),
                {"ingredient_id": ids["id"]},
            )
            cleanup_db.execute(
                sa.text("DELETE FROM drug_classes WHERE id = :drug_class_id"),
                {"drug_class_id": ids["drug_class_id"]},
            )
            cleanup_db.commit()
        except Exception:
            cleanup_db.rollback()
            raise
        finally:
            cleanup_db.close()


def _approval_provenance_fields() -> dict[str, object]:
    """ck_drug_usage_approved_invariants requires evidence_level/source/
    version/last_reviewed_at to be non-null once a row reaches 'approved'.
    Synthetic placeholder values only — never real clinical content."""
    return dict(
        source="Synthetic Test Source",
        version="1.0",
        evidence_level="expert_opinion",
        last_reviewed_at=dt.datetime.now(dt.UTC),
    )


def _ai_synthesized_row(db: Session, ingredient_id: str) -> DrugUsage:
    row = repo.create_draft(
        db,
        DrugUsage,
        authored_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
        drug_ingredient_id=ingredient_id,
        locale="vi",
        audience="patient",
        content="synthetic AI-generated test content — never staged/production",
        origin="ai_synthesized",
        **_approval_provenance_fields(),
    )
    repo.submit_for_review(db, row, actor_user_id=SystemActor.MEDICATION_AI_SYNTHESIS.value)
    return row


def _approved_row(db: Session, ingredient_id: str, **overrides: object) -> DrugUsage:
    fields = dict(
        drug_ingredient_id=ingredient_id,
        locale="vi",
        audience="patient",
        content="synthetic test content — never staged/production",
        **_approval_provenance_fields(),
    )
    fields.update(overrides)
    row = repo.create_draft(db, DrugUsage, authored_by="author-1", **fields)
    repo.submit_for_review(db, row, actor_user_id="author-1")
    return repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=_ROLE)


def _make_generation(db: Session, *, target_row_id: str, **overrides: object) -> KnowledgeAIGeneration:
    fields = dict(
        knowledge_table="drug_usage",
        target_row_id=target_row_id,
        model_provider="synthetic-provider",
        model_identifier="synthetic-model-v1",
        prompt_template_id="synthetic-prompt",
        prompt_template_version="1.0",
        input_source_ids=[],
        input_hash="a" * 64,
        output_hash="b" * 64,
        generation_status="succeeded",
        created_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
    )
    fields.update(overrides)
    gen = KnowledgeAIGeneration(**fields)
    db.add(gen)
    db.commit()
    # `sequence_number` has no `server_default` declared at the ORM level
    # (it's DB/trigger-assigned via k2_s0_round3_hardening), so with this
    # module's `expire_on_commit=False` sessions the in-memory attribute
    # would otherwise stay at its pre-insert value (None) even though
    # Postgres has already assigned the real value — refresh to observe it.
    db.refresh(gen)
    return gen


class TestGenerationOrderingOnPostgres:
    """User Fix Round 3 requirement #1: a deterministic, server/DB-governed
    ordering (`sequence_number`) for AI generation attempts, that never ties
    even when `created_at` does, and survives a fresh session/connection
    reload."""

    def test_identical_created_at_values_get_deterministic_sequence_numbers(
        self, session_factory, ingredient
    ) -> None:
        db = session_factory()
        try:
            row = _ai_synthesized_row(db, ingredient["id"])
            same_ts = dt.datetime.now(dt.UTC)
            first = _make_generation(db, target_row_id=row.id, created_at=same_ts)
            second = _make_generation(db, target_row_id=row.id, created_at=same_ts)
            assert first.created_at == second.created_at, "the tie must be real, not accidental"
            assert first.sequence_number is not None
            assert second.sequence_number is not None
            assert first.sequence_number != second.sequence_number, (
                "identical created_at must not produce a tied ordering key"
            )
            assert second.sequence_number > first.sequence_number, (
                "insertion order, not created_at, must break the tie"
            )

            approved = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=_ROLE)
            assert approved.status == "approved"
            db.refresh(first)
            db.refresh(second)
            assert second.review_status == "promoted", (
                "the later-inserted (higher sequence_number) generation is authoritative"
            )
            assert first.review_status == "pending", "the earlier-inserted generation must not be touched"
        finally:
            db.close()

    def test_succeeded_then_failed_same_timestamp_blocks_promotion_of_older_succeeded(
        self, session_factory, ingredient
    ) -> None:
        db = session_factory()
        try:
            row = _ai_synthesized_row(db, ingredient["id"])
            same_ts = dt.datetime.now(dt.UTC)
            succeeded = _make_generation(db, target_row_id=row.id, generation_status="succeeded", created_at=same_ts)
            failed = _make_generation(db, target_row_id=row.id, generation_status="failed", created_at=same_ts)
            assert succeeded.created_at == failed.created_at
            assert failed.sequence_number > succeeded.sequence_number

            with pytest.raises(repo.AIProvenanceIncompleteError):
                repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=_ROLE)
            db.refresh(row)
            assert row.status == "clinical_review"
            db.refresh(succeeded)
            assert succeeded.review_status == "pending", (
                "an older succeeded attempt must never be promotable just because a "
                "later attempt sharing the same timestamp failed"
            )
        finally:
            db.close()

    def test_concurrent_generation_creation_gets_unique_sequence_numbers(self, session_factory, ingredient) -> None:
        setup_db = session_factory()
        try:
            row = _ai_synthesized_row(setup_db, ingredient["id"])
            row_id = row.id
        finally:
            setup_db.close()

        thread_count = 8
        start = threading.Barrier(thread_count, timeout=15)
        generation_ids: list[str | None] = [None] * thread_count
        errors: list[Exception] = []

        def _create(index: int) -> None:
            db = session_factory()
            try:
                start.wait()
                gen = _make_generation(db, target_row_id=row_id, generation_status="failed")
                generation_ids[index] = gen.id
            except Exception as exc:  # noqa: BLE001 — cross-thread result capture only
                errors.append(exc)
            finally:
                db.close()

        threads = [threading.Thread(target=_create, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"no concurrent insert should raise: {errors}"
        assert None not in generation_ids

        verify_db = session_factory()
        try:
            sequence_numbers = [
                verify_db.get(KnowledgeAIGeneration, gid).sequence_number for gid in generation_ids
            ]
        finally:
            verify_db.close()
        assert None not in sequence_numbers, "every concurrently created row must get a sequence_number"
        # The sequence is table-wide, not per-target-row, so it need not
        # start at 1 in this test — other tests in the same run may have
        # already advanced it. What matters: all distinct, and contiguous
        # (no ties, no gaps) among themselves.
        ordered = sorted(sequence_numbers)
        assert len(set(ordered)) == thread_count, (
            f"{thread_count} concurrent inserts must get {thread_count} DISTINCT "
            f"sequence_number values (no ties), got {sequence_numbers}"
        )
        assert ordered == list(range(ordered[0], ordered[0] + thread_count)), (
            f"{thread_count} concurrent inserts must get consecutive sequence_number "
            f"values with no gaps, got {sequence_numbers}"
        )

    def test_deterministic_selection_survives_reload(self, session_factory, ingredient) -> None:
        db = session_factory()
        try:
            row = _ai_synthesized_row(db, ingredient["id"])
            _make_generation(db, target_row_id=row.id, generation_status="failed")
            authoritative = _make_generation(db, target_row_id=row.id, generation_status="succeeded")
            row_id = row.id
            authoritative_id = authoritative.id
        finally:
            db.close()  # closing here (not just committing) forces the next session to re-derive everything

        reload_db = session_factory()
        try:
            approved = repo.approve_row(
                reload_db,
                reload_db.get(DrugUsage, row_id),
                actor_user_id="reviewer-1",
                actor_role=_ROLE,
            )
            assert approved.status == "approved"
            promoted = reload_db.get(KnowledgeAIGeneration, authoritative_id)
            assert promoted.review_status == "promoted", (
                "the same authoritative generation must be selected after a full "
                "session/connection reload, not merely within one process's cache"
            )
        finally:
            reload_db.close()


class TestContentDeleteOrphanIntegrityOnPostgres:
    """User Fix Round 3 requirement #2: persisted medication knowledge
    content must not be hard-deleted, on Postgres, for both referenced and
    unreferenced rows, with rollback preserving row + provenance, while the
    sanctioned lifecycle-retirement path keeps working."""

    def test_referenced_content_row_cannot_be_hard_deleted(self, session_factory, ingredient) -> None:
        db = session_factory()
        try:
            row = _approved_row(db, ingredient["id"])
            with pytest.raises(ProgrammingError, match="must not be hard-deleted"):
                db.execute(sa.text("DELETE FROM drug_usage WHERE id = :id"), {"id": row.id})
                db.commit()
            db.rollback()

            still_there = db.execute(
                sa.text("SELECT status FROM drug_usage WHERE id = :id"), {"id": row.id}
            ).scalar()
            assert still_there == "approved"
            transitions = db.execute(
                sa.text("SELECT COUNT(*) FROM knowledge_lifecycle_transitions WHERE knowledge_row_id = :id"),
                {"id": row.id},
            ).scalar()
            assert transitions > 0, "provenance history must remain intact"
        finally:
            db.close()

    def test_unreferenced_persisted_row_also_cannot_be_hard_deleted(self, session_factory, ingredient) -> None:
        """Full content immutability, not merely FK-orphan prevention: a
        freshly created draft row with zero lifecycle history and zero AI
        generations referencing it is STILL blocked from hard deletion."""
        db = session_factory()
        try:
            row = repo.create_draft(
                db,
                DrugUsage,
                authored_by="author-1",
                drug_ingredient_id=ingredient["id"],
                locale="vi",
                audience="patient",
                content="never submitted",
                **_approval_provenance_fields(),
            )
            no_history = db.execute(
                sa.text("SELECT COUNT(*) FROM knowledge_lifecycle_transitions WHERE knowledge_row_id = :id"),
                {"id": row.id},
            ).scalar()
            assert no_history == 0, "this row must genuinely have zero referencing history rows"

            with pytest.raises(ProgrammingError, match="must not be hard-deleted"):
                db.execute(sa.text("DELETE FROM drug_usage WHERE id = :id"), {"id": row.id})
                db.commit()
            db.rollback()
            still_there = db.execute(sa.text("SELECT id FROM drug_usage WHERE id = :id"), {"id": row.id}).scalar()
            assert still_there == row.id
        finally:
            db.close()

    def test_rollback_after_blocked_delete_leaves_row_and_provenance_intact(
        self, session_factory, ingredient
    ) -> None:
        db = session_factory()
        try:
            row = _approved_row(db, ingredient["id"])
            gen = _make_generation(db, target_row_id=row.id)
            before_content = db.execute(
                sa.text("SELECT content FROM drug_usage WHERE id = :id"), {"id": row.id}
            ).scalar()

            with pytest.raises(ProgrammingError):
                db.execute(sa.text("DELETE FROM drug_usage WHERE id = :id"), {"id": row.id})
                db.commit()
            db.rollback()

            after_content = db.execute(
                sa.text("SELECT content FROM drug_usage WHERE id = :id"), {"id": row.id}
            ).scalar()
            assert after_content == before_content
            still_gen = db.execute(
                sa.text("SELECT review_status FROM knowledge_ai_generations WHERE id = :id"), {"id": gen.id}
            ).scalar()
            assert still_gen == "pending"
        finally:
            db.close()

    def test_sanctioned_lifecycle_retirement_still_works(self, session_factory, ingredient) -> None:
        db = session_factory()
        try:
            first = _approved_row(db, ingredient["id"])
            second = repo.create_draft(
                db,
                DrugUsage,
                authored_by="author-1",
                drug_ingredient_id=ingredient["id"],
                locale="vi",
                audience="patient",
                content="version 2",
                **_approval_provenance_fields(),
            )
            repo.submit_for_review(db, second, actor_user_id="author-1")
            repo.approve_row(db, second, actor_user_id="reviewer-1", actor_role=_ROLE)
            db.refresh(first)
            assert first.status == "deprecated"

            retired = repo.retire_row(db, first, actor_user_id="reviewer-2", actor_role=_ROLE)
            assert retired.status == "retired"
            still_there = db.execute(sa.text("SELECT id FROM drug_usage WHERE id = :id"), {"id": first.id}).scalar()
            assert still_there == first.id, "retirement is a status transition, never a delete"
        finally:
            db.close()
