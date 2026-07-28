"""Unit tests for K1.6: Approved Medication Knowledge Retrieval Contract.

Business-logic tests (not SQL-dialect-specific), run against the shared
SQLite test DB via the existing `db` fixture (tests/conftest.py) — no
PostgreSQL integration marker needed here, unlike
tests/integration/test_medication_k1_6_knowledge_retrieval_postgres.py.

All rows are synthetic test fixtures — never real clinical content.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from app.core.database import SessionLocal
from app.models.drug_knowledge_content import (
    DrugContraindication,
    DrugMonitoring,
    DrugPatientEducation,
    DrugSideEffect,
    DrugUsage,
)
from app.models.drug_knowledge_core import DrugClass, DrugIngredient, DrugProduct
from app.models.drug_knowledge_references import DrugReference, KnowledgeReferenceLink
from app.services import knowledge_repository as repo
from app.services import knowledge_retrieval as retrieval
from sqlalchemy import event

_ALL_KNOWLEDGE_MODELS = [
    DrugUsage,
    DrugPatientEducation,
    DrugSideEffect,
    DrugMonitoring,
    DrugContraindication,
]

_ROLE = "internal_admin"


def _make_ingredient(db, *, drug_class_id: str | None = None) -> DrugIngredient:
    suffix = uuid.uuid4().hex[:8]
    if drug_class_id is None:
        drug_class = DrugClass(name=f"test-class-{suffix}", required_specialties=[])
        db.add(drug_class)
        db.flush()
        drug_class_id = drug_class.id
    ingredient = DrugIngredient(name_inn=f"test-ingredient-{suffix}", drug_class_id=drug_class_id)
    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)
    return ingredient


def _approval_provenance_fields() -> dict[str, object]:
    """ck_<table>_approved_invariants requires reviewed_by/evidence_level/
    source/version/last_reviewed_at to be non-null once a row reaches
    'approved'. Synthetic placeholder values only.

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


def _model_fields(model_cls: type, ingredient_id: str, *, variant: str = "v1") -> dict[str, object]:
    """Field factory for building a valid content row for any of the 5
    in-scope models. Business-key fields are fixed per call; `variant` only
    ever touches a non-business-key field, so two calls with the same
    ingredient_id and variant share one business key (used for supersession
    setup) while two calls with different ingredient_id never do."""
    base: dict[str, object] = dict(drug_ingredient_id=ingredient_id, **_approval_provenance_fields())
    if model_cls is DrugUsage:
        return {**base, "locale": "vi", "audience": "patient", "content": f"content-{variant}"}
    if model_cls is DrugPatientEducation:
        return {
            **base,
            "theme": "general",
            "locale": "vi",
            "audience": "patient",
            "content": f"content-{variant}",
        }
    if model_cls is DrugSideEffect:
        return {
            **base,
            "concept_code": "nausea",
            "label": "Nausea",
            "frequency": "common",
            "action_level": "self_monitor",
            "description": f"description-{variant}",
        }
    if model_cls is DrugMonitoring:
        return {
            **base,
            "parameter": "renal_function",
            "patient_context": "baseline",
            "guidance": f"guidance-{variant}",
        }
    if model_cls is DrugContraindication:
        return {
            **base,
            "condition_type": "disease",
            "condition_key": "ckd_stage4",
            "condition_detail": f"detail-{variant}",
        }
    raise ValueError(f"unsupported model_cls: {model_cls!r}")


class _partial_index_temporarily_dropped:
    """The 'approved' partial unique index (`uq_drug_usage_approved_key`)
    genuinely prevents ever persisting two 'approved' rows for the same
    business key — in SQLite exactly as in real Postgres. That makes the
    otherwise-impossible state `MultipleApprovedRowsError` defends against
    impossible to construct via a normal bypass INSERT (verified directly:
    the naive version of this test's INSERT raised IntegrityError from the
    real index before this module's own code ever ran). This context
    manager drops the index, lets the test construct the impossible state
    on purpose, then unconditionally recreates it — proving this module's
    defense-in-depth check is reachable and correct, without weakening the
    real DB-level backstop for anything else in the shared, session-scoped
    test session.

    Codex Round 1, P1-3: `__exit__` itself now removes any row that would
    violate the constraint (a defensive `DELETE ... WHERE (cols) IN (SELECT
    cols ... GROUP BY cols HAVING COUNT(*) > 1)`, portable across SQLite and
    Postgres) BEFORE attempting to recreate the index — it no longer trusts
    the test body to have already cleaned up. Previously, if the test
    body's own inline cleanup (delete-then-continue) ever failed or was
    skipped — e.g. the `with pytest.raises(...)` block itself failing
    because the code under test regressed and stopped raising — the
    `CREATE UNIQUE INDEX` statement below would fail against the still-
    duplicate data, silently leaving this index dropped for the REST of
    this session-scoped SQLite file (every later test in the whole suite,
    not just this file, depending on this index). `CREATE UNIQUE INDEX ...
    IF NOT EXISTS` adds a second layer of safety (idempotent, in case
    something upstream already recreated it)."""

    def __init__(self, db, *, index_name: str, table: str, columns: tuple[str, ...]):
        self.db = db
        self.index_name = index_name
        self.table = table
        self.columns = columns

    def __enter__(self):
        self.db.execute(sa.text(f"DROP INDEX {self.index_name}"))
        self.db.commit()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Discard any failed-transaction state left by the test body (e.g.
        # a raised-but-uncaught DB error) before issuing further statements
        # — a no-op on SQLite's autocommit-per-statement DDL, but keeps
        # this safe if ever reused against a dialect where it matters.
        self.db.rollback()
        columns_sql = ", ".join(self.columns)
        # Defense-in-depth: unconditionally remove any row that would still
        # violate the constraint, regardless of whether the test body's own
        # cleanup ran or succeeded — recreation below must never be skipped
        # just because the body didn't get a chance to clean up.
        self.db.execute(
            sa.text(
                f"DELETE FROM {self.table} WHERE status = 'approved' AND "
                f"({columns_sql}) IN ("
                f"SELECT {columns_sql} FROM {self.table} WHERE status = 'approved' "
                f"GROUP BY {columns_sql} HAVING COUNT(*) > 1)"
            )
        )
        self.db.commit()
        self.db.execute(
            sa.text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {self.index_name} ON {self.table} "
                f"({columns_sql}) WHERE status = 'approved'"
            )
        )
        self.db.commit()
        return False


def _approved_row(db, model_cls: type, ingredient_id: str, *, variant: str = "v1", **overrides):
    """Create-draft -> submit -> approve, through the real K1.5 write path
    (never a direct INSERT with status='approved' — proves this module's
    reads only ever see rows that reached 'approved' the real way, except
    in the dedicated bypass/backstop tests below)."""
    fields = _model_fields(model_cls, ingredient_id, variant=variant)
    fields.update(overrides)
    row = repo.create_draft(db, model_cls, authored_by="author-1", **fields)
    repo.submit_for_review(db, row, actor_user_id="author-1")
    return repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=_ROLE)


@pytest.fixture(autouse=True)
def _cleanup_all_knowledge_rows(db):
    """The `db` fixture (tests/conftest.py) has no per-test rollback — a
    plain session on a shared, session-scoped SQLite file. Every test in
    this module creates real 'approved' rows via the real write path, which
    would otherwise persist and break other files' global
    `count(status='approved') == 0` assertions (same reasoning as
    knowledge_repository's own TestApproveRow._cleanup_approved_rows)."""
    existing_ids = {m: {row.id for row in db.query(m.id).all()} for m in _ALL_KNOWLEDGE_MODELS}
    existing_reference_ids = {row.id for row in db.query(DrugReference.id).all()}
    existing_link_ids = {row.id for row in db.query(KnowledgeReferenceLink.id).all()}
    yield
    db.rollback()
    for row in db.query(KnowledgeReferenceLink).filter(
        ~KnowledgeReferenceLink.id.in_(existing_link_ids)
    ).all():
        db.delete(row)
    for row in db.query(DrugReference).filter(~DrugReference.id.in_(existing_reference_ids)).all():
        db.delete(row)
    for m in _ALL_KNOWLEDGE_MODELS:
        for row in db.query(m).filter(~m.id.in_(existing_ids[m])).all():
            db.delete(row)
    db.commit()


class TestGetCurrentByBusinessKey:
    @pytest.mark.parametrize("model_cls", _ALL_KNOWLEDGE_MODELS)
    def test_happy_path_returns_approved_row(self, db, model_cls) -> None:
        ingredient = _make_ingredient(db)
        approved = _approved_row(db, model_cls, ingredient.id)
        business_key = {
            f: getattr(approved, f) for f in retrieval._BUSINESS_KEY_FIELDS[model_cls]
        }
        found = retrieval.get_current_by_business_key(db, model_cls, **business_key)
        assert found is not None
        assert found.id == approved.id
        assert found.status == "approved"

    def test_zero_approved_rows_returns_none(self, db) -> None:
        ingredient = _make_ingredient(db)
        found = retrieval.get_current_by_business_key(
            db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi", audience="patient"
        )
        assert found is None

    def test_draft_row_not_returned(self, db) -> None:
        ingredient = _make_ingredient(db)
        repo.create_draft(db, DrugUsage, authored_by="author-1", **_model_fields(DrugUsage, ingredient.id))
        found = retrieval.get_current_by_business_key(
            db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi", audience="patient"
        )
        assert found is None

    def test_clinical_review_row_not_returned(self, db) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db, DrugUsage, authored_by="author-1", **_model_fields(DrugUsage, ingredient.id)
        )
        repo.submit_for_review(db, row, actor_user_id="author-1")
        found = retrieval.get_current_by_business_key(
            db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi", audience="patient"
        )
        assert found is None

    def test_deprecated_row_not_returned_only_current_approved_is(self, db) -> None:
        ingredient = _make_ingredient(db)
        first = _approved_row(db, DrugUsage, ingredient.id, variant="v1")
        second = _approved_row(db, DrugUsage, ingredient.id, variant="v2")
        db.refresh(first)
        assert first.status == "deprecated"

        found = retrieval.get_current_by_business_key(
            db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi", audience="patient"
        )
        assert found is not None
        assert found.id == second.id

    def test_retired_row_not_returned(self, db) -> None:
        ingredient = _make_ingredient(db)
        first = _approved_row(db, DrugUsage, ingredient.id, variant="v1")
        _approved_row(db, DrugUsage, ingredient.id, variant="v2")
        db.refresh(first)
        retired = repo.retire_row(db, first, actor_user_id="reviewer-1", actor_role=_ROLE)
        assert retired.status == "retired"

        found = retrieval.get_current_by_business_key(
            db, DrugUsage, drug_ingredient_id=retired.drug_ingredient_id, locale="vi", audience="patient"
        )
        assert found is not None
        assert found.id != retired.id

    def test_unknown_business_key_field_raises(self, db) -> None:
        ingredient = _make_ingredient(db)
        with pytest.raises(retrieval.UnknownBusinessKeyFieldError):
            retrieval.get_current_by_business_key(
                db,
                DrugUsage,
                drug_ingredient_id=ingredient.id,
                locale="vi",
                audience="patient",
                bogus_field="x",
            )

    def test_missing_business_key_field_raises(self, db) -> None:
        ingredient = _make_ingredient(db)
        with pytest.raises(retrieval.MissingBusinessKeyFieldError):
            retrieval.get_current_by_business_key(
                db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi"
            )

    def test_multiple_approved_rows_raises(self, db) -> None:
        """Constructs an otherwise-impossible state (two 'approved' rows
        sharing one full business key) by temporarily dropping the real
        partial unique index that normally prevents it — proves this
        module fails closed rather than silently picking one."""
        ingredient = _make_ingredient(db)
        now = dt.datetime.now(dt.UTC)
        with _partial_index_temporarily_dropped(
            db,
            index_name="uq_drug_usage_approved_key",
            table="drug_usage",
            columns=("drug_ingredient_id", "locale", "audience"),
        ):
            for variant in ("a", "b"):
                row = DrugUsage(
                    drug_ingredient_id=ingredient.id,
                    locale="vi",
                    audience="patient",
                    content=f"bypass-{variant}",
                    authored_by="author-1",
                    status="approved",
                    status_changed_by="author-1",
                    status_changed_at=now,
                    # reviewed_by is supplied directly here (not via
                    # _approval_provenance_fields(), which no longer
                    # includes it — fix round 1, Codex Round 1 finding #6)
                    # because this test bypasses approve_row entirely to
                    # construct an otherwise-impossible already-approved
                    # row directly.
                    reviewed_by="reviewer-1",
                    **_approval_provenance_fields(),
                )
                db.add(row)
            db.commit()

            with pytest.raises(retrieval.MultipleApprovedRowsError):
                retrieval.get_current_by_business_key(
                    db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi", audience="patient"
                )
            # No manual cleanup here on purpose (Codex Round 1, P1-3):
            # `_partial_index_temporarily_dropped.__exit__` now defensively
            # removes any constraint-violating row itself before recreating
            # the index, so recreation no longer depends on this test body
            # having cleaned up first — even if the assertion above had
            # failed instead of raising.

    def test_draft_row_forged_to_approved_in_memory_is_still_not_returned(self, db) -> None:
        """A draft row already attached to this session, forged in-memory to
        status='approved' (never flushed/committed), must never be
        returned. This alone is guaranteed by the SQL-level `status`
        filter — the forged value is never sent to the DB (autoflush is
        off) so the WHERE clause itself excludes it regardless of
        `.populate_existing()`. Kept as a basic sanity check; the REAL
        identity-map-staleness proof is the non-filtered-field test below."""
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db, DrugUsage, authored_by="author-1", **_model_fields(DrugUsage, ingredient.id)
        )
        row.status = "approved"  # forged in-memory only, never flushed/committed

        found = retrieval.get_current_by_business_key(
            db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi", audience="patient"
        )
        assert found is None, "the forged in-memory status must never be observed as approved"

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row.id)
            assert persisted.status == "draft", "the forged mutation must never have been persisted"
        finally:
            fresh.close()

    def test_identity_map_staleness_does_not_leak_forged_non_filtered_field(self, db) -> None:
        """The real identity-map-staleness risk: a GENUINELY approved row
        already attached to this session, with a NON-filtered field
        (`content`) forged in-memory (never flushed/committed). Without
        `.populate_existing()`, SQLAlchemy's default query behavior would
        return the SAME cached Python object without overwriting the
        already-loaded (forged) attribute from the fresh query result —
        proven directly below by the break-test technique documented in
        the K1.6 implementation report; this test asserts the real,
        persisted content is what callers observe, never the forged one."""
        ingredient = _make_ingredient(db)
        approved = _approved_row(db, DrugUsage, ingredient.id, variant="real")
        approved.content = "forged in-memory content — never persisted"  # never flushed/committed

        found = retrieval.get_current_by_business_key(
            db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi", audience="patient"
        )
        assert found is not None
        assert found.content == "content-real", (
            "the forged in-memory content must never leak through a fresh read — "
            f"got {found.content!r}"
        )

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, approved.id)
            assert persisted.content == "content-real", (
                "the forged mutation must never have been persisted"
            )
        finally:
            fresh.close()

    def test_read_does_not_commit_pending_session_state(self, db) -> None:
        """The real invariant (Codex Round 1, P1-2): a read must never
        commit the caller's own pending, unrelated, unflushed changes. The
        previous version of this test asserted `not X or X` — a tautology,
        true for every possible value of `db.in_transaction()`, which
        verified nothing. Worse, its underlying premise ("no open
        transaction after a read") is actually FALSE in general: SQLAlchemy
        autobegins a transaction on any SELECT (verified directly:
        `db.in_transaction()` flips `False -> True` across a single
        `get_current_by_business_key` call on a fresh session) — so a
        literal "no open transaction" assertion would have failed for a
        completely benign reason had it not been a no-op. Replaced with the
        invariant that actually matters: no accidental commit of unrelated
        pending state."""
        ingredient = _make_ingredient(db)
        _approved_row(db, DrugUsage, ingredient.id)

        pending_name = f"pending-class-{uuid.uuid4().hex[:8]}"
        pending = DrugClass(name=pending_name, required_specialties=[])
        db.add(pending)  # deliberately never flushed/committed

        retrieval.get_current_by_business_key(
            db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi", audience="patient"
        )

        assert pending in db.new, (
            "a read call must never flush/commit unrelated pending session state"
        )
        fresh = SessionLocal()
        try:
            assert fresh.query(DrugClass).filter_by(name=pending_name).count() == 0, (
                "the pending DrugClass must never have been persisted by a read call"
            )
        finally:
            fresh.close()

    def test_session_remains_usable_after_multiple_approved_rows_error(self, db) -> None:
        """`MultipleApprovedRowsError` is raised in pure Python after the
        query has already completed successfully — it must never leave the
        session in a broken/unusable state for whatever the caller does
        next. Reuses the same forced-violation technique as
        test_multiple_approved_rows_raises."""
        ingredient = _make_ingredient(db)
        now = dt.datetime.now(dt.UTC)
        with _partial_index_temporarily_dropped(
            db,
            index_name="uq_drug_usage_approved_key",
            table="drug_usage",
            columns=("drug_ingredient_id", "locale", "audience"),
        ):
            for variant in ("a", "b"):
                row = DrugUsage(
                    drug_ingredient_id=ingredient.id,
                    locale="vi",
                    audience="patient",
                    content=f"bypass-{variant}",
                    authored_by="author-1",
                    status="approved",
                    status_changed_by="author-1",
                    status_changed_at=now,
                    # reviewed_by is supplied directly here (not via
                    # _approval_provenance_fields(), which no longer
                    # includes it — fix round 1, Codex Round 1 finding #6)
                    # because this test bypasses approve_row entirely to
                    # construct an otherwise-impossible already-approved
                    # row directly.
                    reviewed_by="reviewer-1",
                    **_approval_provenance_fields(),
                )
                db.add(row)
            db.commit()

            with pytest.raises(retrieval.MultipleApprovedRowsError):
                retrieval.get_current_by_business_key(
                    db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi", audience="patient"
                )

            # The session must still be perfectly usable immediately after
            # — proves the exception never left it in a failed/aborted
            # state (a real concern under Postgres, where a genuine DB-level
            # error aborts the transaction until rollback; this exception is
            # pure Python, raised after the query already succeeded, so it
            # must not have that effect).
            other_ingredient = _make_ingredient(db)
            found = retrieval.get_current_by_business_key(
                db, DrugUsage, drug_ingredient_id=other_ingredient.id, locale="vi", audience="patient"
            )
            assert found is None


class TestListCurrentForIngredient:
    def test_returns_only_approved_excludes_other_statuses(self, db) -> None:
        ingredient = _make_ingredient(db)
        approved = _approved_row(db, DrugSideEffect, ingredient.id, concept_code="nausea")
        repo.create_draft(
            db,
            DrugSideEffect,
            authored_by="author-1",
            **{**_model_fields(DrugSideEffect, ingredient.id, variant="draft-only"), "concept_code": "dizziness"},
        )
        results = retrieval.list_current_for_ingredient(db, DrugSideEffect, ingredient.id)
        assert [r.id for r in results] == [approved.id]

    def test_cross_ingredient_rows_excluded(self, db) -> None:
        ingredient_a = _make_ingredient(db)
        ingredient_b = _make_ingredient(db)
        approved_a = _approved_row(db, DrugUsage, ingredient_a.id)
        _approved_row(db, DrugUsage, ingredient_b.id)

        results = retrieval.list_current_for_ingredient(db, DrugUsage, ingredient_a.id)
        assert [r.id for r in results] == [approved_a.id]

    def test_deterministic_ordering_by_secondary_business_key(self, db) -> None:
        ingredient = _make_ingredient(db)

        def _side_effect(concept_code: str):
            fields = _model_fields(DrugSideEffect, ingredient.id)
            fields["concept_code"] = concept_code
            row = repo.create_draft(db, DrugSideEffect, authored_by="author-1", **fields)
            repo.submit_for_review(db, row, actor_user_id="author-1")
            return repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=_ROLE)

        # Inserted out of alphabetical order on purpose.
        _side_effect("zzz_last")
        _side_effect("aaa_first")
        _side_effect("mmm_middle")

        results_1 = retrieval.list_current_for_ingredient(db, DrugSideEffect, ingredient.id)
        results_2 = retrieval.list_current_for_ingredient(db, DrugSideEffect, ingredient.id)
        codes = [r.concept_code for r in results_1]
        assert codes == ["aaa_first", "mmm_middle", "zzz_last"]
        assert [r.id for r in results_1] == [r.id for r in results_2]

    def test_deterministic_ordering_for_three_field_secondary_key_model(self, db) -> None:
        """Codex Round 1, P2-2: the ordering test above only ever exercises
        DrugSideEffect's 1-field secondary key (`concept_code`).
        DrugPatientEducation's secondary key has 3 fields (`theme, locale,
        audience`) — this proves `_secondary_key_columns`'s tuple-ordering
        logic holds for that shape too, including the tiebreaker chain
        (two rows share the same `theme`, differing only on `locale`)."""
        ingredient = _make_ingredient(db)

        def _education(theme: str, locale: str = "vi", audience: str = "patient"):
            fields = _model_fields(DrugPatientEducation, ingredient.id)
            fields.update(theme=theme, locale=locale, audience=audience)
            row = repo.create_draft(db, DrugPatientEducation, authored_by="author-1", **fields)
            repo.submit_for_review(db, row, actor_user_id="author-1")
            return repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=_ROLE)

        # Inserted out of order on purpose.
        _education("zzz_theme")
        _education("aaa_theme", locale="vi")
        _education("aaa_theme", locale="en")

        results = retrieval.list_current_for_ingredient(db, DrugPatientEducation, ingredient.id)
        keys = [(r.theme, r.locale, r.audience) for r in results]
        assert keys == [
            ("aaa_theme", "en", "patient"),
            ("aaa_theme", "vi", "patient"),
            ("zzz_theme", "vi", "patient"),
        ]

    def test_no_approved_rows_returns_empty_list(self, db) -> None:
        ingredient = _make_ingredient(db)
        assert retrieval.list_current_for_ingredient(db, DrugUsage, ingredient.id) == []

    # Codex Round 2, P3-2: one row of secondary-key overrides per model,
    # ordered so the FIRST element sorts alphabetically before the SECOND
    # — complements (doesn't duplicate) the two existing dedicated
    # ordering tests above (DrugSideEffect's 1-field key,
    # DrugPatientEducation's 3-field tiebreaker) by also covering the
    # three previously-untested 2-field-secondary-key models plus DrugUsage,
    # in a single parametrized test rather than 5 near-identical ones.
    _ORDERED_SECONDARY_KEY_PAIRS: dict[type, tuple[dict, dict]] = {
        DrugUsage: ({"locale": "en", "audience": "patient"}, {"locale": "vi", "audience": "patient"}),
        DrugPatientEducation: (
            {"theme": "aaa_theme", "locale": "vi", "audience": "patient"},
            {"theme": "zzz_theme", "locale": "vi", "audience": "patient"},
        ),
        DrugSideEffect: ({"concept_code": "aaa_code"}, {"concept_code": "zzz_code"}),
        DrugMonitoring: (
            {"parameter": "aaa_param", "patient_context": "baseline"},
            {"parameter": "zzz_param", "patient_context": "baseline"},
        ),
        DrugContraindication: (
            {"condition_type": "aaa_type", "condition_key": "k"},
            {"condition_type": "zzz_type", "condition_key": "k"},
        ),
    }

    @pytest.mark.parametrize("model_cls", _ALL_KNOWLEDGE_MODELS)
    def test_deterministic_ordering_across_all_models(self, db, model_cls) -> None:
        ingredient = _make_ingredient(db)
        first_key, second_key = self._ORDERED_SECONDARY_KEY_PAIRS[model_cls]

        def _approve(overrides: dict):
            fields = {**_model_fields(model_cls, ingredient.id), **overrides}
            row = repo.create_draft(db, model_cls, authored_by="author-1", **fields)
            repo.submit_for_review(db, row, actor_user_id="author-1")
            return repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=_ROLE)

        # Inserted out of order on purpose (second key first).
        second_row = _approve(second_key)
        first_row = _approve(first_key)

        results = retrieval.list_current_for_ingredient(db, model_cls, ingredient.id)
        assert [r.id for r in results] == [first_row.id, second_row.id]


class TestListCurrentForDrugClass:
    @pytest.mark.parametrize("model_cls", _ALL_KNOWLEDGE_MODELS)
    def test_includes_all_ingredients_directly_in_class(self, db, model_cls) -> None:
        """Codex Round 1, P2-2: previously only ever exercised DrugUsage —
        parametrized across all 5 models so a model-specific business-key/
        secondary-column bug (e.g. DrugPatientEducation's 3-field
        secondary key) can't hide behind DrugUsage's simpler 2-field one."""
        drug_class = DrugClass(name=f"test-class-{uuid.uuid4().hex[:8]}", required_specialties=[])
        db.add(drug_class)
        db.commit()
        db.refresh(drug_class)

        ingredient_a = _make_ingredient(db, drug_class_id=drug_class.id)
        ingredient_b = _make_ingredient(db, drug_class_id=drug_class.id)
        other_class_ingredient = _make_ingredient(db)

        approved_a = _approved_row(db, model_cls, ingredient_a.id)
        approved_b = _approved_row(db, model_cls, ingredient_b.id)
        _approved_row(db, model_cls, other_class_ingredient.id)

        results = retrieval.list_current_for_drug_class(db, model_cls, drug_class.id)
        assert {r.id for r in results} == {approved_a.id, approved_b.id}

    def test_orders_by_ingredient_name_then_secondary_key(self, db) -> None:
        drug_class = DrugClass(name=f"test-class-{uuid.uuid4().hex[:8]}", required_specialties=[])
        db.add(drug_class)
        db.commit()
        db.refresh(drug_class)

        ingredient_z = DrugIngredient(name_inn=f"zzz-ingredient-{uuid.uuid4().hex[:8]}", drug_class_id=drug_class.id)
        ingredient_a = DrugIngredient(name_inn=f"aaa-ingredient-{uuid.uuid4().hex[:8]}", drug_class_id=drug_class.id)
        db.add_all([ingredient_z, ingredient_a])
        db.commit()
        db.refresh(ingredient_z)
        db.refresh(ingredient_a)

        approved_z = _approved_row(db, DrugUsage, ingredient_z.id)
        approved_a = _approved_row(db, DrugUsage, ingredient_a.id)

        results = retrieval.list_current_for_drug_class(db, DrugUsage, drug_class.id)
        assert [r.id for r in results] == [approved_a.id, approved_z.id]

    def test_no_recursion_into_child_classes(self, db) -> None:
        """A sub-class (parent_class_id pointing at the parent) is NOT
        rolled up — list_current_for_drug_class is non-recursive by
        design (see the function's own docstring)."""
        parent = DrugClass(name=f"parent-{uuid.uuid4().hex[:8]}", required_specialties=[])
        db.add(parent)
        db.commit()
        db.refresh(parent)
        child = DrugClass(
            name=f"child-{uuid.uuid4().hex[:8]}",
            required_specialties=[],
            parent_class_id=parent.id,
        )
        db.add(child)
        db.commit()
        db.refresh(child)

        parent_ingredient = _make_ingredient(db, drug_class_id=parent.id)
        child_ingredient = _make_ingredient(db, drug_class_id=child.id)
        approved_parent = _approved_row(db, DrugUsage, parent_ingredient.id)
        _approved_row(db, DrugUsage, child_ingredient.id)

        results = retrieval.list_current_for_drug_class(db, DrugUsage, parent.id)
        assert [r.id for r in results] == [approved_parent.id]


class TestGetCurrentBatch:
    @pytest.mark.parametrize("model_cls", _ALL_KNOWLEDGE_MODELS)
    def test_multiple_ingredients_grouped_correctly(self, db, model_cls) -> None:
        """Codex Round 1, P2-2: parametrized across all 5 models (was
        DrugUsage-only)."""
        ingredient_a = _make_ingredient(db)
        ingredient_b = _make_ingredient(db)
        approved_a = _approved_row(db, model_cls, ingredient_a.id)
        approved_b = _approved_row(db, model_cls, ingredient_b.id)

        result = retrieval.get_current_batch(db, model_cls, [ingredient_a.id, ingredient_b.id])
        assert [r.id for r in result[ingredient_a.id]] == [approved_a.id]
        assert [r.id for r in result[ingredient_b.id]] == [approved_b.id]

    def test_multiple_approved_rows_for_one_ingredient_all_included(self, db) -> None:
        """Codex Round 1, P2-4: every OTHER batch test has at most 1
        approved row per ingredient — this proves get_current_batch
        correctly returns and orders MULTIPLE approved rows for a single
        ingredient (the realistic ADR-07 shape: several approved side
        effects for one active-medication ingredient)."""
        ingredient = _make_ingredient(db)

        def _side_effect(concept_code: str):
            fields = _model_fields(DrugSideEffect, ingredient.id)
            fields["concept_code"] = concept_code
            row = repo.create_draft(db, DrugSideEffect, authored_by="author-1", **fields)
            repo.submit_for_review(db, row, actor_user_id="author-1")
            return repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=_ROLE)

        # Inserted out of alphabetical order on purpose.
        approved_z = _side_effect("zzz_last")
        approved_a = _side_effect("aaa_first")

        result = retrieval.get_current_batch(db, DrugSideEffect, [ingredient.id])
        assert [r.id for r in result[ingredient.id]] == [approved_a.id, approved_z.id]

    def test_ingredient_with_zero_approved_rows_present_with_empty_list(self, db) -> None:
        ingredient_with = _make_ingredient(db)
        ingredient_without = _make_ingredient(db)
        _approved_row(db, DrugUsage, ingredient_with.id)

        result = retrieval.get_current_batch(
            db, DrugUsage, [ingredient_with.id, ingredient_without.id]
        )
        assert ingredient_without.id in result
        assert result[ingredient_without.id] == []

    def test_duplicate_ingredient_ids_in_input_collapse_to_one_key(self, db) -> None:
        ingredient = _make_ingredient(db)
        approved = _approved_row(db, DrugUsage, ingredient.id)

        result = retrieval.get_current_batch(db, DrugUsage, [ingredient.id, ingredient.id])
        assert set(result.keys()) == {ingredient.id}
        assert [r.id for r in result[ingredient.id]] == [approved.id]

    def test_empty_input_returns_empty_dict(self, db) -> None:
        assert retrieval.get_current_batch(db, DrugUsage, []) == {}

    def test_inconsistent_state_fails_whole_batch(self, db) -> None:
        """A direct-INSERT bypass creates two approved rows sharing a full
        business key for one of the requested ingredients — the whole
        batch call must raise, not silently return partial/bad data for
        that ingredient."""
        ingredient_ok = _make_ingredient(db)
        ingredient_bad = _make_ingredient(db)
        approved_ok = _approved_row(db, DrugUsage, ingredient_ok.id)

        now = dt.datetime.now(dt.UTC)
        with _partial_index_temporarily_dropped(
            db,
            index_name="uq_drug_usage_approved_key",
            table="drug_usage",
            columns=("drug_ingredient_id", "locale", "audience"),
        ):
            for variant in ("a", "b"):
                row = DrugUsage(
                    drug_ingredient_id=ingredient_bad.id,
                    locale="vi",
                    audience="patient",
                    content=f"bypass-{variant}",
                    authored_by="author-1",
                    status="approved",
                    status_changed_by="author-1",
                    status_changed_at=now,
                    # reviewed_by supplied directly (see
                    # test_multiple_approved_rows_raises's comment).
                    reviewed_by="reviewer-1",
                    **_approval_provenance_fields(),
                )
                db.add(row)
            db.commit()

            with pytest.raises(retrieval.MultipleApprovedRowsError):
                retrieval.get_current_batch(db, DrugUsage, [ingredient_ok.id, ingredient_bad.id])
            # No manual cleanup here on purpose — see
            # test_multiple_approved_rows_raises's comment: __exit__ now
            # defensively cleans up constraint-violating rows itself.
        db.refresh(approved_ok)
        assert approved_ok.status == "approved"


class TestListReferencesFor:
    def _make_reference(self, db, **overrides) -> DrugReference:
        suffix = uuid.uuid4().hex[:8]
        fields = dict(
            publisher="Synthetic Publisher",
            title=f"Synthetic Title {suffix}",
            source_type="clinical_guideline",
            document_identifier=f"doc-{suffix}",
            publication_date=dt.date(2026, 1, 1),
            source_version="1.0",
            accessed_at=dt.date(2026, 1, 2),
        )
        fields.update(overrides)
        reference = DrugReference(**fields)
        db.add(reference)
        db.commit()
        db.refresh(reference)
        return reference

    def _link(self, db, *, model_cls, row_id, reference_id) -> None:
        link = KnowledgeReferenceLink(
            knowledge_table=retrieval.KNOWLEDGE_TABLE_NAME[model_cls],
            knowledge_row_id=row_id,
            drug_reference_id=reference_id,
        )
        db.add(link)
        db.commit()

    def test_zero_references_returns_empty_list(self, db) -> None:
        ingredient = _make_ingredient(db)
        approved = _approved_row(db, DrugUsage, ingredient.id)
        assert retrieval.list_references_for(db, DrugUsage, approved.id) == []

    def test_one_reference_returned(self, db) -> None:
        ingredient = _make_ingredient(db)
        approved = _approved_row(db, DrugUsage, ingredient.id)
        reference = self._make_reference(db)
        self._link(db, model_cls=DrugUsage, row_id=approved.id, reference_id=reference.id)

        results = retrieval.list_references_for(db, DrugUsage, approved.id)
        assert [r.id for r in results] == [reference.id]

    def test_many_to_many_one_reference_cited_by_multiple_rows(self, db) -> None:
        ingredient_a = _make_ingredient(db)
        ingredient_b = _make_ingredient(db)
        approved_a = _approved_row(db, DrugUsage, ingredient_a.id)
        approved_b = _approved_row(db, DrugUsage, ingredient_b.id)
        reference = self._make_reference(db)
        self._link(db, model_cls=DrugUsage, row_id=approved_a.id, reference_id=reference.id)
        self._link(db, model_cls=DrugUsage, row_id=approved_b.id, reference_id=reference.id)

        assert [r.id for r in retrieval.list_references_for(db, DrugUsage, approved_a.id)] == [
            reference.id
        ]
        assert [r.id for r in retrieval.list_references_for(db, DrugUsage, approved_b.id)] == [
            reference.id
        ]

    def test_does_not_cross_knowledge_table_boundary(self, db) -> None:
        """A reference linked under a DIFFERENT knowledge_table (but with
        the same raw row id, hypothetically) must never leak across —
        proves the polymorphic (table, row_id) filter is both conditions,
        not row_id alone."""
        ingredient = _make_ingredient(db)
        approved = _approved_row(db, DrugSideEffect, ingredient.id)
        reference = self._make_reference(db)
        self._link(db, model_cls=DrugMonitoring, row_id=approved.id, reference_id=reference.id)

        assert retrieval.list_references_for(db, DrugSideEffect, approved.id) == []

    def test_batch_returns_per_row_grouping_and_empty_for_uncited_rows(self, db) -> None:
        ingredient_a = _make_ingredient(db)
        ingredient_b = _make_ingredient(db)
        approved_a = _approved_row(db, DrugUsage, ingredient_a.id)
        approved_b = _approved_row(db, DrugUsage, ingredient_b.id)
        reference = self._make_reference(db)
        self._link(db, model_cls=DrugUsage, row_id=approved_a.id, reference_id=reference.id)

        result = retrieval.list_references_for_batch(
            db, DrugUsage, [approved_a.id, approved_b.id]
        )
        assert [r.id for r in result[approved_a.id]] == [reference.id]
        assert result[approved_b.id] == []

    def test_batch_empty_input_returns_empty_dict(self, db) -> None:
        assert retrieval.list_references_for_batch(db, DrugUsage, []) == {}


class TestListReferencesForIdentityBasedLookupContract:
    """Codex Round 1, P1-1 -> PTH review: `list_references_for`/
    `list_references_for_batch` are a deliberate **identity-based
    provenance lookup** — they do NOT verify the referenced row's
    lifecycle status or existence (see the functions' own docstrings,
    Option A). These tests make that decision explicit and
    regression-proof: previously this behavior was real but completely
    undocumented and untested, discovered only via ad hoc reproduction
    during Codex Round 1."""

    def _make_reference(self, db, **overrides) -> DrugReference:
        suffix = uuid.uuid4().hex[:8]
        fields = dict(
            publisher="Synthetic Publisher",
            title=f"Synthetic Title {suffix}",
            source_type="clinical_guideline",
            document_identifier=f"doc-{suffix}",
            publication_date=dt.date(2026, 1, 1),
            source_version="1.0",
            accessed_at=dt.date(2026, 1, 2),
        )
        fields.update(overrides)
        reference = DrugReference(**fields)
        db.add(reference)
        db.commit()
        db.refresh(reference)
        return reference

    def _link(self, db, *, model_cls, row_id, reference_id) -> None:
        link = KnowledgeReferenceLink(
            knowledge_table=retrieval.KNOWLEDGE_TABLE_NAME[model_cls],
            knowledge_row_id=row_id,
            drug_reference_id=reference_id,
        )
        db.add(link)
        db.commit()

    def test_returns_citation_for_a_draft_row(self, db) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db, DrugUsage, authored_by="author-1", **_model_fields(DrugUsage, ingredient.id)
        )
        reference = self._make_reference(db)
        self._link(db, model_cls=DrugUsage, row_id=row.id, reference_id=reference.id)

        results = retrieval.list_references_for(db, DrugUsage, row.id)
        assert [r.id for r in results] == [reference.id], (
            "identity-based lookup: citations are returned regardless of "
            "the underlying row's lifecycle status (documented contract, "
            "not a bug)"
        )

    def test_returns_citation_for_a_deprecated_row(self, db) -> None:
        ingredient = _make_ingredient(db)
        first = _approved_row(db, DrugUsage, ingredient.id, variant="v1")
        _approved_row(db, DrugUsage, ingredient.id, variant="v2")
        db.refresh(first)
        assert first.status == "deprecated"
        reference = self._make_reference(db)
        self._link(db, model_cls=DrugUsage, row_id=first.id, reference_id=reference.id)

        results = retrieval.list_references_for(db, DrugUsage, first.id)
        assert [r.id for r in results] == [reference.id]

    def test_returns_empty_list_for_a_nonexistent_row_id(self, db) -> None:
        """No link exists for this id -> empty list, same as any other
        "no citations" case. This function never checks whether the row
        itself exists."""
        assert (
            retrieval.list_references_for(db, DrugUsage, "00000000-0000-0000-0000-000000000000")
            == []
        )


class TestUnsupportedKnowledgeModel:
    """Codex Round 1, P2-1: every public function must fail the SAME way
    (`UnsupportedKnowledgeModelError`) for a `model_cls` outside the 5
    supported models. Before this fix: a non-empty call raised a bare
    `KeyError` (not part of this module's exception taxonomy), while
    `get_current_batch`/`list_references_for_batch` called with an EMPTY
    id list skipped validation entirely and silently returned `{}` —
    indistinguishable from "no approved knowledge exists" for a caller
    that passed the wrong model_cls entirely."""

    class _NotAKnowledgeModel:
        pass

    def test_get_current_by_business_key(self, db) -> None:
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.get_current_by_business_key(
                db, self._NotAKnowledgeModel, drug_ingredient_id="x"
            )

    def test_list_current_for_ingredient(self, db) -> None:
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.list_current_for_ingredient(db, self._NotAKnowledgeModel, "x")

    def test_list_current_for_drug_class(self, db) -> None:
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.list_current_for_drug_class(db, self._NotAKnowledgeModel, "x")

    def test_get_current_batch_nonempty_input(self, db) -> None:
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.get_current_batch(db, self._NotAKnowledgeModel, ["x"])

    def test_get_current_batch_empty_input_still_validates(self, db) -> None:
        """Regression: previously returned `{}` silently for an empty
        list, without ever checking `model_cls` (the bug this class
        exists to close)."""
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.get_current_batch(db, self._NotAKnowledgeModel, [])

    def test_list_references_for(self, db) -> None:
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.list_references_for(db, self._NotAKnowledgeModel, "x")

    def test_list_references_for_batch_nonempty_input(self, db) -> None:
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.list_references_for_batch(db, self._NotAKnowledgeModel, ["x"])

    def test_list_references_for_batch_empty_input_still_validates(self, db) -> None:
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.list_references_for_batch(db, self._NotAKnowledgeModel, [])

    @pytest.mark.parametrize(
        "malformed_model_cls",
        [
            pytest.param(["not", "a", "class"], id="unhashable-list"),
            pytest.param({"not": "a class"}, id="unhashable-dict"),
            pytest.param(DrugUsage(), id="orm-instance-of-a-supported-model"),
            pytest.param(object(), id="plain-object-instance"),
        ],
    )
    def test_malformed_non_class_model_cls_raises_on_every_function(
        self, db, malformed_model_cls
    ) -> None:
        """Codex Round 2, P2-1: a non-class, possibly non-hashable
        `model_cls` (a list, a dict, an INSTANCE instead of a class) must
        raise the SAME `UnsupportedKnowledgeModelError` as any other
        unsupported input on every one of the 6 public functions — never a
        bare `TypeError` (the previous behavior for unhashable inputs,
        since the old code went straight to `model_cls not in
        _BUSINESS_KEY_FIELDS` without first checking `isinstance(model_cls,
        type)`)."""
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.get_current_by_business_key(db, malformed_model_cls, drug_ingredient_id="x")
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.list_current_for_ingredient(db, malformed_model_cls, "x")
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.list_current_for_drug_class(db, malformed_model_cls, "x")
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.get_current_batch(db, malformed_model_cls, ["x"])
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.list_references_for(db, malformed_model_cls, "x")
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.list_references_for_batch(db, malformed_model_cls, ["x"])

    def test_unrelated_real_orm_class_raises(self, db) -> None:
        """A genuine, unrelated mapped ORM class (`DrugProduct` — real,
        hashable, not a stand-in) must also fail closed — proves the check
        is a real membership test against the 5 supported models, not just
        "is this a plain Python class"."""
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.get_current_by_business_key(db, DrugProduct, drug_ingredient_id="x")

    def test_get_current_batch_empty_input_with_malformed_model_still_validates(self, db) -> None:
        """Codex Round 2: at least one empty-batch case with a MALFORMED
        (non-class, unhashable) model_cls, not just an
        unsupported-but-otherwise-valid class."""
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.get_current_batch(db, ["not", "a", "class"], [])

    def test_list_references_for_batch_empty_input_with_malformed_model_still_validates(
        self, db
    ) -> None:
        with pytest.raises(retrieval.UnsupportedKnowledgeModelError):
            retrieval.list_references_for_batch(db, ["not", "a", "class"], [])

    def test_supported_models_all_pass_validation(self, db) -> None:
        """The flip side: none of the 5 real supported models are ever
        mistakenly rejected by the new isinstance/membership checks."""
        for model_cls in _ALL_KNOWLEDGE_MODELS:
            retrieval._require_supported_model(model_cls)  # must not raise

    def test_error_message_is_deterministic_and_has_no_memory_address(self, db) -> None:
        """The message must be identical across repeated calls (no
        instance-repr-style `at 0x...` memory address) and must name the
        received type / the 5 supported models."""
        import re

        messages = set()
        for _ in range(3):
            try:
                retrieval.get_current_by_business_key(
                    db, DrugUsage(), drug_ingredient_id="x"
                )
            except retrieval.UnsupportedKnowledgeModelError as exc:
                messages.add(str(exc))
        assert len(messages) == 1, f"error message is not deterministic: {messages}"
        message = next(iter(messages))
        assert not re.search(r"0x[0-9a-fA-F]+", message), (
            f"error message must never embed a memory address: {message!r}"
        )
        assert "DrugUsage" in message
        for name in ("DrugContraindication", "DrugMonitoring", "DrugPatientEducation",
                     "DrugSideEffect", "DrugUsage"):
            assert name in message, f"expected supported model name {name!r} in message"


class TestBatchQueryCountRegression:
    """Codex Round 1, P2-3: the N+1-avoidance claim in
    `get_current_batch`/`list_references_for_batch`'s docstrings was
    previously verified only by an ad hoc script outside the committed
    test suite — a real regression (e.g. a future refactor looping
    per-item) would not have been caught by anything in this file.
    Instruments the session's own `before_cursor_execute` event to count
    SELECTs directly."""

    def _count_selects(self, db, fn):
        queries: list[str] = []

        def _listener(conn, cursor, statement, parameters, context, executemany):
            if statement.strip().upper().startswith("SELECT"):
                queries.append(statement)

        event.listen(db.get_bind(), "before_cursor_execute", _listener)
        try:
            result = fn()
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", _listener)
        return result, len(queries)

    def test_get_current_batch_issues_exactly_one_select(self, db) -> None:
        ingredients = [_make_ingredient(db) for _ in range(5)]
        for ing in ingredients:
            _approved_row(db, DrugUsage, ing.id)
        # Materialize ids BEFORE instrumenting: `expire_on_commit=True`
        # means `ingredient.id` is an expired attribute after the commits
        # above, so accessing it for the first time inside the lambda
        # would itself trigger 5 lazy-reload SELECTs unrelated to
        # get_current_batch — a test-methodology artifact, not an N+1 in
        # the function under test (confirmed directly: those extra
        # queries were `SELECT drug_ingredients...`, never issued by
        # get_current_batch itself, which only ever queries `drug_usage`).
        ingredient_ids = [i.id for i in ingredients]

        _, count = self._count_selects(
            db, lambda: retrieval.get_current_batch(db, DrugUsage, ingredient_ids)
        )
        assert count == 1, f"expected exactly 1 SELECT for 5 ingredients, got {count}"

    def test_list_references_for_batch_issues_exactly_one_select(self, db) -> None:
        ingredients = [_make_ingredient(db) for _ in range(5)]
        approved_rows = [_approved_row(db, DrugUsage, ing.id) for ing in ingredients]
        reference = DrugReference(
            publisher="Synthetic Publisher",
            title=f"Synthetic Title {uuid.uuid4().hex[:8]}",
            source_type="clinical_guideline",
            document_identifier=f"doc-{uuid.uuid4().hex[:8]}",
            publication_date=dt.date(2026, 1, 1),
            source_version="1.0",
            accessed_at=dt.date(2026, 1, 2),
        )
        db.add(reference)
        db.commit()
        db.refresh(reference)
        for row in approved_rows:
            db.add(
                KnowledgeReferenceLink(
                    knowledge_table="drug_usage",
                    knowledge_row_id=row.id,
                    drug_reference_id=reference.id,
                )
            )
        db.commit()
        # Materialize ids BEFORE instrumenting — see the matching comment
        # in test_get_current_batch_issues_exactly_one_select: expired
        # attributes accessed for the first time inside the lambda would
        # otherwise be miscounted as part of the function under test.
        row_ids = [r.id for r in approved_rows]

        _, count = self._count_selects(
            db,
            lambda: retrieval.list_references_for_batch(db, DrugUsage, row_ids),
        )
        assert count == 1, f"expected exactly 1 SELECT for 5 rows, got {count}"


class TestPopulateExistingCaveat:
    """Codex Round 1, P2-5: `.populate_existing()` protects against a row
    already dirty-in-memory being returned *stale* (see other tests in
    this file), but the SAME mechanism can, as a documented (module
    docstring), accepted trade-off, discard a caller's own legitimate,
    not-yet-flushed edit to that row. PTH review: keep the existing K1.5
    pattern unchanged, just document and regression-test it — this test
    locks in the CURRENT, accepted behavior so a future change to it is a
    deliberate decision, not an silent side effect of some unrelated
    refactor."""

    def test_unrelated_pending_edit_on_same_row_is_discarded_by_a_read(self, db) -> None:
        ingredient = _make_ingredient(db)
        approved = _approved_row(db, DrugUsage, ingredient.id, variant="real")
        approved.content = "pending edit — never flushed/committed"

        found = retrieval.get_current_by_business_key(
            db, DrugUsage, drug_ingredient_id=ingredient.id, locale="vi", audience="patient"
        )

        assert found is approved
        assert found.content == "content-real", (
            "documented, accepted trade-off: a read touching the same "
            "identity-mapped row discards an unrelated unflushed edit — "
            "see the module docstring's populate_existing() caveat"
        )


class TestBusinessKeyIndexConformance:
    """Codex Round 2, P2-2: every other test in this file trusts
    `retrieval._BUSINESS_KEY_FIELDS` (re-exported from `knowledge_
    repository.py`, K1.5) as ground truth for what each model's business
    key is. This class instead independently declares the expected
    business key per model (below, hand-written, NOT derived from
    `_BUSINESS_KEY_FIELDS`) and checks BOTH the real DB index metadata AND
    the Python registry against it — so a drift in either direction (a
    future migration changes an index without updating the registry, or
    someone edits the registry without a matching migration) fails
    explicitly instead of every other test silently agreeing on the wrong
    definition.

    Deliberately does NOT introduce a second production registry — this
    mapping exists only inside this test, whose entire purpose is
    detecting drift between the two real sources of truth (the migrated
    schema and `_BUSINESS_KEY_FIELDS`), not to replace either."""

    _EXPECTED_BUSINESS_KEYS: dict[type, tuple[str, ...]] = {
        DrugUsage: ("drug_ingredient_id", "locale", "audience"),
        DrugPatientEducation: ("drug_ingredient_id", "theme", "locale", "audience"),
        DrugSideEffect: ("drug_ingredient_id", "concept_code"),
        DrugMonitoring: ("drug_ingredient_id", "parameter", "patient_context"),
        DrugContraindication: ("drug_ingredient_id", "condition_type", "condition_key"),
    }

    def _approved_partial_unique_index(self, model_cls: type):
        """Identifies the index structurally (unique=True AND carries a
        dialect-specific partial WHERE predicate) rather than by name
        pattern — doesn't assume/depend on the `uq_<table>_approved_key`
        naming convention, which is itself just a K1.5 convention, not a
        structural guarantee."""
        candidates = [
            idx
            for idx in model_cls.__table__.indexes
            if idx.unique and idx.dialect_options["sqlite"].get("where") is not None
        ]
        assert len(candidates) == 1, (
            f"{model_cls.__name__}: expected exactly one unique index with "
            f"a partial WHERE predicate, found {len(candidates)}: "
            f"{[i.name for i in candidates]}"
        )
        return candidates[0]

    @pytest.mark.parametrize("model_cls", _ALL_KNOWLEDGE_MODELS)
    def test_approved_index_columns_match_independent_expected_business_key(
        self, model_cls
    ) -> None:
        expected = self._EXPECTED_BUSINESS_KEYS[model_cls]
        index = self._approved_partial_unique_index(model_cls)

        assert index.unique is True, f"{model_cls.__name__}: approved-key index must be UNIQUE"
        actual_columns = tuple(index.columns.keys())
        assert actual_columns == expected, (
            f"{model_cls.__name__}: real index columns {actual_columns} != "
            f"independently expected business key {expected}"
        )

    @pytest.mark.parametrize("model_cls", _ALL_KNOWLEDGE_MODELS)
    @pytest.mark.parametrize("dialect_name", ["sqlite", "postgresql"])
    def test_approved_index_predicate_limits_to_status_approved(
        self, model_cls, dialect_name
    ) -> None:
        """Reads the raw `TextClause.text` each dialect-specific kwarg
        carries directly (never a compiled/rendered SQL string) — dialect-
        neutral by construction (works without a live connection to either
        database) and not brittle to whitespace/quoting a compiler might
        introduce. Normalizes whitespace and case before comparing so
        `status = 'approved'` and `status='approved'` are both accepted."""
        index = self._approved_partial_unique_index(model_cls)
        where_clause = index.dialect_options[dialect_name].get("where")
        assert where_clause is not None, (
            f"{model_cls.__name__}: {dialect_name} partial index predicate is missing"
        )
        normalized = "".join(where_clause.text.split()).lower()
        assert normalized == "status='approved'", (
            f"{model_cls.__name__}: {dialect_name} partial predicate "
            f"{where_clause.text!r} does not limit uniqueness to status='approved'"
        )

    @pytest.mark.parametrize("model_cls", _ALL_KNOWLEDGE_MODELS)
    def test_business_key_fields_registry_matches_independent_expected_mapping(
        self, model_cls
    ) -> None:
        """The OTHER half of drift detection: the Python registry itself
        (`_BUSINESS_KEY_FIELDS`, not the DB index) must also match the
        same independently declared mapping."""
        expected = self._EXPECTED_BUSINESS_KEYS[model_cls]
        actual = retrieval._BUSINESS_KEY_FIELDS[model_cls]
        assert actual == expected, (
            f"{model_cls.__name__}: _BUSINESS_KEY_FIELDS {actual} != "
            f"independently expected {expected}"
        )


class TestDormancyBoundary:
    def test_new_module_functions_have_zero_callers_outside_tests(self) -> None:
        """K1 dormancy discipline: a read path existing here does not mean
        anything calls it. Every function this module exports must have
        zero hits in app/api, app/ai, and frontend/src."""
        import pathlib
        import re

        backend_dir = pathlib.Path(__file__).resolve().parents[1]
        repo_root = backend_dir.parent
        function_names = [
            "get_current_by_business_key",
            "list_current_for_ingredient",
            "list_current_for_drug_class",
            "get_current_batch",
            "list_references_for",
            "list_references_for_batch",
            # Codex Round 1, P3-4: also match the module path itself, not
            # just the bare function names — an aliased import
            # (`from ...knowledge_retrieval import get_current_batch as
            # gcb`) would rename away every function-name match above, but
            # the import statement's own module path can't be aliased away
            # the same way (still catches `import
            # app.services.knowledge_retrieval as kr` too, since the
            # literal substring is still present in that statement).
            "knowledge_retrieval",
        ]
        pattern = re.compile("|".join(function_names))
        search_dirs = [
            backend_dir / "app" / "api",
            backend_dir / "app" / "ai",
            repo_root / "frontend" / "src",
        ]
        hits = []
        for directory in search_dirs:
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file() and pattern.search(path.read_text(errors="ignore")):
                    hits.append(str(path))
        assert hits == [], f"K1.6 dormancy violated — found references in: {hits}"
