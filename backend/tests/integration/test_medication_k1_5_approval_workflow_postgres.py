"""Postgres integration tests for K1.5: Clinical Review & Approval Write Path
against a REAL PostgreSQL instance.

Two things a SQLite unit test cannot prove on its own (plan §4.3,
MEDICATION_K1_5_APPROVAL_WORKFLOW_IMPLEMENTATION_PLAN.md):

1. The atomic `UPDATE ... WHERE status = 'clinical_review'` optimistic-
   concurrency pattern holds under Postgres's actual transaction isolation
   semantics, not just SQLite's.
2. The partial unique index (`uq_drug_usage_approved_key`, already shipped
   in `k1_m01_knowledge_schema` — NOT added by this slice) really is a
   working, independent DB-level backstop: bypassing the service layer
   entirely and inserting a second `approved` row for the same business
   key directly must raise a real Postgres IntegrityError.

Runs only when POSTGRES_TEST_URL is set — same convention as
tests/integration/test_medication_a1b_orchestrator_postgres.py.

All rows synthetic test fixtures — never real clinical content.
"""

from __future__ import annotations

import datetime as dt
import os
import threading
import time
import uuid
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.models.drug_knowledge_content import DrugUsage
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.services import knowledge_repository as repo
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


def _delete_lifecycle_transitions_for_ingredient(db: Session, ingredient_id: str) -> None:
    """Test-only escape hatch (fix round 1, 2026-07-28): k2_s0_integrity_guards'
    append-only trigger correctly blocks this raw DELETE in real usage —
    but this fixture's own teardown still needs to remove the history rows
    it created, scoped strictly to this one ingredient_id, so the shared
    disposable mcp_test database stays clean for later downgrade tests.
    Temporarily disabling the trigger for the duration of this one DELETE
    is a test-harness-only privilege; it is always re-enabled before this
    function returns."""
    db.execute(sa.text("ALTER TABLE knowledge_lifecycle_transitions DISABLE TRIGGER trg_knowledge_lifecycle_transitions_append_only"))
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
        db.execute(sa.text("ALTER TABLE knowledge_lifecycle_transitions ENABLE TRIGGER trg_knowledge_lifecycle_transitions_append_only"))


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
    """Every DrugUsage row any test in this module creates uses this
    fixture's `id` as its `drug_ingredient_id` (the shared business-key
    field, via `_submitted_row`/direct construction) — so it alone is
    enough to scope a full, FK-safe teardown of everything a single test
    created.

    Test-isolation fix (2026-07-27): since Slice 0, `submit_for_review`/
    `approve_row` also append a row to `knowledge_lifecycle_transitions`
    (real, append-only history — its own migration's `downgrade()`
    refuses to run while any row exists, by design). Before this fix nothing
    ever deleted those rows, so repeated runs against the shared disposable
    mcp_test database accumulated history that eventually made the module's
    own `migrated_schema` teardown downgrade fail. This finally block
    deletes, by direct SQL scoped strictly to this fixture's own captured
    ids (never table-wide/unpredicated), everything this one test could
    have created — in FK-safe order (transitions/usage rows before their
    parent ingredient/class) — and runs even if the test body raised.
    Deletion is plain SQL issued by the test itself, never through
    knowledge_repository.py (which exposes no delete path at all, by
    design, per ADR-13 append-only) — the production append-only guarantee
    is untouched.
    """
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
            _delete_lifecycle_transitions_for_ingredient(cleanup_db, ids["id"])
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
    'approved' — same requirement as the SQLite unit tests
    (tests/test_knowledge_repository.py). Synthetic placeholder values
    only — never real clinical content/sourcing.

    `reviewed_by` deliberately omitted (fix round 1, 2026-07-28, Codex
    Round 1 finding #6): `build_draft` now rejects an explicit
    `reviewed_by=` kwarg — it is bound to the approving actor inside
    `approve_row` itself."""
    return dict(
        source="Synthetic Test Source",
        version="1.0",
        evidence_level="expert_opinion",
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


class TestConcurrentApproveRaceUnderRealPostgresIsolation:
    """Real Postgres connection, per plan §4.3 — the atomic
    UPDATE...WHERE status='clinical_review' pattern (and, since the Codex
    round-1 P1-1 fix, the SELECT...FOR UPDATE canonical-row lock ahead of
    it) must hold under Postgres's actual transaction isolation semantics,
    not just SQLite's.

    Codex round-1 P2-1: the original version of this test called
    approve_row for session A synchronously to completion (including its
    commit) BEFORE ever calling approve_row for session B — i.e. plain
    sequential Python calls with no threading at all, despite the test's
    own name/docstring claiming "concurrent". This version uses two real
    threads racing the SAME row, synchronized to start together via a
    Barrier. Genuine overlap is no longer test-instrumented — it comes
    directly from approve_row's own real `SELECT ... FOR UPDATE` on the
    canonical row (P1-1): whichever thread's statement reaches Postgres
    second genuinely blocks on that row's lock until the first thread's
    transaction ends, which is the exact same locking behavior a real
    production concurrent-approval call would hit.
    """

    def test_concurrent_approve_race_under_real_postgres_isolation(
        self, session_factory, ingredient
    ) -> None:
        db_setup = session_factory()
        try:
            row = _submitted_row(db_setup, ingredient["id"])
            row_id = row.id
        finally:
            db_setup.close()

        barrier = threading.Barrier(2)
        results: dict[str, tuple[str, object]] = {}

        def _race(key: str, actor_user_id: str) -> None:
            db = session_factory()
            try:
                row = db.get(DrugUsage, row_id)
                assert row.status == "clinical_review"
                barrier.wait(timeout=10)
                approved = repo.approve_row(
                    db, row, actor_user_id=actor_user_id, actor_role="internal_admin"
                )
                results[key] = ("success", approved.status)
            except Exception as exc:  # noqa: BLE001 — cross-thread result capture only
                results[key] = ("failure", exc)
            finally:
                db.close()

        thread_a = threading.Thread(target=_race, args=("a", "reviewer-1"))
        thread_b = threading.Thread(target=_race, args=("b", "reviewer-2"))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=30)
        thread_b.join(timeout=30)

        assert not thread_a.is_alive() and not thread_b.is_alive(), (
            "a racing thread deadlocked or timed out"
        )
        assert set(results) == {"a", "b"}, f"both threads must report a result, got {results}"

        outcomes = {k: v[0] for k, v in results.items()}
        assert sorted(outcomes.values()) == ["failure", "success"], (
            f"exactly one of the two racing approvals must succeed, got {outcomes}"
        )
        loser_key = next(k for k, v in outcomes.items() if v == "failure")
        # The loser can lose two ways depending on exact interleaving,
        # both correct: (a) it wins the FOR UPDATE lock race but the winner
        # already committed by the time its own transition is validated
        # against the now-'approved' canonical row (Illegal transition
        # approved->approved), or (b) it is genuinely blocked on the FOR
        # UPDATE lock, unblocks after the winner commits, and then loses
        # the atomic UPDATE's rowcount check. Either way it must be a
        # TransitionError, never a raw DB error or a silent no-op.
        assert isinstance(results[loser_key][1], repo.TransitionError), (
            f"loser must fail with TransitionError, got {type(results[loser_key][1])}: "
            f"{results[loser_key][1]}"
        )

        verify_db = session_factory()
        try:
            approved_count = (
                verify_db.query(DrugUsage).filter_by(id=row_id, status="approved").count()
            )
            assert approved_count == 1, "exactly one session's approval must have won"
        finally:
            verify_db.close()


class TestConcurrentApproveTwoDistinctRowsRaceForSameBusinessKey:
    """Gate A (PTH review of the K1.5 implementation checkpoint): the test
    above races two sessions over the SAME row (a losing-race read). This
    test instead has TWO DISTINCT clinical_review rows for the SAME
    business key, each approved through the real approve_row production
    path by its own thread/session, forced to genuinely overlap — not
    called sequentially — via real Postgres row-lock contention: both
    threads' _deprecate_superseded step targets the SAME pre-existing
    approved row first, so whichever thread loses that lock race is
    provably blocked mid-transaction, not just started later.

    This exercises the DB partial-unique-index backstop as a live side
    effect of two concurrent service-layer calls, not a standalone bypass
    INSERT — the backstop test below is kept as an additional, lower-level
    proof, not a replacement for this one.

    Codex round-3 P3-1: the synchronization point between thread B holding
    row1's lock and thread C being released to race it used to rely on a
    fixed `time.sleep(1.0)` grace period after B's lock-acquired signal —
    not a proof of contention, just a guess generous enough not to flake
    in practice, and inherently either too short (flaky) or too long
    (slow) depending on the machine. Replaced with a third, independent
    monitoring connection polling `pg_stat_activity` (bounded interval
    sleeps, monotonic deadline) until it observes a backend genuinely in
    `wait_event_type = 'Lock'` state.

    Codex round-4 P3: the round-3 fix filtered only by
    `l.relation = 'drug_usage'::regclass` — any backend blocked on that
    relation for any reason would satisfy it, not necessarily thread C's
    own connection. Hardened further: thread C's own `pg_backend_pid()`
    is captured directly from its own session immediately after it's
    created (before it does anything else), published to the main thread,
    and the monitoring poll filters by that EXACT pid — proving thread C's
    own backend specifically is blocked, not just "some backend somewhere"
    on the same table.
    """

    def test_two_distinct_clinical_review_rows_race_to_approve_same_business_key(
        self, session_factory, ingredient, monkeypatch
    ) -> None:
        setup_db = session_factory()
        try:
            old_approved = _submitted_row(
                setup_db, ingredient["id"], content="old approved version"
            )
            old_approved = repo.approve_row(
                setup_db, old_approved, actor_user_id="reviewer-0", actor_role="internal_admin"
            )
            assert old_approved.status == "approved"
            old_approved_id = old_approved.id

            candidate_b = _submitted_row(setup_db, ingredient["id"], content="candidate B")
            candidate_c = _submitted_row(setup_db, ingredient["id"], content="candidate C")
            candidate_b_id = candidate_b.id
            candidate_c_id = candidate_c.id
        finally:
            setup_db.close()

        # A bare threading.Barrier lining up the two approve_row *calls* is
        # not sufficient to force genuine overlap: local Postgres is fast
        # enough that thread B's entire transaction (deprecate + approve +
        # commit) can complete before thread C's first statement is even
        # sent, in which case there is no real lock contention at all — C
        # simply starts fresh afterward, sees candidate_b as the new
        # approved row, and correctly deprecates it too. Both calls then
        # "succeed" with no exception, which is valid sequential behavior,
        # not proof of overlap. (Observed empirically: the Barrier-only
        # version of this test passed on ~1 run in ~10 and failed its own
        # "exactly one must fail" assertion the rest of the time, with
        # both sides reporting success — not a product bug, a test-design
        # bug in the first draft of this test.)
        #
        # To force TRUE overlap deterministically, `_deprecate_superseded`
        # is instrumented (monkeypatch, not a production code change) so
        # reviewer-b's call pauses — with row1's lock already acquired,
        # inside its still-open transaction — until reviewer-c's thread has
        # had time to issue its own conflicting UPDATE and genuinely block
        # on that same Postgres row lock. `approve_row` itself, and the
        # exact statement sequence it issues, are completely unmodified —
        # this is still the real production approval path end to end.
        row1_locked_by_b = threading.Event()
        release_b = threading.Event()
        c_pid_ready = threading.Event()
        c_pid_holder: dict[str, int] = {}
        original_deprecate = repo._deprecate_superseded

        def _instrumented_deprecate(db, row, *, actor_user_id, now):
            result = original_deprecate(db, row, actor_user_id=actor_user_id, now=now)
            if actor_user_id == "reviewer-b":
                row1_locked_by_b.set()
                release_b.wait(timeout=10)
            return result

        monkeypatch.setattr(repo, "_deprecate_superseded", _instrumented_deprecate)

        results: dict[str, tuple[str, object]] = {}

        def _race_b() -> None:
            db = session_factory()
            try:
                row = db.get(DrugUsage, candidate_b_id)
                approved = repo.approve_row(
                    db, row, actor_user_id="reviewer-b", actor_role="internal_admin"
                )
                results["b"] = ("success", approved.status)
            except Exception as exc:  # noqa: BLE001
                # This except exists ONLY to carry the losing thread's
                # exception back to the main thread for assertion — it does
                # NOT mean approve_row swallowed anything. approve_row's own
                # except Exception: db.rollback(); raise already ran and
                # re-raised the *original, unmodified* exception before this
                # line ever sees it (verified below: isinstance + message).
                results["b"] = ("failure", exc)
            finally:
                db.close()

        def _race_c() -> None:
            row1_locked_by_b.wait(timeout=10)  # don't even start until B holds the lock
            db = session_factory()
            try:
                # Publish this connection's own backend pid BEFORE doing
                # anything that could block, so the main thread can poll
                # pg_stat_activity for this EXACT backend (Codex round-4
                # P3) rather than any backend blocked on the relation.
                c_pid_holder["pid"] = db.execute(sa.text("SELECT pg_backend_pid()")).scalar()
                c_pid_ready.set()
                row = db.get(DrugUsage, candidate_c_id)
                # This call's own _deprecate_superseded UPDATE genuinely
                # blocks in Postgres here, waiting on row1's lock — real
                # DB-level contention, not a Python-side wait.
                approved = repo.approve_row(
                    db, row, actor_user_id="reviewer-c", actor_role="internal_admin"
                )
                results["c"] = ("success", approved.status)
            except Exception as exc:  # noqa: BLE001
                results["c"] = ("failure", exc)
            finally:
                db.close()

        thread_b = threading.Thread(target=_race_b)
        thread_c = threading.Thread(target=_race_c)
        thread_b.start()
        thread_c.start()
        assert row1_locked_by_b.wait(timeout=10), "B never reached the lock point"
        assert c_pid_ready.wait(timeout=10), "C's backend pid was never published"
        c_pid = c_pid_holder["pid"]

        # Confirm thread C's OWN backend (pinned by pid, not just "some"
        # backend blocked on the drug_usage relation — Codex round-4 P3)
        # is GENUINELY blocked on the Postgres row lock B holds, via a
        # third, independent monitoring connection polling
        # pg_stat_activity — before releasing B, rather than guessing
        # with a fixed sleep (Codex round-3 P3-1).
        monitor_db = session_factory()
        try:
            blocked_confirmed = False
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                waiting = monitor_db.execute(
                    sa.text(
                        "SELECT count(*) FROM pg_stat_activity a "
                        "WHERE a.pid = :pid "
                        "AND a.wait_event_type = 'Lock' "
                        "AND a.state = 'active'"
                    ),
                    {"pid": c_pid},
                ).scalar()
                monitor_db.rollback()
                if waiting and waiting > 0:
                    blocked_confirmed = True
                    break
                time.sleep(0.05)
            assert blocked_confirmed, (
                f"thread C's own backend (pid={c_pid}) never appeared "
                "genuinely blocked in pg_stat_activity within the timeout "
                "— this test must observe real contention on THAT exact "
                "connection, not assume it from a fixed sleep or from any "
                "backend on the table (it should fail exactly like this if "
                "the _deprecate_superseded row lock is ever removed)"
            )
        finally:
            # Always release B even if the pg_stat_activity assertion above
            # fails, so both threads can still be joined and cleaned up
            # rather than hanging on `release_b.wait(timeout=10)`.
            release_b.set()
            monitor_db.close()

        thread_b.join(timeout=30)
        thread_c.join(timeout=30)

        assert not thread_b.is_alive() and not thread_c.is_alive(), (
            "a racing thread deadlocked or timed out — the two transactions "
            "must resolve deterministically via row-lock contention, never hang"
        )
        assert set(results) == {"b", "c"}, f"both threads must report a result, got {results}"

        outcomes = {k: v[0] for k, v in results.items()}
        assert sorted(outcomes.values()) == ["failure", "success"], (
            f"exactly one of the two racing approvals must succeed and the other "
            f"must fail — never both succeeding, never both failing, got {outcomes}"
        )
        winner_key = next(k for k, v in outcomes.items() if v == "success")
        loser_key = "c" if winner_key == "b" else "b"
        winner_id = candidate_b_id if winner_key == "b" else candidate_c_id
        loser_id = candidate_c_id if winner_key == "b" else candidate_b_id

        # Codex round-1 P1-3: the loser must surface as a TransitionError
        # (plan §7's taxonomy for "lost optimistic-concurrency race"), not
        # a raw IntegrityError — but the original IntegrityError must not
        # be discarded, only re-typed (`raise ... from exc`, checked via
        # __cause__).
        loser_exc = results[loser_key][1]
        assert isinstance(loser_exc, repo.TransitionError), (
            "the losing transaction must fail via the domain TransitionError "
            "taxonomy (plan §7's 'lost optimistic-concurrency race'), not a raw "
            f"unmapped IntegrityError — got {type(loser_exc)}: {loser_exc}"
        )
        assert isinstance(loser_exc.__cause__, IntegrityError), (
            "the real Postgres IntegrityError must still be reachable via "
            "__cause__ — the DB backstop firing must never look like it was "
            "silently swallowed, only re-typed"
        )
        assert "uq_drug_usage_approved_key" in str(loser_exc.__cause__), (
            "the underlying IntegrityError must name the actual partial unique "
            "index, proving it came from the real DB constraint and not an "
            "unrelated failure"
        )

        # Durable-visibility check (transaction-boundary "commit succeeded"
        # proof, Gate B): read from a THIRD, fresh session/connection that
        # never participated in the race.
        verify_db = session_factory()
        try:
            approved_rows = (
                verify_db.query(DrugUsage)
                .filter_by(
                    drug_ingredient_id=ingredient["id"],
                    locale="vi",
                    audience="patient",
                    status="approved",
                )
                .all()
            )
            assert len(approved_rows) == 1, (
                "exactly one row must be approved after the race resolves — never "
                "zero (both failing) and never two (the invariant #1 violation this "
                "whole slice exists to prevent)"
            )
            assert approved_rows[0].id == winner_id

            old_row = verify_db.get(DrugUsage, old_approved_id)
            assert old_row.status == "deprecated", (
                "the pre-existing approved row must have been deprecated by "
                "whichever candidate won"
            )

            loser_row = verify_db.get(DrugUsage, loser_id)
            assert loser_row.status == "clinical_review", (
                "the losing transaction's row must be completely untouched — its "
                "rollback must be full, not leaving it in a partial/corrupt "
                "intermediate status"
            )
        finally:
            verify_db.close()


class TestPartialUniqueIndexBackstop:
    """Proves the DB-level backstop (plan §3.5 invariant #1, second
    enforcement layer) actually works, independent of trusting the
    service-layer code to be bug-free — bypasses approve_row entirely and
    inserts a second 'approved' row for the same business key directly via
    the ORM. This index already exists (k1_m01_knowledge_schema, verified
    prior to this slice) — this test does not create it."""

    def test_partial_unique_index_backstop_rejects_second_approved_row(
        self, session_factory, ingredient
    ) -> None:
        db1 = session_factory()
        try:
            first = _submitted_row(db1, ingredient["id"])
            first = repo.approve_row(
                db1, first, actor_user_id="reviewer-1", actor_role="internal_admin"
            )
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
                # reviewed_by supplied directly (not via
                # _approval_provenance_fields(), which no longer includes
                # it — fix round 1, Codex Round 1 finding #6) because this
                # test bypasses approve_row entirely.
                reviewed_by="reviewer-1",
                **_approval_provenance_fields(),
            )
            db2.add(rogue)
            with pytest.raises(IntegrityError, match="uq_drug_usage_approved_key"):
                db2.commit()
            db2.rollback()
        finally:
            db2.close()

        verify_db = session_factory()
        try:
            approved_count = (
                verify_db.query(DrugUsage)
                .filter_by(
                    drug_ingredient_id=ingredient["id"],
                    locale="vi",
                    audience="patient",
                    status="approved",
                )
                .count()
            )
            assert approved_count == 1, (
                "the rogue direct-INSERT bypass must never have been committed — "
                "only the legitimate approve_row-created row survives"
            )
        finally:
            verify_db.close()


class TestConstraintMappingUsesStructuredDiagnostics:
    """Codex round-2 P2-1: `_is_approved_key_violation` must identify the
    approved-key partial unique index via the real Postgres driver's
    structured diagnostics (`exc.orig.diag.constraint_name`), never by
    searching the rendered exception text — which embeds bound SQL
    parameters and is therefore attacker/caller-influenceable."""

    def test_deceptive_actor_id_does_not_cause_false_positive_remap(
        self, session_factory, ingredient
    ) -> None:
        """A row missing required provenance violates
        ck_drug_usage_approved_invariants (a CHECK constraint, NOT the
        approved-key unique index) on approval. Passing
        actor_user_id="uq_drug_usage_approved_key" — a value that, under
        the old string-matching implementation, appeared verbatim in the
        rendered IntegrityError's bound-parameter list and caused a false
        positive — must have zero effect on the diagnostics-based
        implementation: the real IntegrityError must propagate
        completely unmapped."""
        db = session_factory()
        try:
            row = DrugUsage(
                drug_ingredient_id=ingredient["id"],
                locale="vi",
                audience="patient",
                content="missing provenance on purpose",
                authored_by="author-1",
                status="clinical_review",
                status_changed_by="author-1",
                status_changed_at=dt.datetime.now(dt.UTC),
                # source/version/evidence_level/reviewed_by/last_reviewed_at
                # intentionally omitted.
            )
            db.add(row)
            db.commit()

            with pytest.raises(IntegrityError) as exc_info:
                repo.approve_row(
                    db,
                    row,
                    actor_user_id="uq_drug_usage_approved_key",
                    actor_role="internal_admin",
                )
            assert not isinstance(exc_info.value, repo.TransitionError), (
                "a CHECK-constraint violation must never be reclassified as a "
                "TransitionError just because an unrelated bound parameter "
                "happens to contain the approved-key constraint's name"
            )
            assert exc_info.value.orig.diag.constraint_name == (
                "ck_drug_usage_approved_invariants"
            )
        finally:
            db.close()


class TestSameRowRaceProvesRealLockContention:
    """Codex round-2 P2-3: the same-row race test above (kept, still
    genuinely threaded) could in principle pass even under 100%
    sequential execution with zero real overlap — the outcome (one
    success, one TransitionError, final count=1) looks identical either
    way, so it doesn't actually PROVE contention occurred, only that the
    final state is correct regardless.

    This test goes further: it confirms, via a THIRD monitoring
    connection querying `pg_stat_activity`, that thread B's backend is
    GENUINELY blocked waiting on the row lock thread A holds — not
    inferred from timing or a `time.sleep()`. It calls the real
    `approve_row` production path for both threads; the only
    instrumentation is a pause inserted via monkeypatching
    `_lock_canonical_row` at the exact point its own `FOR UPDATE` lock
    would be held, so this test fails if that lock is ever removed (with
    no `FOR UPDATE`, thread B's SELECT would never block during the
    observed window, and the pg_stat_activity poll would time out
    finding no waiting backend).

    Codex round-4 P3: the poll used to filter only by
    `l.relation = 'drug_usage'::regclass` — any backend blocked on that
    relation would satisfy it, not necessarily thread B's own connection.
    Hardened: thread B's own `pg_backend_pid()` is captured directly from
    its own session (before it does anything else) and published to the
    main thread, which then polls `pg_stat_activity` filtered by that
    EXACT pid.
    """

    def test_thread_b_genuinely_blocks_on_thread_a_row_lock(
        self, session_factory, ingredient, monkeypatch
    ) -> None:
        db_setup = session_factory()
        try:
            row = _submitted_row(db_setup, ingredient["id"])
            row_id = row.id
        finally:
            db_setup.close()

        a_locked = threading.Event()
        release_a = threading.Event()
        b_pid_ready = threading.Event()
        b_pid_holder: dict[str, int] = {}
        original_lock_canonical_row = repo._lock_canonical_row

        def _instrumented_lock_canonical_row(db, model_cls, rid):
            canonical = original_lock_canonical_row(db, model_cls, rid)
            if db.info.get("test_thread") == "a":
                a_locked.set()
                release_a.wait(timeout=15)
            return canonical

        monkeypatch.setattr(repo, "_lock_canonical_row", _instrumented_lock_canonical_row)

        results: dict[str, tuple[str, object]] = {}

        def _thread_a() -> None:
            db = session_factory()
            db.info["test_thread"] = "a"
            try:
                row = db.get(DrugUsage, row_id)
                approved = repo.approve_row(
                    db, row, actor_user_id="reviewer-a", actor_role="internal_admin"
                )
                results["a"] = ("success", approved.status)
            except Exception as exc:  # noqa: BLE001 — cross-thread result capture only
                results["a"] = ("failure", exc)
            finally:
                db.close()

        def _thread_b() -> None:
            assert a_locked.wait(timeout=15), "thread A never reached the lock point"
            db = session_factory()
            try:
                # Publish this connection's own backend pid BEFORE doing
                # anything that could block, so the main thread can poll
                # pg_stat_activity for this EXACT backend (Codex round-4
                # P3) rather than any backend blocked on the relation.
                b_pid_holder["pid"] = db.execute(sa.text("SELECT pg_backend_pid()")).scalar()
                b_pid_ready.set()
                row = db.get(DrugUsage, row_id)
                # This call's own SELECT ... FOR UPDATE genuinely blocks
                # here in Postgres, waiting on the row lock thread A
                # holds — real DB-level contention, confirmed below via
                # pg_stat_activity, not assumed.
                approved = repo.approve_row(
                    db, row, actor_user_id="reviewer-b", actor_role="internal_admin"
                )
                results["b"] = ("success", approved.status)
            except Exception as exc:  # noqa: BLE001
                results["b"] = ("failure", exc)
            finally:
                db.close()

        thread_a = threading.Thread(target=_thread_a)
        thread_b = threading.Thread(target=_thread_b)
        thread_a.start()
        thread_b.start()

        try:
            assert a_locked.wait(timeout=15), "thread A never reached the lock point"
            assert b_pid_ready.wait(timeout=15), "thread B's backend pid was never published"
            b_pid = b_pid_holder["pid"]

            # Poll pg_stat_activity from a FRESH monitoring connection
            # until thread B's OWN backend (pinned by pid, not just "some"
            # backend blocked on the drug_usage relation — Codex round-4
            # P3) genuinely shows up waiting on a lock — the actual proof
            # of contention, not an inference from timing.
            monitor_db = session_factory()
            try:
                blocked_confirmed = False
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    waiting = monitor_db.execute(
                        sa.text(
                            "SELECT count(*) FROM pg_stat_activity a "
                            "WHERE a.pid = :pid "
                            "AND a.wait_event_type = 'Lock' "
                            "AND a.state = 'active'"
                        ),
                        {"pid": b_pid},
                    ).scalar()
                    monitor_db.rollback()
                    if waiting and waiting > 0:
                        blocked_confirmed = True
                        break
                    time.sleep(0.1)
                assert blocked_confirmed, (
                    f"thread B's own backend (pid={b_pid}) never appeared "
                    "genuinely blocked in pg_stat_activity within the "
                    "timeout — this test must observe real contention on "
                    "THAT exact connection, not infer it from timing or "
                    "from any backend on the table (it should fail exactly "
                    "like this if FOR UPDATE is ever removed from "
                    "_lock_canonical_row)"
                )
            finally:
                monitor_db.close()

            release_a.set()
        finally:
            # Always release A even if the pg_stat_activity assertion
            # above fails, so the threads below can still be joined and
            # cleaned up rather than hanging.
            release_a.set()

        thread_a.join(timeout=30)
        thread_b.join(timeout=30)

        assert not thread_a.is_alive() and not thread_b.is_alive(), (
            "a racing thread deadlocked or timed out"
        )
        assert set(results) == {"a", "b"}, f"both threads must report a result, got {results}"

        outcomes = {k: v[0] for k, v in results.items()}
        assert sorted(outcomes.values()) == ["failure", "success"], (
            f"exactly one of the two racing approvals must succeed, got {outcomes}"
        )
        loser_key = next(k for k, v in outcomes.items() if v == "failure")
        assert isinstance(results[loser_key][1], repo.TransitionError), (
            f"loser must fail with TransitionError, got {type(results[loser_key][1])}: "
            f"{results[loser_key][1]}"
        )

        verify_db = session_factory()
        try:
            approved_count = (
                verify_db.query(DrugUsage).filter_by(id=row_id, status="approved").count()
            )
            assert approved_count == 1, "exactly one session's approval must have won"
        finally:
            verify_db.close()


class TestRepeatedApprovalCyclesDoNotBlockMigrationDowngrade:
    """Regression, 2026-07-27 (test-isolation fix above): proves that
    cleaning up after each test actually keeps the shared, disposable
    mcp_test database clean enough for a REAL Alembic downgrade past
    k2_s0_lifecycle_transitions to succeed — not just that domain rows are
    gone. k2_s0_lifecycle_transitions.downgrade() refuses to run while
    `knowledge_lifecycle_transitions` holds any row (real append-only
    history); before the `ingredient` fixture's teardown fix, every
    submit_for_review/approve_row call in this module left rows behind
    there forever, so a second consecutive run (or the module's own final
    teardown) would eventually hit that RuntimeError guard.

    Runs a full create -> submit -> approve -> ID-scoped cleanup cycle
    TWICE in a row against the same schema (simulating two consecutive
    test-suite runs against the same disposable database), then performs
    the real downgrade past every Slice 0 revision and back to head. The
    downgrade raising RuntimeError is exactly the failure mode this test
    exists to catch.
    """

    def _one_full_cycle(self, session_factory: sessionmaker[Session], label: str) -> None:
        setup_db = session_factory()
        try:
            suffix = f"{label}-{uuid.uuid4().hex[:8]}"
            drug_class = DrugClass(name=f"repeat-class-{suffix}", required_specialties=[])
            setup_db.add(drug_class)
            setup_db.flush()
            ingredient_row = DrugIngredient(
                name_inn=f"repeat-ingredient-{suffix}", drug_class_id=drug_class.id
            )
            setup_db.add(ingredient_row)
            setup_db.commit()
            ingredient_id, drug_class_id = ingredient_row.id, drug_class.id
        finally:
            setup_db.close()

        approve_db = session_factory()
        try:
            row = _submitted_row(approve_db, ingredient_id)
            approved = repo.approve_row(
                approve_db, row, actor_user_id="reviewer-1", actor_role="internal_admin"
            )
            assert approved.status == "approved"
        finally:
            approve_db.close()

        cleanup_db = session_factory()
        try:
            _delete_lifecycle_transitions_for_ingredient(cleanup_db, ingredient_id)
            cleanup_db.execute(
                sa.text("DELETE FROM drug_usage WHERE drug_ingredient_id = :ingredient_id"),
                {"ingredient_id": ingredient_id},
            )
            cleanup_db.execute(
                sa.text("DELETE FROM drug_ingredients WHERE id = :ingredient_id"),
                {"ingredient_id": ingredient_id},
            )
            cleanup_db.execute(
                sa.text("DELETE FROM drug_classes WHERE id = :drug_class_id"),
                {"drug_class_id": drug_class_id},
            )
            cleanup_db.commit()
        except Exception:
            cleanup_db.rollback()
            raise
        finally:
            cleanup_db.close()

    def test_two_consecutive_cycles_leave_downgrade_unblocked(
        self, session_factory: sessionmaker[Session], migrated_schema: sa.Engine
    ) -> None:
        self._one_full_cycle(session_factory, "run1")
        self._one_full_cycle(session_factory, "run2")

        db_url = migrated_schema.url.render_as_string(hide_password=False)
        cfg = _make_alembic_config(db_url)
        try:
            # Must not raise: if either cycle above left a row in
            # knowledge_lifecycle_transitions, this raises RuntimeError
            # (k2_s0_lifecycle_transitions.downgrade()'s own non-empty-table
            # guard) — the exact contamination this regression test exists
            # to prevent from recurring.
            command.downgrade(cfg, "k1_a1b_f2_specialty_seed")
        finally:
            # Always restore head, so this module's own migrated_schema
            # fixture (and any test running after this one) is unaffected.
            command.upgrade(cfg, "head")
