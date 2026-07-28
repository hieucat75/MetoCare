"""PostgreSQL integration tests for K1.6: Approved Medication Knowledge
Retrieval Contract against a REAL PostgreSQL instance.

Three things a SQLite unit test cannot prove on its own (plan §4.3/§10,
MEDICATION_K1_6_KNOWLEDGE_RETRIEVAL_IMPLEMENTATION_PLAN.md):

1. Concurrent approve/read visibility under Postgres's actual MVCC/
   transaction-isolation semantics: a reader calling
   `get_current_by_business_key` while an `approve_row` transition is
   mid-transaction (uncommitted) must observe either the pre- or
   post-transition single approved row — never zero, never two.
2. Query-plan sanity: the partial unique index / `ix_drug_ingredients_
   drug_class_id` are actually usable by the query shapes this module
   issues (checked with `enable_seqscan=off` so the assertion is about
   whether the index CAN be chosen, not whether the planner happens to
   prefer it on a small/empty table — stable, not brittle to exact cost).
3. The partial unique index really is a working, independent DB-level
   backstop — proven the same way K1.5's own backstop test proves it: the
   bypass INSERT of a second 'approved' row itself fails with a real
   IntegrityError. The state `MultipleApprovedRowsError` reads back against
   (two persisted 'approved' rows for one business key) is provably
   impossible to construct via any INSERT while that index is active in
   EITHER dialect — so, as in the SQLite unit tests, that specific
   defense-in-depth code path is proven reachable by temporarily dropping
   and recreating the real index around the minimum necessary window.

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
from app.models.drug_knowledge_content import DrugUsage
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.services import knowledge_repository as repo
from app.services import knowledge_retrieval as retrieval
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")

pytestmark = pytest.mark.integration


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


@pytest.fixture()
def ingredient(session_factory: sessionmaker[Session]) -> Generator[dict, None, None]:
    """Test-isolation fix (2026-07-27, final-checkpoint verification):
    every DrugUsage row this file's tests create uses this fixture's `id`
    as its `drug_ingredient_id`. `submit_for_review`/`approve_row` each
    append a row to `knowledge_lifecycle_transitions` (Slice 0, real
    append-only history — its migration's `downgrade()` refuses to run
    while any row exists). This fixture previously had no teardown at
    all, so repeated runs against the shared disposable mcp_test database
    accumulated transition rows that eventually blocked a downstream
    migration downgrade (same defect independently found and fixed in
    test_medication_k1_5_approval_workflow_postgres.py's `ingredient`
    fixture). Cleanup runs in a `finally` block (fires even if the test
    body raised), scoped strictly by this fixture's own captured
    `id`/`drug_class_id` — never table-wide."""
    suffix = uuid.uuid4().hex[:8]
    db = session_factory()
    try:
        drug_class = DrugClass(name=f"test-class-{suffix}", required_specialties=[])
        db.add(drug_class)
        db.flush()
        ingredient_row = DrugIngredient(
            name_inn=f"test-ingredient-{suffix}", drug_class_id=drug_class.id
        )
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
            cleanup_db.execute(
                sa.text(
                    "DELETE FROM knowledge_lifecycle_transitions "
                    "WHERE knowledge_table = 'drug_usage' "
                    "AND knowledge_row_id IN "
                    "(SELECT id FROM drug_usage WHERE drug_ingredient_id = :ingredient_id)"
                ),
                {"ingredient_id": ids["id"]},
            )
            cleanup_db.execute(
                sa.text("DELETE FROM drug_usage WHERE drug_ingredient_id = :ingredient_id"),
                {"ingredient_id": ids["id"]},
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
    """ck_drug_usage_approved_invariants requires reviewed_by/evidence_level/
    source/version/last_reviewed_at to be non-null once a row reaches
    'approved' — same requirement as the SQLite unit tests. Synthetic
    placeholder values only — never real clinical content/sourcing."""
    return dict(
        source="Synthetic Test Source",
        version="1.0",
        evidence_level="expert_opinion",
        reviewed_by="reviewer-1",
        last_reviewed_at=dt.datetime.now(dt.UTC),
    )


def _submitted_row(db: Session, ingredient_id: str, **overrides: object) -> DrugUsage:
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
    return row


class TestConcurrentApproveReadVisibility:
    """Plan §10: a reader calling `get_current_by_business_key` while an
    `approve_row` supersession transition is mid-transaction (uncommitted)
    must observe either the pre- or post-transition single approved row —
    never zero, never two. An in-flight, uncommitted transaction's changes
    (the old row's `deprecated` UPDATE) are invisible to any other session
    until commit under Postgres's default isolation level (READ COMMITTED)
    — and, more precisely (Codex Round 1, P3-6), under ANY of Postgres's
    isolation levels, since none of them permit dirty reads; this test
    doesn't pin down or require the specific default, only the "no dirty
    reads" property common to all of them. This test proves that guarantee
    holds for THIS module's read path specifically, not just for
    `approve_row`'s own writers (already proven by K1.5's own concurrency
    tests).

    `_deprecate_superseded` is instrumented (monkeypatch, not a production
    code change) to pause AFTER it has deprecated the old row but BEFORE
    `approve_row` issues its own approve UPDATE — the exact mid-transition
    window plan §10 asks to be proven safe. `approve_row` itself, and the
    exact statement sequence it issues, are completely unmodified."""

    def test_reader_never_observes_zero_or_two_during_supersession(
        self, session_factory, ingredient, monkeypatch
    ) -> None:
        setup_db = session_factory()
        try:
            old_approved = _submitted_row(setup_db, ingredient["id"], content="old approved version")
            old_approved = repo.approve_row(
                setup_db, old_approved, actor_user_id="reviewer-0", actor_role="internal_admin"
            )
            assert old_approved.status == "approved"
            old_approved_id = old_approved.id

            candidate = _submitted_row(setup_db, ingredient["id"], content="candidate new version")
            candidate_id = candidate.id
        finally:
            setup_db.close()

        deprecated_paused = threading.Event()
        release_writer = threading.Event()
        writer_done = threading.Event()
        writer_result: dict[str, object] = {}
        original_deprecate = repo._deprecate_superseded

        def _instrumented_deprecate(db, row, *, actor_user_id, now):
            result = original_deprecate(db, row, actor_user_id=actor_user_id, now=now)
            deprecated_paused.set()
            release_writer.wait(timeout=10)
            return result

        monkeypatch.setattr(repo, "_deprecate_superseded", _instrumented_deprecate)

        def _writer() -> None:
            db = session_factory()
            try:
                row = db.get(DrugUsage, candidate_id)
                approved = repo.approve_row(
                    db, row, actor_user_id="reviewer-1", actor_role="internal_admin"
                )
                writer_result["status"] = approved.status
            except Exception as exc:  # noqa: BLE001 — cross-thread result capture only
                writer_result["error"] = exc
            finally:
                db.close()
                writer_done.set()

        writer_thread = threading.Thread(target=_writer)
        writer_thread.start()

        assert deprecated_paused.wait(timeout=10), "writer never reached the mid-transition pause"

        # Mid-transaction (old row deprecated in an UNCOMMITTED transaction,
        # new row not yet approved): a separate reader session must still
        # see exactly the PRE-transition state — the old row is still
        # 'approved' from any other session's point of view, since Postgres
        # READ COMMITTED hides uncommitted changes entirely.
        reader_db = session_factory()
        try:
            mid_transition = retrieval.get_current_by_business_key(
                reader_db, DrugUsage, drug_ingredient_id=ingredient["id"], locale="vi", audience="patient"
            )
            assert mid_transition is not None, "reader must never observe zero approved rows"
            assert mid_transition.id == old_approved_id, (
                "reader must observe the PRE-transition row while the writer's "
                "transaction is still uncommitted"
            )
        finally:
            reader_db.close()

        release_writer.set()
        assert writer_done.wait(timeout=10), "writer never finished"
        writer_thread.join(timeout=5)
        assert not writer_thread.is_alive(), "writer thread did not finish within the join timeout"
        assert "error" not in writer_result, f"writer failed unexpectedly: {writer_result.get('error')}"
        assert writer_result["status"] == "approved"

        # Post-transition: a fresh reader must now observe exactly the NEW
        # row — never zero, never two.
        post_db = session_factory()
        try:
            post_transition = retrieval.get_current_by_business_key(
                post_db, DrugUsage, drug_ingredient_id=ingredient["id"], locale="vi", audience="patient"
            )
            assert post_transition is not None
            assert post_transition.id == candidate_id
        finally:
            post_db.close()


class TestQueryPlanSanity:
    """New for K1.6 (plan §10): assert the query shapes this module issues
    can actually use the indexes they're designed around. `enable_seqscan`
    is forced off for the duration of each EXPLAIN so the assertion is
    about whether the index CAN be chosen — stable regardless of table
    size/statistics in an ephemeral test DB — not whether the planner
    happens to prefer it, which would be brittle."""

    def _explain(self, db: Session, query) -> str:
        compiled = query.statement.compile(
            dialect=db.bind.dialect, compile_kwargs={"literal_binds": True}
        )
        db.execute(sa.text("SET LOCAL enable_seqscan = off"))
        result = db.execute(sa.text(f"EXPLAIN {compiled}"))
        return "\n".join(row[0] for row in result)

    def test_get_current_by_business_key_uses_partial_approved_index(
        self, session_factory, ingredient
    ) -> None:
        db = session_factory()
        try:
            with db.begin():
                query = db.query(DrugUsage).filter_by(
                    status="approved",
                    drug_ingredient_id=ingredient["id"],
                    locale="vi",
                    audience="patient",
                )
                plan = self._explain(db, query)
            assert "uq_drug_usage_approved_key" in plan, plan
        finally:
            db.close()

    def test_list_current_for_drug_class_uses_ingredient_class_index(
        self, session_factory, ingredient
    ) -> None:
        """Codex Round 1, P3-2: this EXPLAIN'd query now includes the same
        `ORDER BY` clause the real `list_current_for_drug_class` issues
        (`DrugIngredient.name_inn, *order_columns`) — the previous version
        omitted it, so it wasn't a byte-for-byte match of the production
        query shape (a missing Sort node is unlikely to change the
        underlying scan/join strategy, but there's no reason to leave the
        gap when it costs nothing to close)."""
        db = session_factory()
        try:
            with db.begin():
                query = (
                    db.query(DrugUsage)
                    .join(DrugIngredient, DrugIngredient.id == DrugUsage.drug_ingredient_id)
                    .filter(
                        DrugUsage.status == "approved",
                        DrugIngredient.drug_class_id == ingredient["drug_class_id"],
                    )
                    .order_by(DrugIngredient.name_inn, DrugUsage.locale, DrugUsage.audience)
                )
                plan = self._explain(db, query)
            assert (
                "ix_drug_ingredients_drug_class_id" in plan or "uq_drug_usage_approved_key" in plan
            ), plan
        finally:
            db.close()


class TestPartialUniqueIndexBackstopReadSide:
    """Proves the DB-level backstop is still real (mirrors K1.5's own
    TestPartialUniqueIndexBackstop) AND that this module's
    `MultipleApprovedRowsError` defense-in-depth check is reachable and
    correct against a REAL, persisted Postgres violation — not a
    hypothetical. Since the active partial unique index makes it
    structurally impossible to INSERT a second 'approved' row for one
    business key (proven first, below, exactly like K1.5's test), the
    otherwise-unreachable state is constructed by temporarily dropping and
    recreating the real index around the minimum necessary window — the
    same technique used in the SQLite unit tests, for the same reason.

    Codex Round 1, P1-3: the recreate step is defensive, not merely
    sequential — it removes any row that would still violate the
    constraint BEFORE recreating the index, regardless of whether the test
    body's own assertion above it passed or failed. Previously, if the
    `pytest.raises` assertion had failed instead of raising (i.e. a
    regression that stopped `get_current_by_business_key` from raising),
    the `finally` block's plain DELETE-then-CREATE sequence would still
    have run, but a DIFFERENT failure mode (the DELETE step itself
    erroring for any reason) would have skipped the CREATE INDEX
    statement entirely — silently leaving this index dropped for the rest
    of this module-scoped Postgres schema (shared with
    `TestQueryPlanSanity`, which currently only avoids hitting this by
    virtue of running EARLIER in file-definition order, not by any
    guarantee)."""

    def test_second_approved_insert_is_rejected_by_the_real_index(
        self, session_factory, ingredient
    ) -> None:
        db1 = session_factory()
        try:
            first = _submitted_row(db1, ingredient["id"])
            first = repo.approve_row(db1, first, actor_user_id="reviewer-1", actor_role="internal_admin")
            assert first.status == "approved"
        finally:
            db1.close()

        db2 = session_factory()
        try:
            now = dt.datetime.now(dt.UTC)
            rogue = DrugUsage(
                drug_ingredient_id=ingredient["id"],
                locale="vi",
                audience="patient",
                content="bypasses the service layer entirely",
                authored_by="author-2",
                status="approved",
                status_changed_by="author-2",
                status_changed_at=now,
                **_approval_provenance_fields(),
            )
            db2.add(rogue)
            with pytest.raises(IntegrityError, match="uq_drug_usage_approved_key"):
                db2.commit()
            db2.rollback()
        finally:
            db2.close()

    def test_get_current_by_business_key_raises_against_a_real_forced_violation(
        self, session_factory, ingredient
    ) -> None:
        db = session_factory()
        try:
            db.execute(sa.text("DROP INDEX uq_drug_usage_approved_key"))
            db.commit()
            try:
                now = dt.datetime.now(dt.UTC)
                for variant in ("a", "b"):
                    row = DrugUsage(
                        drug_ingredient_id=ingredient["id"],
                        locale="vi",
                        audience="patient",
                        content=f"forced-violation-{variant}",
                        authored_by="author-1",
                        status="approved",
                        status_changed_by="author-1",
                        status_changed_at=now,
                        **_approval_provenance_fields(),
                    )
                    db.add(row)
                db.commit()

                with pytest.raises(retrieval.MultipleApprovedRowsError):
                    retrieval.get_current_by_business_key(
                        db,
                        DrugUsage,
                        drug_ingredient_id=ingredient["id"],
                        locale="vi",
                        audience="patient",
                    )
            finally:
                # Defensive, not merely sequential (Codex Round 1, P1-3):
                # discard any failed-transaction state first, then remove
                # ANY row that would still violate the constraint — via a
                # portable GROUP BY/HAVING query, not by trusting this
                # specific test's own ids — before attempting to recreate
                # the index, so recreation is never skipped just because
                # something above it didn't clean up as expected.
                db.rollback()
                db.execute(
                    sa.text(
                        "DELETE FROM drug_usage WHERE status = 'approved' AND "
                        "(drug_ingredient_id, locale, audience) IN ("
                        "SELECT drug_ingredient_id, locale, audience FROM drug_usage "
                        "WHERE status = 'approved' "
                        "GROUP BY drug_ingredient_id, locale, audience HAVING COUNT(*) > 1)"
                    )
                )
                db.commit()
                db.execute(
                    sa.text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_drug_usage_approved_key ON "
                        "drug_usage (drug_ingredient_id, locale, audience) "
                        "WHERE status = 'approved'"
                    )
                )
                db.commit()
        finally:
            db.close()
