"""Unit tests for K1-S3: draft-only knowledge repository/service layer.

Business-logic tests (not SQL-dialect-specific), so these run against the
shared SQLite test DB via the existing `db` fixture (tests/conftest.py) —
no PostgreSQL integration marker needed, unlike the migration test files.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid

import pytest
from app.core.database import SessionLocal
from app.core.system_actors import SystemActor
from app.models.drug_knowledge_ai_generation import KnowledgeAIGeneration
from app.models.drug_knowledge_content import (
    ORIGIN_VALUES,
    STATUS_VALUES,
    DrugContraindication,
    DrugMonitoring,
    DrugPatientEducation,
    DrugSideEffect,
    DrugUsage,
)
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.models.drug_knowledge_governance import ClinicalSpecialty
from app.models.drug_knowledge_lifecycle_transition import KnowledgeLifecycleTransition
from app.services import knowledge_repository as repo
from sqlalchemy.exc import IntegrityError


def _make_ingredient(db, *, required_specialties: list[str] | None = None) -> DrugIngredient:
    suffix = uuid.uuid4().hex[:8]
    drug_class = DrugClass(name=f"test-class-{suffix}", required_specialties=required_specialties or [])
    db.add(drug_class)
    db.flush()
    ingredient = DrugIngredient(name_inn=f"test-ingredient-{suffix}", drug_class_id=drug_class.id)
    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)
    return ingredient


def _approval_provenance_fields() -> dict[str, object]:
    """ck_<table>_approved_invariants requires reviewed_by/evidence_level/
    source/version/last_reviewed_at to be non-null once a row reaches
    'approved' (drug_knowledge_content.py:48). Synthetic placeholder values
    only — never real clinical content/sourcing.

    `reviewed_by` is deliberately NOT included here (fix round 1,
    2026-07-28, Codex Round 1 finding #6): `build_draft` now rejects an
    explicit `reviewed_by=` kwarg outright — it is bound exclusively to the
    approving actor inside `approve_row`'s own UPDATE, never pre-supplied
    at draft creation. The `approved_invariants` CHECK still passes at
    approval time because `approve_row` sets `reviewed_by` in the same
    statement as `status='approved'`."""
    return dict(
        source="Synthetic Test Source",
        version="1.0",
        evidence_level="expert_opinion",
        last_reviewed_at=dt.datetime.now(dt.UTC),
    )


class TestCreateDraft:
    def test_creates_row_with_draft_status(self, db) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="synthetic test content — never staged/production",
        )
        assert row.status == "draft"
        assert row.authored_by == "author-1"
        assert row.status_changed_by == "author-1"
        assert row.id is not None

    def test_create_new_version_does_not_overwrite(self, db) -> None:
        """Editing content means calling create_draft again for the same
        business key — must produce a SECOND row, never mutate the first."""
        ingredient = _make_ingredient(db)
        first = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="version 1",
        )
        second = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="version 2",
            **_approval_provenance_fields(),
        )
        assert first.id != second.id
        rows = (
            db.query(DrugUsage)
            .filter_by(drug_ingredient_id=ingredient.id, locale="vi", audience="patient")
            .all()
        )
        assert len(rows) == 2
        assert {r.content for r in rows} == {"version 1", "version 2"}
        # The first row is untouched — this proves version 2 was appended,
        # not an UPDATE of version 1.
        db.refresh(first)
        assert first.content == "version 1"

    def test_reviewed_by_cannot_be_pre_supplied_at_draft_creation(self, db) -> None:
        """Codex Round 1 finding #6 (fix round 1, 2026-07-28): draft
        construction must not accept a caller-supplied reviewed_by — it is
        bound exclusively to the approving actor at approve_row time."""
        ingredient = _make_ingredient(db)
        with pytest.raises(ValueError, match="reviewed_by"):
            repo.create_draft(
                db,
                DrugUsage,
                authored_by="author-1",
                drug_ingredient_id=ingredient.id,
                locale="vi",
                audience="patient",
                content="content",
                reviewed_by="forged-reviewer",
            )


class TestPublishedQueryExcludesDrafts:
    def test_draft_not_returned_by_list_published(self, db) -> None:
        ingredient = _make_ingredient(db)
        repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="draft content",
        )
        published = repo.list_published(db, DrugUsage, drug_ingredient_id=ingredient.id)
        assert published == []

    @pytest.mark.parametrize(
        "model_cls",
        [DrugUsage, DrugPatientEducation, DrugSideEffect, DrugMonitoring, DrugContraindication],
    )
    def test_zero_approved_rows_exist_anywhere(self, db, model_cls) -> None:
        """K1-S3 scope lock: nothing in this codebase can create an approved
        row, in ANY of the 5 in-scope tables — not just DrugUsage."""
        count = db.query(model_cls).filter_by(status="approved").count()
        assert count == 0

    def test_status_kwarg_cannot_override_draft(self, db) -> None:
        """A caller passing status='approved' through **fields must not be
        able to bypass create_draft's hardcoded status='draft' — Python's
        duplicate-keyword-argument TypeError is what actually prevents
        this (create_draft always passes status='draft' explicitly), and
        this regression test locks that behavior in rather than leaving it
        as an incidental property of the current implementation."""
        ingredient = _make_ingredient(db)
        with pytest.raises(TypeError, match="status"):
            repo.create_draft(
                db,
                DrugUsage,
                authored_by="author-1",
                drug_ingredient_id=ingredient.id,
                locale="vi",
                audience="patient",
                content="content",
                status="approved",
            )
        assert db.query(DrugUsage).filter_by(status="approved").count() == 0


class TestTransitionValidation:
    def test_draft_to_clinical_review_allowed(self) -> None:
        repo.validate_transition(
            "draft", "clinical_review", authored_by="author-1", actor_user_id="author-1"
        )  # does not raise

    def test_draft_to_approved_directly_rejected(self) -> None:
        """ADR-13: no transition ever skips clinical_review."""
        with pytest.raises(repo.TransitionError, match="Illegal transition"):
            repo.validate_transition(
                "draft", "approved", authored_by="author-1", actor_user_id="reviewer-1"
            )

    def test_self_approval_rejected(self) -> None:
        with pytest.raises(repo.TransitionError, match="Self-approval"):
            repo.validate_transition(
                "clinical_review",
                "approved",
                authored_by="author-1",
                actor_user_id="author-1",
                specialty_complete=True,
            )

    def test_approval_without_specialty_completeness_rejected(self) -> None:
        with pytest.raises(repo.TransitionError, match="specialty"):
            repo.validate_transition(
                "clinical_review",
                "approved",
                authored_by="author-1",
                actor_user_id="reviewer-1",
                specialty_complete=False,
            )

    def test_approval_with_different_actor_and_complete_specialties_passes_validation(self) -> None:
        """Proves the RULE is correctly implemented — this does not mean
        anything in the actual repository can reach 'approved'; see module
        docstring. This is a unit test of validate_transition in isolation."""
        repo.validate_transition(
            "clinical_review",
            "approved",
            authored_by="author-1",
            actor_user_id="reviewer-1",
            specialty_complete=True,
        )  # does not raise

    def test_submit_for_review_blocked_from_non_draft_status(self, db) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        repo.submit_for_review(db, row, actor_user_id="author-1")
        assert row.status == "clinical_review"
        # Submitting again (already clinical_review, not draft) is illegal.
        with pytest.raises(repo.TransitionError):
            repo.submit_for_review(db, row, actor_user_id="author-1")

    def test_concurrent_submit_for_review_only_one_wins(self, db) -> None:
        """Two 'sessions' both read the row while it's still draft, then
        both attempt the transition — the atomic UPDATE...WHERE status
        prevents both from succeeding (Codex-flagged race, now fixed)."""
        from app.core.database import SessionLocal

        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        row_id = row.id

        session_a = SessionLocal()
        session_b = SessionLocal()
        try:
            row_a = session_a.get(DrugUsage, row_id)
            row_b = session_b.get(DrugUsage, row_id)
            assert row_a.status == row_b.status == "draft"

            repo.submit_for_review(session_a, row_a, actor_user_id="author-1")
            assert row_a.status == "clinical_review"
            with pytest.raises(repo.TransitionError, match="did not win|not in 'draft'|race"):
                repo.submit_for_review(session_b, row_b, actor_user_id="author-1")
        finally:
            session_a.close()
            session_b.close()


class TestApprovalAuthorizationMatrix:
    """Codex round-3 P2-2: exhaustive coverage of `can_approve_knowledge`/
    `assert_can_approve_knowledge` (the ONE gate `approve_row`/
    `retire_row` are required to share — see
    `test_approve_row_and_retire_row_both_gate_through_assert_can_approve_knowledge`
    below) across every `UserRole` value plus the two non-role runtime
    inputs a caller could still pass (an unrecognized string, `None`).
    Frozen policy per `can_approve_knowledge`'s own docstring: only
    `internal_admin`/`super_admin` may approve or retire; everything else
    fails closed."""

    @pytest.mark.parametrize(
        "role,expected",
        [
            ("internal_admin", True),
            ("super_admin", True),
            ("medical_reviewer", False),
            ("doctor", False),
            ("patient", False),
            ("clinic_admin", False),
            ("ai_service", False),
            ("unknown_role_never_defined", False),
            (None, False),
        ],
    )
    def test_can_approve_knowledge_matrix(self, role, expected) -> None:
        assert repo.can_approve_knowledge(role) is expected

    @pytest.mark.parametrize(
        "role",
        [
            "medical_reviewer",
            "doctor",
            "patient",
            "clinic_admin",
            "ai_service",
            "unknown_role_never_defined",
            None,
        ],
    )
    def test_assert_can_approve_knowledge_rejects_every_non_capable_role(self, role) -> None:
        with pytest.raises(repo.KnowledgeApprovalAuthorizationError):
            repo.assert_can_approve_knowledge(role)

    @pytest.mark.parametrize("role", ["internal_admin", "super_admin"])
    def test_assert_can_approve_knowledge_allows_every_capable_role(self, role) -> None:
        repo.assert_can_approve_knowledge(role)  # does not raise

    def test_approve_row_and_retire_row_both_gate_through_assert_can_approve_knowledge(
        self,
    ) -> None:
        """Proves both write paths use the SAME non-bypassable gate,
        rather than each independently re-testing the full role matrix
        against both functions — mirrors the existing source-grep-based
        invariant-#2 verification technique already used in
        MEDICATION_K1_5_COMPLIANCE_REVIEW.md."""
        import inspect

        approve_src = inspect.getsource(repo.approve_row)
        retire_src = inspect.getsource(repo.retire_row)
        assert "assert_can_approve_knowledge(actor_role)" in approve_src
        assert "assert_can_approve_knowledge(actor_role)" in retire_src


class TestSpecialtyCompletenessFailsClosed:
    def test_returns_false_not_raise_when_ingredient_missing(self, db) -> None:
        """Constructing a row with a drug_ingredient_id that doesn't exist
        (bypassing the repository, direct ORM) must fail closed, not crash."""
        row = DrugUsage(
            drug_ingredient_id="does-not-exist",
            locale="vi",
            audience="patient",
            content="content",
            authored_by="author-1",
            status="draft",
            status_changed_by="author-1",
        )
        assert repo.check_specialty_completeness(db, row) is False

    def test_returns_false_when_reviewed_specialty_row_deleted(self, db) -> None:
        """knowledge_review_specialties.specialty_id is not FK-enforced —
        if the referenced ClinicalSpecialty is deleted after the review was
        recorded, completeness must fail closed, not crash on None.code."""
        ingredient = _make_ingredient(db, required_specialties=["cardiology"])
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        repo.record_specialty_review(
            db,
            knowledge_table="drug_usage",
            knowledge_row_id=row.id,
            specialty_id="does-not-exist",
            reviewed_by="reviewer-1",
        )
        assert repo.check_specialty_completeness(db, row) is False

    def test_returns_false_when_valid_review_coexists_with_dangling_one(self, db) -> None:
        """A legitimate review for the required specialty existing alongside
        an unrelated dangling review row must still fail closed — the
        dangling reference is itself a data-integrity problem worth
        surfacing, not something to silently ignore while evaluating the
        rest (Codex round 2)."""
        suffix = uuid.uuid4().hex[:8]
        specialty = ClinicalSpecialty(
            code=f"cardiology-{suffix}", display_name_vi="Tim mạch", display_name_en="Cardiology"
        )
        db.add(specialty)
        db.commit()

        ingredient = _make_ingredient(db, required_specialties=[specialty.code])
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        repo.record_specialty_review(
            db,
            knowledge_table="drug_usage",
            knowledge_row_id=row.id,
            specialty_id=specialty.id,
            reviewed_by="reviewer-1",
        )
        repo.record_specialty_review(
            db,
            knowledge_table="drug_usage",
            knowledge_row_id=row.id,
            specialty_id="does-not-exist",
            reviewed_by="reviewer-2",
        )
        assert repo.check_specialty_completeness(db, row) is False


class TestSpecialtyCompleteness:
    def test_no_required_specialties_is_trivially_complete(self, db) -> None:
        ingredient = _make_ingredient(db, required_specialties=[])
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        assert repo.check_specialty_completeness(db, row) is True

    def test_required_specialty_without_review_is_incomplete(self, db) -> None:
        ingredient = _make_ingredient(db, required_specialties=["endocrinology"])
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        assert repo.check_specialty_completeness(db, row) is False

    def test_required_specialty_with_recorded_review_is_complete(self, db) -> None:
        ingredient = _make_ingredient(db, required_specialties=["endocrinology"])
        suffix = uuid.uuid4().hex[:8]
        specialty = ClinicalSpecialty(
            code=f"endocrinology-{suffix}",
            display_name_vi="Nội tiết",
            display_name_en="Endocrinology",
        )
        # Match the ingredient's required_specialties list to this specialty's
        # actual (unique-suffixed) code so this test doesn't collide with
        # other tests seeding the same "endocrinology" code in the shared DB.
        ingredient_row = db.get(DrugIngredient, ingredient.id)
        drug_class = db.get(DrugClass, ingredient_row.drug_class_id)
        drug_class.required_specialties = [specialty.code]
        db.add(specialty)
        db.commit()

        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        assert repo.check_specialty_completeness(db, row) is False

        repo.record_specialty_review(
            db,
            knowledge_table="drug_usage",
            knowledge_row_id=row.id,
            specialty_id=specialty.id,
            reviewed_by="reviewer-1",
        )
        assert repo.check_specialty_completeness(db, row) is True

    def test_ignores_forged_required_specialties_on_attached_drug_class(self, db) -> None:
        """Codex round-3 P1-2: a `DrugClass` already attached to this
        session's identity map (loaded earlier, e.g. by
        `_make_ingredient` itself) with `required_specialties` mutated in
        memory and never persisted (autoflush=False) must not be able to
        forge the gate from strict (['cardiology']) to lenient ([]) —
        `check_specialty_completeness` must read the REAL persisted
        value, not the dirty in-memory one."""
        ingredient = _make_ingredient(db, required_specialties=["cardiology"])
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        assert repo.check_specialty_completeness(db, row) is False

        drug_class = db.get(DrugClass, ingredient.drug_class_id)
        drug_class.required_specialties = []  # forged in-memory only, never flushed

        assert repo.check_specialty_completeness(db, row) is False, (
            "the forged in-memory required_specialties=[] must not bypass the "
            "gate — the real persisted value (['cardiology']) must still apply"
        )

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugClass, ingredient.drug_class_id)
            assert persisted.required_specialties == ["cardiology"], (
                "the forged mutation must never have been persisted"
            )
        finally:
            fresh.close()

    def test_ignores_forged_drug_class_id_on_attached_ingredient(self, db) -> None:
        """Codex round-3 P1-2 variant: a `DrugIngredient` already attached
        to this session's identity map with `drug_class_id` forged in
        memory (pointing at a lenient class with no required specialties)
        must not be able to redirect the gate away from its REAL,
        persisted, strict drug_class."""
        strict_ingredient = _make_ingredient(db, required_specialties=["cardiology"])
        lenient_ingredient = _make_ingredient(db, required_specialties=[])

        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=strict_ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        assert repo.check_specialty_completeness(db, row) is False

        ingredient_row = db.get(DrugIngredient, strict_ingredient.id)
        lenient_row = db.get(DrugIngredient, lenient_ingredient.id)
        ingredient_row.drug_class_id = lenient_row.drug_class_id  # forged in-memory only

        assert repo.check_specialty_completeness(db, row) is False, (
            "the forged in-memory drug_class_id must not redirect the gate to "
            "the lenient class — the real persisted strict drug_class_id must "
            "still apply"
        )

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugIngredient, strict_ingredient.id)
            assert persisted.drug_class_id == strict_ingredient.drug_class_id, (
                "the forged mutation must never have been persisted"
            )
        finally:
            fresh.close()

    def test_ignores_forged_matching_specialty_code_forged_to_mismatch(self, db) -> None:
        """Codex round-4 P2: a `ClinicalSpecialty` already attached to
        this session's identity map, whose PERSISTED code genuinely
        satisfies the required specialty, must not have its completeness
        verdict flipped to incomplete just because some other in-session
        code forged its `.code` attribute in memory (never flushed) to a
        value that no longer matches. The gate must read the real,
        persisted code, not the dirty cached one."""
        suffix = uuid.uuid4().hex[:8]
        real_code = f"cardiology-{suffix}"
        specialty = ClinicalSpecialty(
            code=real_code, display_name_vi="Tim mạch", display_name_en="Cardiology"
        )
        db.add(specialty)
        db.commit()

        ingredient = _make_ingredient(db, required_specialties=[real_code])
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        repo.record_specialty_review(
            db,
            knowledge_table="drug_usage",
            knowledge_row_id=row.id,
            specialty_id=specialty.id,
            reviewed_by="reviewer-1",
        )
        assert repo.check_specialty_completeness(db, row) is True

        attached_specialty = db.get(ClinicalSpecialty, specialty.id)
        attached_specialty.code = "forged-mismatch-code"  # in-memory only, never flushed

        assert repo.check_specialty_completeness(db, row) is True, (
            "the forged in-memory code must not flip a genuinely-complete "
            "review to incomplete — the real persisted code still matches"
        )

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(ClinicalSpecialty, specialty.id)
            assert persisted.code == real_code, "the forged mutation must never have been persisted"
        finally:
            fresh.close()

    def test_ignores_forged_mismatching_specialty_code_forged_to_match(self, db) -> None:
        """Codex round-4 P2 variant (the compliance-critical direction): a
        `ClinicalSpecialty` already attached to this session's identity
        map, whose PERSISTED code does NOT satisfy the required
        specialty, must not have its completeness verdict flipped to
        COMPLETE just because some other in-session code forged its
        `.code` attribute in memory to match the required code. If this
        ever regressed, an approval could be granted for a knowledge row
        whose real, required specialty review never actually happened."""
        suffix = uuid.uuid4().hex[:8]
        required_code = f"endocrinology-{suffix}"
        reviewed_but_wrong_code = f"cardiology-{suffix}"
        specialty = ClinicalSpecialty(
            code=reviewed_but_wrong_code,
            display_name_vi="Tim mạch",
            display_name_en="Cardiology",
        )
        db.add(specialty)
        db.commit()

        ingredient = _make_ingredient(db, required_specialties=[required_code])
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        # A review WAS recorded, but for the wrong specialty — required_code
        # itself was never reviewed.
        repo.record_specialty_review(
            db,
            knowledge_table="drug_usage",
            knowledge_row_id=row.id,
            specialty_id=specialty.id,
            reviewed_by="reviewer-1",
        )
        assert repo.check_specialty_completeness(db, row) is False

        attached_specialty = db.get(ClinicalSpecialty, specialty.id)
        attached_specialty.code = required_code  # forged in-memory only, never flushed

        assert repo.check_specialty_completeness(db, row) is False, (
            "BUG if this fails: the forged in-memory code let an unrelated, "
            "wrongly-reviewed specialty masquerade as the actually-required "
            "one — an approval could bypass a specialty review that never "
            "really happened"
        )

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(ClinicalSpecialty, specialty.id)
            assert persisted.code == reviewed_but_wrong_code, (
                "the forged mutation must never have been persisted"
            )
        finally:
            fresh.close()


class TestApproveRow:
    _ROLE = "internal_admin"

    @pytest.fixture(autouse=True)
    def _cleanup_approved_rows(self, db):
        """The `db` fixture (tests/conftest.py) has no per-test rollback —
        it's a plain session on a shared, session-scoped SQLite file
        (create_all() runs once, autouse, session-scoped). Unlike every
        other test in this file, these tests must call approve_row for
        real (non-negotiable invariants #1/#3 require it), which commits
        real 'approved' rows that would otherwise persist and break
        test_medication_knowledge_import_orchestrator.py's/this file's own
        TestPublishedQueryExcludesDrafts.test_zero_approved_rows_exist_anywhere
        global count() == 0 checks for any test running later in the same
        session. Deleting what this class creates, every time, keeps those
        pre-existing regression tests passing unmodified (plan §3.2/§9.7)
        without weakening them or making them orchestrator-scoped."""
        existing_ids = {row.id for row in db.query(DrugUsage.id).all()}
        yield
        db.rollback()
        for row in db.query(DrugUsage).filter(~DrugUsage.id.in_(existing_ids)).all():
            db.delete(row)
        db.commit()

    def _submitted_row(self, db, *, required_specialties: list[str] | None = None, **overrides):
        ingredient = _make_ingredient(db, required_specialties=required_specialties)
        fields = dict(
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="synthetic test content — never staged/production",
            **_approval_provenance_fields(),
        )
        fields.update(overrides)
        row = repo.create_draft(db, DrugUsage, authored_by="author-1", **fields)
        repo.submit_for_review(db, row, actor_user_id="author-1")
        return ingredient, row

    def test_happy_path_approves_and_records_actor(self, db) -> None:
        _, row = self._submitted_row(db)
        approved = repo.approve_row(
            db, row, actor_user_id="reviewer-1", actor_role=self._ROLE
        )
        assert approved.status == "approved"
        assert approved.status_changed_by == "reviewer-1"

    def test_rejects_self_approval_at_write_time(self, db) -> None:
        _, row = self._submitted_row(db)
        with pytest.raises(repo.TransitionError, match="Self-approval"):
            repo.approve_row(db, row, actor_user_id="author-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_rejects_incomplete_specialty_at_write_time(self, db) -> None:
        _, row = self._submitted_row(db, required_specialties=["cardiology"])
        with pytest.raises(repo.TransitionError, match="specialty"):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    @pytest.mark.parametrize(
        "role",
        [
            "patient",
            "doctor",
            "clinic_admin",
            "medical_reviewer",
            "ai_service",
            "unknown_role_never_defined",
            None,
        ],
    )
    def test_rejects_unauthorized_role(self, db, role) -> None:
        """Codex round-3 P2-2: full authorization matrix, not just
        'patient' — every UserRole other than internal_admin/super_admin,
        plus an unrecognized string and None, must be rejected."""
        _, row = self._submitted_row(db)
        with pytest.raises(repo.KnowledgeApprovalAuthorizationError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=role)
        db.refresh(row)
        assert row.status == "clinical_review"

    @pytest.mark.parametrize("role", ["internal_admin", "super_admin"])
    def test_every_capable_role_can_approve_end_to_end(self, db, role) -> None:
        """Codex round-3 P2-2: the happy-path tests elsewhere in this
        class all hard-code `internal_admin` (`self._ROLE`) — this proves
        `super_admin`, the OTHER approval-capable role per
        `can_approve_knowledge`, works end-to-end too."""
        _, row = self._submitted_row(db)
        approved = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=role)
        assert approved.status == "approved"

    def test_rejects_from_draft_status(self, db) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        with pytest.raises(repo.TransitionError, match="Illegal transition"):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "draft"

    def test_auto_deprecates_prior_approved_row_same_business_key(self, db) -> None:
        ingredient, first = self._submitted_row(db)
        first = repo.approve_row(db, first, actor_user_id="reviewer-1", actor_role=self._ROLE)
        assert first.status == "approved"

        second = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="version 2",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, second, actor_user_id="author-1")
        second = repo.approve_row(db, second, actor_user_id="reviewer-1", actor_role=self._ROLE)

        db.refresh(first)
        assert first.status == "deprecated"
        assert first.status_changed_by == "reviewer-1"
        assert second.status == "approved"

    def test_rolls_back_deprecation_when_second_statement_fails(self, db, monkeypatch) -> None:
        """Gate B (PTH review of the K1.5 checkpoint). Codex round-3 P2-1:
        the previous version of this test gave `prior_approved` and
        `target` DIFFERENT business keys (different ingredients) — so the
        REAL `_deprecate_superseded` call made as part of approving
        `target` never touched `prior_approved` at all (zero rows
        matched, different business key); the "deprecation" the old test
        claimed to prove rolled back was actually a second, unrelated raw
        UPDATE the monkeypatch itself issued directly against `target`.
        The assertion `prior_approved.status == "approved"` passed
        trivially regardless of whether rollback worked, since nothing
        real had ever changed it — a fake-green test.

        Fixed: `prior_approved` and `target` now share the EXACT SAME
        business key (same ingredient, locale, audience), so when
        `target`'s own `approve_row` call reaches `_deprecate_superseded`,
        the REAL, unmodified deprecation logic finds and updates
        `prior_approved` — this is genuine product behavior, not a
        monkeypatch side effect standing in for it. The monkeypatch here
        does exactly one thing: run the real `_deprecate_superseded`,
        then force the SECOND statement (the approve UPDATE) to fail
        deterministically by flipping `target`'s REAL DB status to
        'retired' via a raw UPDATE with `synchronize_session=False` (so
        the in-memory ORM object stays 'clinical_review', but
        approve_row's own atomic `UPDATE ... WHERE status =
        'clinical_review'` correctly sees 0 matching rows against the
        real DB truth and raises TransitionError — the same shape a lost
        concurrency race would produce).

        Since P1-1, approve_row resolves a canonical row (`SELECT ... FOR
        UPDATE`) once at the top and uses it consistently for every
        check, so this corruption must happen strictly AFTER
        `validate_transition` has already passed against the canonical
        row, but BEFORE the approve UPDATE statement runs — exactly where
        `_deprecate_superseded` is called from inside `approve_row`.
        """
        ingredient, prior_approved = self._submitted_row(db)
        prior_approved = repo.approve_row(
            db, prior_approved, actor_user_id="reviewer-1", actor_role=self._ROLE
        )
        assert prior_approved.status == "approved"

        target = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="version 2 — same business key as prior_approved",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, target, actor_user_id="author-1")
        target_id = target.id

        from sqlalchemy import update as sa_update

        original_deprecate = repo._deprecate_superseded

        def _deprecate_then_corrupt_target(db, row, *, actor_user_id, now):
            # `row` here is `target`'s own canonical object — since target
            # shares prior_approved's exact business key, this call for
            # real finds and deprecates prior_approved (id != target.id,
            # status='approved', same business key). Not a stand-in.
            result = original_deprecate(db, row, actor_user_id=actor_user_id, now=now)
            db.execute(
                sa_update(DrugUsage).where(DrugUsage.id == target_id).values(status="retired"),
                execution_options={"synchronize_session": False},
            )
            return result

        monkeypatch.setattr(repo, "_deprecate_superseded", _deprecate_then_corrupt_target)

        with pytest.raises(repo.TransitionError, match="not in 'clinical_review'"):
            repo.approve_row(db, target, actor_user_id="reviewer-2", actor_role=self._ROLE)

        assert not db.in_transaction(), (
            "the failed approve_row call must roll back and close its own "
            "transaction, not leave the session mid-transaction"
        )

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            fresh_prior = fresh.get(DrugUsage, prior_approved.id)
            fresh_target = fresh.get(DrugUsage, target_id)
            assert fresh_prior.status == "approved", (
                "the REAL deprecate UPDATE (first statement, matching "
                "target's exact business key) must be rolled back when the "
                "approve UPDATE (second statement) fails — no partial "
                "commit of just the deprecation"
            )
            assert fresh_target.status == "clinical_review", (
                "the corrupting raw UPDATE must ALSO be rolled back — target "
                "must be exactly where it started, not left at 'retired'"
            )
        finally:
            fresh.close()

    def test_ignores_spoofed_fields_on_caller_supplied_object(self, db) -> None:
        """Codex round-1 P1-1: approve_row must trust only `row.id` (used
        to locate the row) from the caller-supplied object — never any
        other field. Constructs a genuinely DETACHED DrugUsage instance
        (never added to the session) sharing the real row's id but with
        forged authored_by/drug_ingredient_id/content/status. If approve_row
        wrongly trusted the detached object's `authored_by`, this would NOT
        look like self-approval (forged authored_by != actor_user_id) and
        the approval would incorrectly succeed. With the fix, approve_row
        re-fetches the canonical persisted row by id and correctly detects
        that the REAL authored_by equals actor_user_id — self-approval,
        rejected."""
        ingredient, real = self._submitted_row(db)  # authored_by="author-1"

        spoofed = DrugUsage(
            id=real.id,
            drug_ingredient_id="not-the-real-ingredient-id",
            locale="vi",
            audience="patient",
            content="forged in-memory content — never persisted",
            authored_by="not-the-real-author",
            status="clinical_review",
            status_changed_by="not-the-real-author",
        )
        assert spoofed not in db  # never added/attached — genuinely detached

        with pytest.raises(repo.TransitionError, match="Self-approval"):
            repo.approve_row(db, spoofed, actor_user_id="author-1", actor_role=self._ROLE)

        db.refresh(real)
        assert real.status == "clinical_review"
        assert real.authored_by == "author-1"
        assert real.drug_ingredient_id == ingredient.id
        assert real.content == "synthetic test content — never staged/production"

    def test_ignores_forged_authored_by_on_attached_identity_mapped_object(self, db) -> None:
        """Codex round-2 P1-1: the DETACHED-object test above does not
        cover the realistic, more dangerous case — a row already loaded/
        attached in THIS session's identity map (e.g. the caller did
        `db.get()` earlier), with an attribute mutated in memory and never
        persisted (`SessionLocal` has `autoflush=False`,
        app/core/database.py:37, so this mutation is never silently
        flushed). Before the populate_existing=True fix, SQLAlchemy would
        return the SAME cached object from `_lock_canonical_row` without
        overwriting the forged attribute — reproduced directly against
        the pre-fix code: approve_row incorrectly SUCCEEDED and even
        PERSISTED "forged-author" as the real authored_by on commit."""
        _, row = self._submitted_row(db)  # authored_by="author-1", attached to `db`
        row.authored_by = "forged-author"  # in-memory only, never flushed/committed

        with pytest.raises(repo.TransitionError, match="Self-approval"):
            repo.approve_row(db, row, actor_user_id="author-1", actor_role=self._ROLE)

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row.id)
            assert persisted.authored_by == "author-1", (
                "the forged in-memory authored_by must never be persisted, and "
                "self-approval must be evaluated against the real value"
            )
            assert persisted.status == "clinical_review"
        finally:
            fresh.close()

    def test_ignores_forged_status_preventing_double_approval(self, db) -> None:
        """Codex round-2 P1-1 variant: forging `status` in memory (back to
        'clinical_review' on an already-'approved' attached row) must not
        let a caller re-approve it — invariant #3 (no double approval)
        must hold against the REAL persisted status, not a forged one."""
        _, row = self._submitted_row(db)
        approved = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        assert approved.status == "approved"

        approved.status = "clinical_review"  # forged in-memory only

        with pytest.raises(repo.TransitionError, match="Illegal transition"):
            repo.approve_row(db, approved, actor_user_id="reviewer-2", actor_role=self._ROLE)

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row.id)
            assert persisted.status == "approved"
        finally:
            fresh.close()

    def test_ignores_forged_secondary_business_key_field(self, db) -> None:
        """Codex round-2 P1-1 variant: forging a secondary business-key
        field (`locale`) in memory must not change which prior approved
        row `_deprecate_superseded` targets — it must use the REAL
        persisted business key, never a caller-forged one. Sets up an
        unrelated row at a DIFFERENT locale sharing the same ingredient,
        to prove a forged locale can't cause the wrong row to be
        deprecated (or the right one to be missed)."""
        ingredient = _make_ingredient(db)

        real_prior = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="v1",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, real_prior, actor_user_id="author-1")
        real_prior = repo.approve_row(
            db, real_prior, actor_user_id="reviewer-1", actor_role=self._ROLE
        )

        unrelated = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="en",
            audience="patient",
            content="unrelated locale — must never be touched",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, unrelated, actor_user_id="author-1")
        unrelated = repo.approve_row(
            db, unrelated, actor_user_id="reviewer-1", actor_role=self._ROLE
        )

        new_version = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="v2",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, new_version, actor_user_id="author-1")
        new_version.locale = "en"  # forged in-memory — pretend this is the en row

        repo.approve_row(db, new_version, actor_user_id="reviewer-1", actor_role=self._ROLE)

        db.refresh(real_prior)
        db.refresh(unrelated)
        assert real_prior.status == "deprecated", (
            "the REAL prior approved row at locale='vi' must be deprecated, "
            "using the persisted business key, not the forged one"
        )
        assert unrelated.status == "approved", (
            "the unrelated locale='en' row must never be touched by a forged "
            "locale value on a different row"
        )

    def test_ignores_forged_drug_ingredient_id_for_specialty_gate(self, db) -> None:
        """Codex round-2 P1-1 variant: forging `drug_ingredient_id` in
        memory must not change which ingredient's specialty-completeness
        gate applies. The row's real ingredient requires a specialty
        review that was never recorded; a forged ingredient (no required
        specialties) must not be able to bypass that gate."""
        strict_ingredient = _make_ingredient(db, required_specialties=["cardiology"])
        lenient_ingredient = _make_ingredient(db, required_specialties=[])

        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=strict_ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, row, actor_user_id="author-1")
        row.drug_ingredient_id = lenient_ingredient.id  # forged in-memory only

        with pytest.raises(repo.TransitionError, match="specialty"):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row.id)
            assert persisted.drug_ingredient_id == strict_ingredient.id
            assert persisted.status == "clinical_review"
        finally:
            fresh.close()

    def test_session_usable_after_validation_failure(self, db) -> None:
        """Codex round-1 P1-2: the entire function — not just the final
        UPDATE/commit — must run inside one transaction boundary, so a
        pre-write validation failure (self-approval here) never leaves the
        session mid-transaction. Proven two ways: (1) `db.in_transaction()`
        is False immediately after the raised TransitionError, before any
        `refresh`/other call; (2) the same session performs a normal,
        unrelated successful write right after, proving it was never left
        in a broken/half-open state."""
        _, row = self._submitted_row(db)

        with pytest.raises(repo.TransitionError, match="Self-approval"):
            repo.approve_row(db, row, actor_user_id="author-1", actor_role=self._ROLE)

        assert not db.in_transaction(), (
            "approve_row must roll back and close its transaction on any "
            "failure, including a pre-write validation failure, not just a "
            "DB-write failure"
        )

        other_ingredient = _make_ingredient(db)
        other_row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-2",
            drug_ingredient_id=other_ingredient.id,
            locale="vi",
            audience="patient",
            content="proves the session recovered",
        )
        assert other_row.id is not None
        assert other_row.status == "draft"

    def test_session_has_no_open_transaction_after_successful_approve(self, db) -> None:
        """Codex round-2 P2-2: the SUCCESS path must also never leave the
        session mid-transaction, not just the failure paths P1-2 already
        covers. Reproduced directly against the pre-fix code: `db.commit()`
        followed by a post-commit `db.refresh(canonical)` autobegan a new
        (mostly-empty) transaction — `db.in_transaction()` was True
        immediately after a successful approve_row call, contradicting
        plan §5. The returned object's attributes must still be correct
        (the refresh moved earlier, before commit, not removed)."""
        _, row = self._submitted_row(db)

        approved = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)

        assert not db.in_transaction(), (
            "approve_row must not autobegin a new transaction via a "
            "post-commit query — commit must be the last DB operation of "
            "the success path"
        )
        assert approved.status == "approved"
        assert approved.status_changed_by == "reviewer-1"

    def test_concurrent_approve_only_one_wins(self, db) -> None:
        """Mirrors test_concurrent_submit_for_review_only_one_wins: two
        sessions both read the row while clinical_review, both attempt
        approve_row.

        Codex round-2 P1-1: since `_lock_canonical_row` now uses
        `populate_existing=True`, session B's identity-mapped `row_b` is
        force-refreshed from the DB the moment `approve_row` runs for it —
        it correctly sees session A's already-committed 'approved' status
        immediately, so `validate_transition` now rejects it as an
        illegal ('approved' -> 'approved') transition at the validation
        step, rather than reaching the atomic UPDATE and failing there on
        a stale in-memory status (the pre-fix behavior this test used to
        assert). Both are legitimate ways to reject a lost race; only the
        message differs.
        """
        from app.core.database import SessionLocal

        _, row = self._submitted_row(db)
        row_id = row.id

        session_a = SessionLocal()
        session_b = SessionLocal()
        try:
            row_a = session_a.get(DrugUsage, row_id)
            row_b = session_b.get(DrugUsage, row_id)
            assert row_a.status == row_b.status == "clinical_review"

            repo.approve_row(session_a, row_a, actor_user_id="reviewer-1", actor_role=self._ROLE)
            assert row_a.status == "approved"
            with pytest.raises(
                repo.TransitionError,
                match="did not win|not in 'clinical_review'|race|Illegal transition",
            ):
                repo.approve_row(session_b, row_b, actor_user_id="reviewer-2", actor_role=self._ROLE)
        finally:
            session_a.close()
            session_b.close()

    def test_rejects_double_approval(self, db) -> None:
        """Non-negotiable invariant #3: approved -> approved must be
        rejected, and a rejected second call must have zero effect."""
        _, row = self._submitted_row(db)
        row = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        first_changed_at = row.status_changed_at

        with pytest.raises(repo.TransitionError, match="Illegal transition"):
            repo.approve_row(db, row, actor_user_id="reviewer-2", actor_role=self._ROLE)

        db.refresh(row)
        assert row.status == "approved"
        assert row.status_changed_at == first_changed_at

    def test_rejects_approval_of_retired_row(self, db) -> None:
        """Non-negotiable invariant #3: retired -> approved must be
        rejected — retired content can never be resurrected directly."""
        ingredient, first = self._submitted_row(db)
        first = repo.approve_row(db, first, actor_user_id="reviewer-1", actor_role=self._ROLE)

        second = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="version 2",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, second, actor_user_id="author-1")
        repo.approve_row(db, second, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(first)
        assert first.status == "deprecated"

        retired = repo.retire_row(db, first, actor_user_id="reviewer-1", actor_role=self._ROLE)
        assert retired.status == "retired"

        with pytest.raises(repo.TransitionError, match="Illegal transition"):
            repo.approve_row(db, retired, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(retired)
        assert retired.status == "retired"

    def test_unrelated_integrity_error_is_not_remapped(self, db) -> None:
        """Codex round-1 P1-3: approve_row must map ONLY the approved-key
        partial-unique-index violation to TransitionError — every other
        IntegrityError must propagate completely unmodified. Builds a row
        missing the provenance fields ck_drug_usage_approved_invariants
        requires once status='approved' (deliberately NOT using
        _approval_provenance_fields()) — approving it violates that CHECK
        constraint, not the approved-key unique index, so it must surface
        as a raw IntegrityError, never a TransitionError."""
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
            # source/version/evidence_level/reviewed_by/last_reviewed_at
            # intentionally omitted — nullable until 'approved'.
        )
        repo.submit_for_review(db, row, actor_user_id="author-1")

        with pytest.raises(IntegrityError) as exc_info:
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        assert not isinstance(exc_info.value, repo.TransitionError)
        assert "ck_drug_usage_approved_invariants" in str(exc_info.value)
        assert "uq_drug_usage_approved_key" not in str(exc_info.value)

        db.rollback()
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_rejects_row_marked_for_deletion_not_yet_flushed(self, db) -> None:
        """Codex round-3 P1-1: db.delete(row) then immediately calling
        approve_row on the SAME object (this SessionLocal has
        autoflush=False, so nothing has flushed yet) must fail closed —
        the canonical-row re-fetch alone does not see any of this, since
        the row is still physically present and unchanged in the DB."""
        _, row = self._submitted_row(db)
        row_id = row.id
        db.delete(row)
        assert row in db.deleted

        with pytest.raises(repo.TransitionError, match="marked for deletion"):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)

        assert not db.in_transaction()

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row_id)
            assert persisted is not None, "the row must not have been deleted"
            assert persisted.status == "clinical_review"
        finally:
            fresh.close()

    def test_rejects_row_already_flushed_as_deleted(self, db) -> None:
        """Codex round-3 P1-1 variant: the DELETE has already been
        flushed within the still-open transaction (pending commit) by an
        earlier statement in this same session. Must still fail closed,
        and the rollback must undo the already-flushed DELETE, not just
        refuse to add to it.

        Codex round-4: since the pending-delete check now runs on
        `canonical` (resolved by `_lock_canonical_row` FIRST — see that
        fix's rationale), and a flushed-but-uncommitted DELETE makes the
        row genuinely unfindable by `_lock_canonical_row`'s own
        `db.get()` within this same transaction (the DELETE has already
        been sent to Postgres), the error observed here is now
        `_lock_canonical_row`'s "does not exist" — not
        `_reject_if_pending_delete`'s "marked for deletion". Both are
        equally fail-closed (TransitionError, rollback, row preserved);
        which ONE fires is just a matter of which check reaches the
        already-gone row first. The still-unflushed case
        (`test_rejects_row_marked_for_deletion_not_yet_flushed` above)
        remains the one that actually exercises
        `_reject_if_pending_delete`'s own logic, since there the row is
        still genuinely fetchable."""
        _, row = self._submitted_row(db)
        row_id = row.id
        db.delete(row)
        db.flush()

        with pytest.raises(repo.TransitionError, match="does not exist|marked for deletion"):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)

        assert not db.in_transaction()

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row_id)
            assert persisted is not None, "the already-flushed DELETE must be rolled back"
            assert persisted.status == "clinical_review"
        finally:
            fresh.close()

    def test_unauthorized_call_from_clean_session_leaves_no_open_transaction(self, db) -> None:
        """Codex round-3 P1-3 clean-baseline test: proves the ORIGINAL
        finding does not reproduce. Starting from a session with
        `db.in_transaction() is False`, an unauthorized-role call raises
        KnowledgeApprovalAuthorizationError (a pure-Python check, no DB
        interaction) and leaves the session exactly as it started — no
        transaction was ever opened by this call, so there is nothing for
        a rollback to have missed."""
        _, row = self._submitted_row(db)
        db.commit()
        assert not db.in_transaction()

        with pytest.raises(repo.KnowledgeApprovalAuthorizationError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role="patient")

        assert not db.in_transaction()
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_rejects_spoofed_object_when_real_row_has_unflushed_pending_delete(
        self, db
    ) -> None:
        """Codex round-4 P1: the round-3 pending-delete check ran on the
        CALLER-SUPPLIED `row` argument, BEFORE canonical was even
        resolved — a DETACHED object sharing the real row's id, but never
        itself passed to `db.delete()`, bypassed it entirely. Reproduced
        directly against the round-3 code: `approve_row` returned
        `status='approved'` and the row was gone from a fresh session
        afterward, because the session's still-pending DELETE on the REAL
        identity-mapped object fired regardless at commit time. Fixed by
        resolving canonical first (by id, via the identity map) and
        checking canonical's deleted state, never the caller argument's."""
        _, row = self._submitted_row(db)
        row_id = row.id
        drug_ingredient_id = row.drug_ingredient_id
        db.delete(row)  # the REAL, identity-mapped object — unflushed
        assert row in db.deleted

        spoofed = DrugUsage(
            id=row_id,
            drug_ingredient_id=drug_ingredient_id,
            locale="vi",
            audience="patient",
            content="spoofed — never persisted",
            authored_by="not-the-real-author",
            status="clinical_review",
            status_changed_by="not-the-real-author",
        )
        assert spoofed not in db  # never added/attached — genuinely detached
        assert spoofed not in db.deleted

        with pytest.raises(repo.TransitionError, match="marked for deletion"):
            repo.approve_row(db, spoofed, actor_user_id="reviewer-1", actor_role=self._ROLE)

        assert not db.in_transaction()

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row_id)
            assert persisted is not None, "the row must not have been deleted"
            assert persisted.status == "clinical_review"
        finally:
            fresh.close()

    def test_rejects_spoofed_object_when_real_row_already_flushed_as_deleted(
        self, db
    ) -> None:
        """Codex round-4 P1 variant: same bypass as above, but the real
        row's DELETE has already been flushed (pending commit) by the
        time the spoofed object is passed in. As with
        `test_rejects_row_already_flushed_as_deleted`, once flushed the
        row is genuinely unfindable within this transaction, so
        `_lock_canonical_row` raises "does not exist" before
        `_reject_if_pending_delete` even runs — still fail-closed, still
        rolled back, just via the earlier check. The key property this
        test proves is that the SPOOFED argument object (never attached,
        never itself deleted) does not let the operation succeed despite
        the real row being gone — canonical resolution is by id via `db`
        alone, so the spoofed object's own identity is irrelevant."""
        _, row = self._submitted_row(db)
        row_id = row.id
        drug_ingredient_id = row.drug_ingredient_id
        db.delete(row)
        db.flush()

        spoofed = DrugUsage(
            id=row_id,
            drug_ingredient_id=drug_ingredient_id,
            locale="vi",
            audience="patient",
            content="spoofed — never persisted",
            authored_by="not-the-real-author",
            status="clinical_review",
            status_changed_by="not-the-real-author",
        )
        assert spoofed not in db

        with pytest.raises(repo.TransitionError, match="does not exist|marked for deletion"):
            repo.approve_row(db, spoofed, actor_user_id="reviewer-1", actor_role=self._ROLE)

        assert not db.in_transaction()

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row_id)
            assert persisted is not None, "the already-flushed DELETE must be rolled back"
            assert persisted.status == "clinical_review"
        finally:
            fresh.close()


class TestRetireRow:
    _ROLE = "internal_admin"

    @pytest.fixture(autouse=True)
    def _cleanup_approved_rows(self, db):
        """See TestApproveRow._cleanup_approved_rows — same shared-session
        SQLite fixture, same need to not leave 'approved'/'deprecated'/
        'retired' rows behind for later tests' global count() == 0 checks."""
        existing_ids = {row.id for row in db.query(DrugUsage.id).all()}
        yield
        db.rollback()
        for row in db.query(DrugUsage).filter(~DrugUsage.id.in_(existing_ids)).all():
            db.delete(row)
        db.commit()

    def _deprecated_row(self, db):
        """Build a row through draft -> clinical_review -> approved ->
        deprecated (via a superseding second approval), matching
        TestApproveRow's own pattern rather than mutating status by hand."""
        ingredient = _make_ingredient(db)
        first = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="version 1",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, first, actor_user_id="author-1")
        first = repo.approve_row(db, first, actor_user_id="reviewer-1", actor_role=self._ROLE)

        second = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="version 2",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, second, actor_user_id="author-1")
        repo.approve_row(db, second, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(first)
        assert first.status == "deprecated"
        return first

    def test_happy_path_retires_deprecated_row(self, db) -> None:
        row = self._deprecated_row(db)
        retired = repo.retire_row(db, row, actor_user_id="reviewer-2", actor_role=self._ROLE)
        assert retired.status == "retired"
        assert retired.status_changed_by == "reviewer-2"

    def test_session_has_no_open_transaction_after_successful_retire(self, db) -> None:
        """Codex round-2 P2-2, retire_row side — same requirement as
        approve_row's matching test above."""
        row = self._deprecated_row(db)
        retired = repo.retire_row(db, row, actor_user_id="reviewer-2", actor_role=self._ROLE)

        assert not db.in_transaction(), (
            "retire_row must not autobegin a new transaction via a "
            "post-commit query — commit must be the last DB operation of "
            "the success path"
        )
        assert retired.status == "retired"
        assert retired.status_changed_by == "reviewer-2"

    @pytest.mark.parametrize("status", ["draft", "clinical_review", "approved"])
    def test_rejects_from_non_deprecated_status(self, db, status) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
            **_approval_provenance_fields(),
        )
        if status in ("clinical_review", "approved"):
            repo.submit_for_review(db, row, actor_user_id="author-1")
        if status == "approved":
            row = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)

        with pytest.raises(repo.TransitionError, match="Illegal transition"):
            repo.retire_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == status

    @pytest.mark.parametrize(
        "role",
        [
            "patient",
            "doctor",
            "clinic_admin",
            "medical_reviewer",
            "ai_service",
            "unknown_role_never_defined",
            None,
        ],
    )
    def test_rejects_unauthorized_role(self, db, role) -> None:
        """Codex round-3 P2-2: full authorization matrix, retire_row side
        — see TestApproveRow's matching test for full rationale."""
        row = self._deprecated_row(db)
        with pytest.raises(repo.KnowledgeApprovalAuthorizationError):
            repo.retire_row(db, row, actor_user_id="reviewer-1", actor_role=role)
        db.refresh(row)
        assert row.status == "deprecated"

    @pytest.mark.parametrize("role", ["internal_admin", "super_admin"])
    def test_every_capable_role_can_retire_end_to_end(self, db, role) -> None:
        """Codex round-3 P2-2: retire_row side of
        test_every_capable_role_can_approve_end_to_end."""
        row = self._deprecated_row(db)
        retired = repo.retire_row(db, row, actor_user_id="reviewer-2", actor_role=role)
        assert retired.status == "retired"

    def test_rejects_row_marked_for_deletion_not_yet_flushed(self, db) -> None:
        """Codex round-3 P1-1, retire_row side — see TestApproveRow's
        matching test for full rationale."""
        row = self._deprecated_row(db)
        row_id = row.id
        db.delete(row)
        assert row in db.deleted

        with pytest.raises(repo.TransitionError, match="marked for deletion"):
            repo.retire_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)

        assert not db.in_transaction()

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row_id)
            assert persisted is not None, "the row must not have been deleted"
            assert persisted.status == "deprecated"
        finally:
            fresh.close()

    def test_rejects_row_already_flushed_as_deleted(self, db) -> None:
        """Codex round-3 P1-1, retire_row side — see TestApproveRow's
        matching test for full rationale (round-4: match now accepts
        `_lock_canonical_row`'s "does not exist" too — see that test's
        updated docstring for why)."""
        row = self._deprecated_row(db)
        row_id = row.id
        db.delete(row)
        db.flush()

        with pytest.raises(repo.TransitionError, match="does not exist|marked for deletion"):
            repo.retire_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)

        assert not db.in_transaction()

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row_id)
            assert persisted is not None, "the already-flushed DELETE must be rolled back"
            assert persisted.status == "deprecated"
        finally:
            fresh.close()

    def test_rejects_spoofed_object_when_real_row_has_unflushed_pending_delete(
        self, db
    ) -> None:
        """Codex round-4 P1, retire_row side — see TestApproveRow's
        matching test for full rationale."""
        row = self._deprecated_row(db)
        row_id = row.id
        drug_ingredient_id = row.drug_ingredient_id
        db.delete(row)
        assert row in db.deleted

        spoofed = DrugUsage(
            id=row_id,
            drug_ingredient_id=drug_ingredient_id,
            locale="vi",
            audience="patient",
            content="spoofed — never persisted",
            authored_by="not-the-real-author",
            status="deprecated",
            status_changed_by="not-the-real-author",
        )
        assert spoofed not in db
        assert spoofed not in db.deleted

        with pytest.raises(repo.TransitionError, match="marked for deletion"):
            repo.retire_row(db, spoofed, actor_user_id="reviewer-1", actor_role=self._ROLE)

        assert not db.in_transaction()

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row_id)
            assert persisted is not None, "the row must not have been deleted"
            assert persisted.status == "deprecated"
        finally:
            fresh.close()

    def test_rejects_spoofed_object_when_real_row_already_flushed_as_deleted(
        self, db
    ) -> None:
        """Codex round-4 P1 variant, retire_row side — see TestApproveRow's
        matching test for full rationale (match accepts `_lock_canonical_row`'s
        "does not exist" too — see that test's updated docstring)."""
        row = self._deprecated_row(db)
        row_id = row.id
        drug_ingredient_id = row.drug_ingredient_id
        db.delete(row)
        db.flush()

        spoofed = DrugUsage(
            id=row_id,
            drug_ingredient_id=drug_ingredient_id,
            locale="vi",
            audience="patient",
            content="spoofed — never persisted",
            authored_by="not-the-real-author",
            status="deprecated",
            status_changed_by="not-the-real-author",
        )
        assert spoofed not in db

        with pytest.raises(repo.TransitionError, match="does not exist|marked for deletion"):
            repo.retire_row(db, spoofed, actor_user_id="reviewer-1", actor_role=self._ROLE)

        assert not db.in_transaction()

        from app.core.database import SessionLocal

        fresh = SessionLocal()
        try:
            persisted = fresh.get(DrugUsage, row_id)
            assert persisted is not None, "the already-flushed DELETE must be rolled back"
            assert persisted.status == "deprecated"
        finally:
            fresh.close()

    def test_unauthorized_call_from_clean_session_leaves_no_open_transaction(self, db) -> None:
        """Codex round-3 P1-3 clean-baseline test, retire_row side — see
        TestApproveRow's matching test for full rationale."""
        row = self._deprecated_row(db)
        db.commit()
        assert not db.in_transaction()

        with pytest.raises(repo.KnowledgeApprovalAuthorizationError):
            repo.retire_row(db, row, actor_user_id="reviewer-1", actor_role="patient")

        assert not db.in_transaction()
        db.refresh(row)
        assert row.status == "deprecated"


_ALL_KNOWLEDGE_MODELS = [
    DrugUsage,
    DrugPatientEducation,
    DrugSideEffect,
    DrugMonitoring,
    DrugContraindication,
]


def _model_fields(model_cls: type, ingredient_id: str, *, variant: str = "v1") -> dict[str, object]:
    """Field factory for building a valid content row for any of the 5
    in-scope models. Business-key fields are fixed per call; `variant`
    only ever touches a non-business-key field, so two calls with the
    same ingredient_id and different variant share one business key
    (used for supersession tests) while two calls with different
    ingredient_id never do."""
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


class TestApproveRetireAcrossAllKnowledgeModels:
    """Codex round-1 P2-2: TestApproveRow/TestRetireRow above only ever
    exercise DrugUsage. approve_row/retire_row are generic across all 5
    in-scope models (the KnowledgeModel TypeVar) — a bug in model
    dispatch, or in one specific model's own `_BUSINESS_KEY_FIELDS` tuple,
    would go completely undetected without exercising the real write path
    for each. This class is a smoke suite, not full behavioral coverage —
    TestApproveRow/TestRetireRow already cover the full behavioral matrix
    (self-approval, specialty gates, illegal transitions, concurrency, ...)
    in depth for DrugUsage; this only proves the same core mechanics
    (approve, same-key supersession, different-key non-supersession,
    retire) hold for all 5 models, including DrugUsage again for symmetry.
    """

    _ROLE = "internal_admin"

    @pytest.fixture(autouse=True)
    def _cleanup_approved_rows(self, db):
        """See TestApproveRow._cleanup_approved_rows — same shared
        session-scoped SQLite fixture, same reasoning, generalized across
        all 5 models since this class exercises every one of them."""
        existing_ids = {m: {row.id for row in db.query(m.id).all()} for m in _ALL_KNOWLEDGE_MODELS}
        yield
        db.rollback()
        for m in _ALL_KNOWLEDGE_MODELS:
            for row in db.query(m).filter(~m.id.in_(existing_ids[m])).all():
                db.delete(row)
        db.commit()

    @pytest.mark.parametrize("model_cls", _ALL_KNOWLEDGE_MODELS)
    def test_happy_path_approve_supersede_and_retire(self, db, model_cls) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db, model_cls, authored_by="author-1", **_model_fields(model_cls, ingredient.id)
        )
        repo.submit_for_review(db, row, actor_user_id="author-1")
        approved = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        assert approved.status == "approved"

        second = repo.create_draft(
            db,
            model_cls,
            authored_by="author-1",
            **_model_fields(model_cls, ingredient.id, variant="v2"),
        )
        repo.submit_for_review(db, second, actor_user_id="author-1")
        second = repo.approve_row(db, second, actor_user_id="reviewer-1", actor_role=self._ROLE)
        assert second.status == "approved"

        db.refresh(approved)
        assert approved.status == "deprecated", (
            f"{model_cls.__name__}: same-business-key supersession must "
            "deprecate the prior approved row"
        )

        retired = repo.retire_row(db, approved, actor_user_id="reviewer-1", actor_role=self._ROLE)
        assert retired.status == "retired"

    @pytest.mark.parametrize("model_cls", _ALL_KNOWLEDGE_MODELS)
    def test_different_business_key_does_not_supersede(self, db, model_cls) -> None:
        """A second approval for a DIFFERENT business key (different
        ingredient) must NOT deprecate the first — proves
        _deprecate_superseded's per-model business-key filter is scoped
        correctly, not accidentally matching every row of that model
        regardless of business key."""
        ingredient_a = _make_ingredient(db)
        ingredient_b = _make_ingredient(db)

        row_a = repo.create_draft(
            db, model_cls, authored_by="author-1", **_model_fields(model_cls, ingredient_a.id)
        )
        repo.submit_for_review(db, row_a, actor_user_id="author-1")
        approved_a = repo.approve_row(db, row_a, actor_user_id="reviewer-1", actor_role=self._ROLE)

        row_b = repo.create_draft(
            db, model_cls, authored_by="author-1", **_model_fields(model_cls, ingredient_b.id)
        )
        repo.submit_for_review(db, row_b, actor_user_id="author-1")
        approved_b = repo.approve_row(db, row_b, actor_user_id="reviewer-1", actor_role=self._ROLE)

        db.refresh(approved_a)
        assert approved_a.status == "approved", (
            f"{model_cls.__name__}: a different business key must never be superseded"
        )
        assert approved_b.status == "approved"


# Per-model, per-secondary-field alternate value pairs (drug_ingredient_id
# is excluded — already covered by test_different_business_key_does_not_
# supersede above). Codex round-2 P3-1: the existing cross-model tests
# only ever vary drug_ingredient_id when proving non-supersession — if
# _BUSINESS_KEY_FIELDS were ever accidentally reduced to just
# ("drug_ingredient_id",) for any model, every existing K1.5 test would
# still pass, since none of them independently vary a SECONDARY key field
# while holding the ingredient fixed.
_SECONDARY_KEY_FIELD_ALTERNATES: dict[type, dict[str, tuple[object, object]]] = {
    DrugUsage: {
        "locale": ("vi", "en"),
        "audience": ("patient", "caregiver"),
    },
    DrugPatientEducation: {
        "theme": ("general", "diet"),
        "locale": ("vi", "en"),
        "audience": ("patient", "caregiver"),
    },
    DrugSideEffect: {
        "concept_code": ("nausea", "headache"),
    },
    DrugMonitoring: {
        "parameter": ("renal_function", "liver_function"),
        "patient_context": ("baseline", "pregnancy"),
    },
    DrugContraindication: {
        "condition_type": ("disease", "allergy"),
        "condition_key": ("ckd_stage4", "penicillin_allergy"),
    },
}

_SECONDARY_KEY_FIELD_CASES = [
    (model_cls, field_name)
    for model_cls, fields in _SECONDARY_KEY_FIELD_ALTERNATES.items()
    for field_name in fields
]


class TestBusinessKeyFieldsAreFullyEnforced:
    """Codex round-2 P3-1: for every (model, secondary business-key field)
    pair, two approved rows sharing the same ingredient but differing in
    exactly that one field must NOT supersede each other — proving each
    field genuinely participates in `_BUSINESS_KEY_FIELDS`/the DB partial
    unique index, not just `drug_ingredient_id`. Must fail if
    `_BUSINESS_KEY_FIELDS` for any model is ever reduced to just
    `("drug_ingredient_id",)`.

    The complementary case — full key match causes supersession — is
    already covered by
    TestApproveRetireAcrossAllKnowledgeModels.test_happy_path_approve_supersede_and_retire
    (keeps every business-key field identical across v1/v2, varies only a
    non-key field)."""

    _ROLE = "internal_admin"

    @pytest.fixture(autouse=True)
    def _cleanup_approved_rows(self, db):
        """See TestApproveRow._cleanup_approved_rows — same shared
        session-scoped SQLite fixture, generalized across all 5 models."""
        existing_ids = {m: {row.id for row in db.query(m.id).all()} for m in _ALL_KNOWLEDGE_MODELS}
        yield
        db.rollback()
        for m in _ALL_KNOWLEDGE_MODELS:
            for row in db.query(m).filter(~m.id.in_(existing_ids[m])).all():
                db.delete(row)
        db.commit()

    @pytest.mark.parametrize("model_cls,field_name", _SECONDARY_KEY_FIELD_CASES)
    def test_differing_secondary_field_does_not_supersede(
        self, db, model_cls, field_name
    ) -> None:
        ingredient = _make_ingredient(db)
        value_a, value_b = _SECONDARY_KEY_FIELD_ALTERNATES[model_cls][field_name]

        fields_a = _model_fields(model_cls, ingredient.id)
        fields_a[field_name] = value_a
        row_a = repo.create_draft(db, model_cls, authored_by="author-1", **fields_a)
        repo.submit_for_review(db, row_a, actor_user_id="author-1")
        approved_a = repo.approve_row(db, row_a, actor_user_id="reviewer-1", actor_role=self._ROLE)

        fields_b = _model_fields(model_cls, ingredient.id)
        fields_b[field_name] = value_b
        row_b = repo.create_draft(db, model_cls, authored_by="author-1", **fields_b)
        repo.submit_for_review(db, row_b, actor_user_id="author-1")
        approved_b = repo.approve_row(db, row_b, actor_user_id="reviewer-1", actor_role=self._ROLE)

        db.refresh(approved_a)
        assert approved_a.status == "approved", (
            f"{model_cls.__name__}.{field_name}: rows sharing the same ingredient "
            "but differing only in this secondary business-key field must NOT "
            "supersede each other — if this fails, _BUSINESS_KEY_FIELDS is "
            "missing this field for this model"
        )
        assert approved_b.status == "approved"


class TestRollbackAtomicity:
    def test_missing_required_field_rolls_back_cleanly(self, db) -> None:
        """drug_ingredient_id is NOT NULL — omitting it must raise
        IntegrityError and leave no partial row behind."""
        before = db.query(DrugUsage).count()
        with pytest.raises(IntegrityError):
            repo.create_draft(
                db,
                DrugUsage,
                authored_by="author-1",
                locale="vi",
                audience="patient",
                content="content",
                # drug_ingredient_id intentionally omitted
            )
        after = db.query(DrugUsage).count()
        assert after == before
        # Session must be usable again after rollback — prove it by doing a
        # normal successful write right after.
        db.rollback()
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        assert row.id is not None


# ============================================================================
# 2026-07-27 final-checkpoint additions (PTH decision: KEEP
# knowledge_lifecycle_transitions; close automated test gaps before final
# review). Five categories below, per the checkpoint's own §D test list.
# ============================================================================


def _cleanup_domain_rows(db, existing_ids: set[str]) -> None:
    """Shared teardown for every class below — same shared-session SQLite
    constraint as TestApproveRow/TestRetireRow's own `_cleanup_approved_rows`
    (tests/conftest.py's `db` fixture has no per-test rollback). Deletes,
    scoped strictly by captured ids: lifecycle-transition rows referencing
    any DrugUsage row this test created, then the DrugUsage rows
    themselves — never table-wide."""
    db.rollback()
    new_rows = db.query(DrugUsage).filter(~DrugUsage.id.in_(existing_ids)).all()
    new_ids = [row.id for row in new_rows]
    if new_ids:
        db.query(KnowledgeLifecycleTransition).filter(
            KnowledgeLifecycleTransition.knowledge_table == "drug_usage",
            KnowledgeLifecycleTransition.knowledge_row_id.in_(new_ids),
        ).delete(synchronize_session=False)
    for row in new_rows:
        db.delete(row)
    db.commit()


class TestRejectRow:
    _ROLE = "internal_admin"

    @pytest.fixture(autouse=True)
    def _cleanup(self, db):
        existing_ids = {row.id for row in db.query(DrugUsage.id).all()}
        yield
        _cleanup_domain_rows(db, existing_ids)

    def _submitted_row(self, db, **overrides):
        ingredient = _make_ingredient(db)
        fields = dict(
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="synthetic test content — never staged/production",
            **_approval_provenance_fields(),
        )
        fields.update(overrides)
        row = repo.create_draft(db, DrugUsage, authored_by="author-1", **fields)
        repo.submit_for_review(db, row, actor_user_id="author-1")
        return row

    def test_only_clinical_review_can_transition_to_rejected(self, db) -> None:
        ingredient = _make_ingredient(db)
        draft_row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
        )
        with pytest.raises(repo.TransitionError, match="Illegal transition"):
            repo.reject_row(
                db,
                draft_row,
                actor_user_id="reviewer-1",
                actor_role=self._ROLE,
                reason_code="insufficient_evidence",
                rationale="Synthetic test rationale — no clinical content.",
            )
        db.refresh(draft_row)
        assert draft_row.status == "draft"

    def test_reason_code_is_required(self, db) -> None:
        row = self._submitted_row(db)
        with pytest.raises(TypeError):
            repo.reject_row(  # type: ignore[call-arg]
                db,
                row,
                actor_user_id="reviewer-1",
                actor_role=self._ROLE,
                rationale="Missing reason_code on purpose.",
            )

    def test_rationale_is_required(self, db) -> None:
        row = self._submitted_row(db)
        with pytest.raises(TypeError):
            repo.reject_row(  # type: ignore[call-arg]
                db,
                row,
                actor_user_id="reviewer-1",
                actor_role=self._ROLE,
                reason_code="insufficient_evidence",
            )

    def test_rationale_is_stored_as_supplied(self, db) -> None:
        """`rationale` must round-trip exactly. PHI-freedom itself is a
        caller discipline this module documents (same as
        app/services/audit.py's `details` field) — there is no runtime PHI
        content scanner in this module, so this test proves faithful
        storage of a synthetic, deliberately PHI-free value, not a policy
        enforcement mechanism that does not exist."""
        row = self._submitted_row(db)
        rejected = repo.reject_row(
            db,
            row,
            actor_user_id="reviewer-1",
            actor_role=self._ROLE,
            reason_code="insufficient_evidence",
            rationale="Synthetic, PHI-free: evidence citation is a dead link.",
        )
        assert rejected.status == "rejected"

        transition = (
            db.query(KnowledgeLifecycleTransition)
            .filter_by(knowledge_table="drug_usage", knowledge_row_id=rejected.id)
            .filter_by(to_status="rejected")
            .one()
        )
        assert transition.reason_code == "insufficient_evidence"
        assert transition.rationale == "Synthetic, PHI-free: evidence citation is a dead link."

    def test_actor_is_recorded_on_the_row_and_the_transition(self, db) -> None:
        row = self._submitted_row(db)
        rejected = repo.reject_row(
            db,
            row,
            actor_user_id="reviewer-1",
            actor_role=self._ROLE,
            reason_code="insufficient_evidence",
            rationale="Synthetic test rationale.",
        )
        assert rejected.status_changed_by == "reviewer-1"
        transition = (
            db.query(KnowledgeLifecycleTransition)
            .filter_by(knowledge_table="drug_usage", knowledge_row_id=rejected.id)
            .filter_by(to_status="rejected")
            .one()
        )
        assert transition.actor_id == "reviewer-1"
        assert transition.actor_role == self._ROLE
        assert transition.from_status == "clinical_review"
        assert transition.to_status == "rejected"
        assert transition.transitioned_at is not None

    def test_transition_history_row_is_written(self, db) -> None:
        row = self._submitted_row(db)
        before = db.query(KnowledgeLifecycleTransition).count()
        repo.reject_row(
            db,
            row,
            actor_user_id="reviewer-1",
            actor_role=self._ROLE,
            reason_code="insufficient_evidence",
            rationale="Synthetic test rationale.",
        )
        # +1 for submit_for_review (draft->clinical_review), +1 for this
        # reject (clinical_review->rejected) — both already committed by
        # the time this test's own before/after count runs.
        after = db.query(KnowledgeLifecycleTransition).count()
        assert after == before + 1

    def test_rejected_row_excluded_from_k1_6_retrieval(self, db) -> None:
        from app.services import knowledge_retrieval as retrieval

        row = self._submitted_row(db)
        rejected = repo.reject_row(
            db,
            row,
            actor_user_id="reviewer-1",
            actor_role=self._ROLE,
            reason_code="insufficient_evidence",
            rationale="Synthetic test rationale.",
        )
        found = retrieval.get_current_by_business_key(
            db,
            DrugUsage,
            drug_ingredient_id=rejected.drug_ingredient_id,
            locale="vi",
            audience="patient",
        )
        assert found is None
        current_list = retrieval.list_current_for_ingredient(
            db, DrugUsage, rejected.drug_ingredient_id
        )
        assert rejected.id not in {r.id for r in current_list}

    def test_rejected_row_excluded_from_k2_response_building(self, db) -> None:
        """K2's own response builders (medication_knowledge_response.py)
        only ever receive rows K1.6's retrieval layer already filtered to
        `status='approved'` — proven structurally by the retrieval test
        above; this test proves the same at the ORM query level K2 shares."""
        row = self._submitted_row(db)
        rejected = repo.reject_row(
            db,
            row,
            actor_user_id="reviewer-1",
            actor_role=self._ROLE,
            reason_code="insufficient_evidence",
            rationale="Synthetic test rationale.",
        )
        approved_count = (
            db.query(DrugUsage).filter_by(id=rejected.id, status="approved").count()
        )
        assert approved_count == 0

    def test_rejected_cannot_transition_directly_to_approved(self, db) -> None:
        row = self._submitted_row(db)
        rejected = repo.reject_row(
            db,
            row,
            actor_user_id="reviewer-1",
            actor_role=self._ROLE,
            reason_code="insufficient_evidence",
            rationale="Synthetic test rationale.",
        )
        with pytest.raises(repo.TransitionError, match="Illegal transition"):
            repo.approve_row(db, rejected, actor_user_id="reviewer-2", actor_role=self._ROLE)
        db.refresh(rejected)
        assert rejected.status == "rejected"

    def test_repeated_rejection_is_blocked(self, db) -> None:
        row = self._submitted_row(db)
        rejected = repo.reject_row(
            db,
            row,
            actor_user_id="reviewer-1",
            actor_role=self._ROLE,
            reason_code="insufficient_evidence",
            rationale="First rejection.",
        )
        with pytest.raises(repo.TransitionError, match="Illegal transition"):
            repo.reject_row(
                db,
                rejected,
                actor_user_id="reviewer-2",
                actor_role=self._ROLE,
                reason_code="insufficient_evidence",
                rationale="Second rejection attempt.",
            )
        db.refresh(rejected)
        assert rejected.status == "rejected"

    def test_optimistic_concurrency_only_one_reject_wins(self, db) -> None:
        """Two sessions both read the row while it's still clinical_review,
        then both attempt the transition. Unlike submit_for_review (which
        validates against the caller-supplied in-memory row.status before
        its atomic UPDATE, so a race surfaces as "lost the atomic UPDATE"),
        reject_row re-locks the canonical row via `_lock_canonical_row`
        (a real SELECT-then-validate) BEFORE validate_transition ever
        runs — so the second, stale caller's race is caught one layer
        earlier, deterministically, as an "Illegal transition" (its
        freshly re-locked canonical status is already 'rejected' by the
        time it validates), never a silent double-rejection and never an
        unrelated error."""
        from app.core.database import SessionLocal

        row = self._submitted_row(db)
        row_id = row.id

        session_a = SessionLocal()
        session_b = SessionLocal()
        try:
            row_a = session_a.get(DrugUsage, row_id)
            row_b = session_b.get(DrugUsage, row_id)
            assert row_a.status == row_b.status == "clinical_review"

            repo.reject_row(
                session_a,
                row_a,
                actor_user_id="reviewer-1",
                actor_role=self._ROLE,
                reason_code="insufficient_evidence",
                rationale="Winner.",
            )
            assert row_a.status == "rejected"
            with pytest.raises(repo.TransitionError, match="Illegal transition"):
                repo.reject_row(
                    session_b,
                    row_b,
                    actor_user_id="reviewer-2",
                    actor_role=self._ROLE,
                    reason_code="insufficient_evidence",
                    rationale="Loser.",
                )
            # Exactly one rejection must persist — confirmed from a THIRD,
            # fresh connection so this isn't reading either racer's own
            # possibly-stale session state.
            verify_db = SessionLocal()
            try:
                final = verify_db.get(DrugUsage, row_id)
                assert final.status == "rejected"
            finally:
                verify_db.close()
        finally:
            session_a.close()
            session_b.close()


class TestSystemActorRestrictions:
    """Direct service-layer calls, not HTTP routes — no route exists yet
    for any of this module's write functions (module docstring: "No API
    route... touches this module yet")."""

    _ROLE = "internal_admin"

    @pytest.fixture(autouse=True)
    def _cleanup(self, db):
        existing_ids = {row.id for row in db.query(DrugUsage.id).all()}
        yield
        _cleanup_domain_rows(db, existing_ids)

    def _submitted_row(self, db, **overrides):
        ingredient = _make_ingredient(db)
        fields = dict(
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="synthetic test content — never staged/production",
            **_approval_provenance_fields(),
        )
        fields.update(overrides)
        row = repo.create_draft(db, DrugUsage, authored_by="author-1", **fields)
        repo.submit_for_review(db, row, actor_user_id="author-1")
        return row

    @pytest.mark.parametrize("system_actor", list(SystemActor))
    def test_every_system_actor_denied_by_approve_row(self, db, system_actor) -> None:
        row = self._submitted_row(db)
        with pytest.raises(repo.KnowledgeApprovalAuthorizationError, match="system-actor"):
            # actor_role="internal_admin" (spoofed authorization) must not
            # bypass the identity check.
            repo.approve_row(db, row, actor_user_id=system_actor.value, actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    @pytest.mark.parametrize("system_actor", list(SystemActor))
    def test_every_system_actor_denied_by_reject_row(self, db, system_actor) -> None:
        row = self._submitted_row(db)
        with pytest.raises(repo.KnowledgeApprovalAuthorizationError, match="system-actor"):
            repo.reject_row(
                db,
                row,
                actor_user_id=system_actor.value,
                actor_role=self._ROLE,
                reason_code="insufficient_evidence",
                rationale="Synthetic test rationale.",
            )
        db.refresh(row)
        assert row.status == "clinical_review"

    @pytest.mark.parametrize("system_actor", list(SystemActor))
    def test_every_system_actor_denied_by_retire_row(self, db, system_actor) -> None:
        row = self._submitted_row(db)
        approved = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        # deprecate it via a superseding approval so it reaches 'deprecated'
        second = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=approved.drug_ingredient_id,
            locale="vi",
            audience="patient",
            content="version 2",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, second, actor_user_id="author-1")
        repo.approve_row(db, second, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(approved)
        assert approved.status == "deprecated"

        with pytest.raises(repo.KnowledgeApprovalAuthorizationError, match="system-actor"):
            repo.retire_row(
                db, approved, actor_user_id=system_actor.value, actor_role=self._ROLE
            )
        db.refresh(approved)
        assert approved.status == "deprecated"

    def test_real_human_actor_still_succeeds(self, db) -> None:
        """Proves the system-actor check is a targeted denylist, not an
        overbroad guard that also blocks legitimate human approvers."""
        row = self._submitted_row(db)
        approved = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        assert approved.status == "approved"

    def test_forged_unregistered_system_actor_denied_by_approve_row(self, db) -> None:
        """Codex Round 1 finding #4 (fix round 1, 2026-07-28): before the
        fix, `assert_actor_is_not_system` called `is_system_actor` alone
        (True only for REGISTERED members) — an unregistered value like
        "system:attacker" made `is_system_actor` return False, so it
        silently passed the human-actor gate. This proves the reserved
        `system:` namespace itself is rejected, not just its finitely many
        registered members."""
        row = self._submitted_row(db)
        with pytest.raises(repo.KnowledgeApprovalAuthorizationError, match="reserved system-actor namespace"):
            repo.approve_row(db, row, actor_user_id="system:attacker", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_forged_unregistered_system_actor_denied_by_reject_row(self, db) -> None:
        row = self._submitted_row(db)
        with pytest.raises(repo.KnowledgeApprovalAuthorizationError, match="reserved system-actor namespace"):
            repo.reject_row(
                db,
                row,
                actor_user_id="system:attacker",
                actor_role=self._ROLE,
                reason_code="insufficient_evidence",
                rationale="Synthetic test rationale.",
            )
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_forged_unregistered_system_actor_denied_by_retire_row(self, db) -> None:
        row = self._submitted_row(db)
        approved = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        second = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=approved.drug_ingredient_id,
            locale="vi",
            audience="patient",
            content="version 2",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, second, actor_user_id="author-1")
        repo.approve_row(db, second, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(approved)
        assert approved.status == "deprecated"

        with pytest.raises(repo.KnowledgeApprovalAuthorizationError, match="reserved system-actor namespace"):
            repo.retire_row(db, approved, actor_user_id="system:attacker", actor_role=self._ROLE)
        db.refresh(approved)
        assert approved.status == "deprecated"

    def test_no_transition_row_written_when_system_actor_denied(self, db) -> None:
        row = self._submitted_row(db)
        before = db.query(KnowledgeLifecycleTransition).count()
        with pytest.raises(repo.KnowledgeApprovalAuthorizationError):
            repo.approve_row(
                db,
                row,
                actor_user_id=SystemActor.MEDICATION_AI_SYNTHESIS.value,
                actor_role=self._ROLE,
            )
        after = db.query(KnowledgeLifecycleTransition).count()
        assert after == before, (
            "a denied transition must never leave a history row behind — "
            "the check must fire before any write, including history"
        )


class TestAIProvenanceApprovalGuard:
    _ROLE = "internal_admin"

    @pytest.fixture(autouse=True)
    def _cleanup(self, db):
        existing_ids = {row.id for row in db.query(DrugUsage.id).all()}
        existing_gen_ids = {g.id for g in db.query(KnowledgeAIGeneration.id).all()}
        yield
        db.rollback()
        _cleanup_domain_rows(db, existing_ids)
        db.query(KnowledgeAIGeneration).filter(
            ~KnowledgeAIGeneration.id.in_(existing_gen_ids)
        ).delete(synchronize_session=False)
        db.commit()

    def _ai_synthesized_row(self, db, **overrides):
        ingredient = _make_ingredient(db)
        fields = dict(
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="synthetic AI-generated test content — never staged/production",
            origin="ai_synthesized",
            **_approval_provenance_fields(),
        )
        fields.update(overrides)
        row = repo.create_draft(
            db, DrugUsage, authored_by=SystemActor.MEDICATION_AI_SYNTHESIS.value, **fields
        )
        repo.submit_for_review(db, row, actor_user_id=SystemActor.MEDICATION_AI_SYNTHESIS.value)
        return row

    def _generation(self, db, *, target_row_id: str, knowledge_table: str = "drug_usage", **overrides):
        fields = dict(
            knowledge_table=knowledge_table,
            target_row_id=target_row_id,
            model_provider="synthetic-provider",
            model_identifier="synthetic-model-v1",
            prompt_template_id="synthetic-prompt",
            prompt_template_version="1.0",
            input_source_ids=[],
            # Fix round 3, 2026-07-28 (Codex Round 3 hash-format
            # enforcement): must be a real 64-char lowercase hex string —
            # "synthetic-hash" no longer passes ORM validation.
            input_hash="a" * 64,
            # Fix round 1, 2026-07-28 (Codex Round 1 finding #5): approval
            # now requires a non-empty output_hash — every test exercising
            # the SUCCESS path needs one by default; the test proving the
            # missing-output_hash case overrides it explicitly to None.
            output_hash="b" * 64,
            generation_status="succeeded",
            created_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
        )
        fields.update(overrides)
        gen = KnowledgeAIGeneration(**fields)
        db.add(gen)
        db.commit()
        return gen

    def test_no_generation_record_cannot_be_approved(self, db) -> None:
        row = self._ai_synthesized_row(db)
        with pytest.raises(repo.AIProvenanceIncompleteError, match="refusing to approve"):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_failed_generation_cannot_support_approval(self, db) -> None:
        row = self._ai_synthesized_row(db)
        self._generation(db, target_row_id=row.id, generation_status="failed")
        with pytest.raises(repo.AIProvenanceIncompleteError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    @pytest.mark.parametrize(
        "missing_field", ["model_identifier", "prompt_template_id", "prompt_template_version"]
    )
    def test_incomplete_generation_provenance_cannot_support_approval(
        self, db, missing_field
    ) -> None:
        row = self._ai_synthesized_row(db)
        self._generation(db, target_row_id=row.id, **{missing_field: ""})
        with pytest.raises(repo.AIProvenanceIncompleteError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_generation_linked_to_a_different_knowledge_row_cannot_support_approval(
        self, db
    ) -> None:
        row = self._ai_synthesized_row(db)
        other_row = self._ai_synthesized_row(db)
        # Complete, successful generation — but targeting `other_row`, not `row`.
        self._generation(db, target_row_id=other_row.id)
        with pytest.raises(repo.AIProvenanceIncompleteError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_generation_for_the_wrong_knowledge_table_cannot_support_approval(self, db) -> None:
        row = self._ai_synthesized_row(db)
        # Same target_row_id, but a knowledge_table value that doesn't
        # match DrugUsage's own table name — proves the query matches on
        # BOTH (knowledge_table, target_row_id) together, not id alone.
        self._generation(db, target_row_id=row.id, knowledge_table="drug_side_effects")
        with pytest.raises(repo.AIProvenanceIncompleteError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_successful_complete_generation_plus_authorized_human_approval_succeeds(
        self, db
    ) -> None:
        row = self._ai_synthesized_row(db)
        generation = self._generation(db, target_row_id=row.id)
        approved = repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        assert approved.status == "approved"
        # Fix round 1, 2026-07-28 (Codex Round 1 finding #5): approval must
        # atomically promote the authoritative generation — it must never
        # remain 'pending' after a successful approval relied on it.
        db.refresh(generation)
        assert generation.review_status == "promoted"
        # Fix round 1 finding #6: reviewed_by is bound to the approving actor.
        assert approved.reviewed_by == "reviewer-1"

    def test_missing_output_hash_cannot_support_approval(self, db) -> None:
        """Fix round 3, 2026-07-28: output_hash is nullable — "" is no
        longer a constructible value (fails ORM hash-format validation
        outright), so the missing-hash case is now represented by None,
        which still correctly fails the truthiness check inside
        `_select_and_promote_ai_generation`."""
        row = self._ai_synthesized_row(db)
        self._generation(db, target_row_id=row.id, output_hash=None)
        with pytest.raises(repo.AIProvenanceIncompleteError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_malformed_output_hash_rejected_by_orm(self, db) -> None:
        """Codex Round 3: a structurally invalid hash (wrong length, or
        containing non-hex/uppercase characters) must be rejected at
        construction time, not silently accepted as "some string"."""
        with pytest.raises(ValueError, match="SHA-256"):
            KnowledgeAIGeneration(
                knowledge_table="drug_usage",
                target_row_id=None,
                model_provider="p",
                model_identifier="m",
                prompt_template_id="pt",
                prompt_template_version="1",
                input_source_ids=[],
                input_hash="a" * 64,
                output_hash="not-a-valid-hash",
                generation_status="succeeded",
                created_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
            )

    def test_generation_by_non_ai_synthesis_actor_cannot_support_approval(self, db) -> None:
        """created_by must name the specific AI-synthesis actor — a
        different, otherwise-legitimate, registered SystemActor (e.g. the
        migration/backfill actor) must not qualify (Codex Round 1
        finding #5)."""
        row = self._ai_synthesized_row(db)
        self._generation(db, target_row_id=row.id, created_by=SystemActor.MEDICATION_MIGRATION.value)
        with pytest.raises(repo.AIProvenanceIncompleteError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_non_pending_generation_cannot_support_a_second_approval(self, db) -> None:
        """A generation already promoted/rejected/superseded by an earlier
        decision must not be reusable to authorize a second approval
        (Codex Round 1 finding #5 — "an admissible review_status")."""
        row = self._ai_synthesized_row(db)
        self._generation(db, target_row_id=row.id, review_status="promoted")
        with pytest.raises(repo.AIProvenanceIncompleteError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_latest_generation_failing_blocks_approval_even_if_an_older_one_succeeded(
        self, db
    ) -> None:
        """Codex Round 1 finding #5: the authoritative generation is the
        single MOST RECENT non-superseded attempt, checked by its OWN
        status — an older succeeded attempt must not let approval succeed
        if the actual latest attempt has since failed.

        `sequence_number` set explicitly (fix round 3, 2026-07-28): this
        suite's SQLite database is built via `create_all()`, not a real
        `alembic upgrade head` — so the SQLite AFTER INSERT trigger that
        auto-assigns `sequence_number` in production/migrated databases
        never runs here, and the column would otherwise stay NULL for
        every row. Setting it directly proves the higher-level ordering
        behavior (`_select_and_promote_ai_generation` picks the highest
        `sequence_number`) independent of trigger auto-assignment, which
        is instead verified against a real migrated database in
        tests/test_medication_k2_s0_migrations_sqlite.py and
        tests/integration/test_medication_k2_s0_round3_hardening_postgres.py."""
        row = self._ai_synthesized_row(db)
        base = dt.datetime.now(dt.UTC)
        self._generation(db, target_row_id=row.id, created_at=base - dt.timedelta(hours=1), sequence_number=1)
        self._generation(
            db, target_row_id=row.id, generation_status="failed", created_at=base, sequence_number=2
        )
        with pytest.raises(repo.AIProvenanceIncompleteError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_approval_promotion_only_touches_review_status(self, db) -> None:
        """Real behavioral proof (Codex Round 1 finding #9), referenced by
        TestAppendOnlyHistoryEnforcement's grep-guard: the promotion UPDATE
        inside approve_row must change `review_status` alone — every other
        column on the generation record (including its own immutable
        provenance fields) must survive completely unchanged."""
        row = self._ai_synthesized_row(db)
        generation = self._generation(db, target_row_id=row.id)
        before = {
            "knowledge_table": generation.knowledge_table,
            "target_row_id": generation.target_row_id,
            "model_provider": generation.model_provider,
            "model_identifier": generation.model_identifier,
            "prompt_template_id": generation.prompt_template_id,
            "prompt_template_version": generation.prompt_template_version,
            "input_hash": generation.input_hash,
            "output_hash": generation.output_hash,
            "generation_status": generation.generation_status,
            "origin": generation.origin,
            "created_by": generation.created_by,
            "created_at": generation.created_at,
            "superseded_by_generation_id": generation.superseded_by_generation_id,
        }
        assert generation.review_status == "pending"

        repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)

        db.refresh(generation)
        assert generation.review_status == "promoted"
        after = {
            "knowledge_table": generation.knowledge_table,
            "target_row_id": generation.target_row_id,
            "model_provider": generation.model_provider,
            "model_identifier": generation.model_identifier,
            "prompt_template_id": generation.prompt_template_id,
            "prompt_template_version": generation.prompt_template_version,
            "input_hash": generation.input_hash,
            "output_hash": generation.output_hash,
            "generation_status": generation.generation_status,
            "origin": generation.origin,
            "created_by": generation.created_by,
            "created_at": generation.created_at,
            "superseded_by_generation_id": generation.superseded_by_generation_id,
        }
        assert before == after, "promotion must change review_status alone"

    def test_generation_success_never_auto_approves(self, db) -> None:
        """Creating a complete, successful generation record must never,
        on its own, change the knowledge row's status — approval always
        requires a separate, explicit approve_row call by an authorized
        human."""
        row = self._ai_synthesized_row(db)
        self._generation(db, target_row_id=row.id)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_multiple_generations_choose_the_most_recent_qualifying_record(self, db) -> None:
        """Ordering is by `sequence_number` (fix round 3, 2026-07-28 —
        formerly `created_at DESC`, replaced because `created_at` can
        genuinely tie; see `k2_s0_round3_hardening`). The MOST RECENT
        qualifying (succeeded, non-superseded) generation is authoritative,
        deterministically. An older COMPLETE generation must not let
        approval succeed if a NEWER qualifying generation is incomplete —
        the newest attempt's provenance is what's actually being approved.
        `sequence_number` is set explicitly (this suite's `create_all()`
        SQLite database never runs the real trigger that auto-assigns it —
        see the sibling test above for the full explanation)."""
        row = self._ai_synthesized_row(db)
        base = dt.datetime.now(dt.UTC)
        older = self._generation(
            db, target_row_id=row.id, created_at=base - dt.timedelta(hours=1), sequence_number=1
        )
        newer = self._generation(
            db, target_row_id=row.id, prompt_template_version="", created_at=base, sequence_number=2
        )
        assert newer.created_at > older.created_at
        with pytest.raises(repo.AIProvenanceIncompleteError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_superseded_generation_cannot_support_approval(self, db) -> None:
        row = self._ai_synthesized_row(db)
        original = self._generation(db, target_row_id=row.id)
        replacement = self._generation(db, target_row_id=row.id)
        original.superseded_by_generation_id = replacement.id
        db.commit()
        # Mark the replacement itself incomplete so ONLY the (now
        # superseded) original would otherwise have qualified — proving
        # the superseded one is genuinely excluded, not just outranked by
        # a better candidate.
        replacement.prompt_template_version = ""
        db.commit()
        with pytest.raises(repo.AIProvenanceIncompleteError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)
        db.refresh(row)
        assert row.status == "clinical_review"

    def test_deterministic_selection_survives_reload(self, db) -> None:
        """Same requirement as the Postgres equivalent — the authoritative
        generation must be re-derived identically from a brand-new session,
        not merely cached within the session that created it.
        `sequence_number` set explicitly — see
        test_latest_generation_failing_blocks_approval_even_if_an_older_one_succeeded
        for why this suite's `create_all()` SQLite database never
        auto-assigns it. The trigger-based tie-breaking behavior itself is
        covered by tests/test_medication_k2_s0_migrations_sqlite.py and
        tests/integration/test_medication_k2_s0_round3_hardening_postgres.py,
        both of which run against a real `alembic upgrade head` database."""
        row = self._ai_synthesized_row(db)
        self._generation(db, target_row_id=row.id, generation_status="failed", sequence_number=1)
        authoritative = self._generation(
            db, target_row_id=row.id, generation_status="succeeded", sequence_number=2
        )
        row_id = row.id
        authoritative_id = authoritative.id
        db.close()

        reload_db = SessionLocal()
        try:
            approved = repo.approve_row(
                reload_db,
                reload_db.get(DrugUsage, row_id),
                actor_user_id="reviewer-1",
                actor_role=self._ROLE,
            )
            assert approved.status == "approved"
            promoted = reload_db.get(KnowledgeAIGeneration, authoritative_id)
            assert promoted.review_status == "promoted"
        finally:
            reload_db.close()


class TestConcurrentAIPromotion:
    """Codex Round 1 finding #5 / user Fix Round 1 instruction ("Add
    concurrency and transaction rollback tests for AI promotion"). Two
    genuinely separate DB sessions/threads race to approve the SAME
    ai_synthesized row backed by the SAME single qualifying generation —
    exactly one must win, the other must lose cleanly (no dangling
    'promoted' generation with no matching approved row, no corrupted
    row status), proving `_select_and_promote_ai_generation`'s
    `UPDATE ... WHERE review_status = 'pending'` optimistic-concurrency
    check is a real backstop, not just a theoretical one."""

    _ROLE = "internal_admin"

    @pytest.fixture(autouse=True)
    def _cleanup(self, db):
        existing_ids = {row.id for row in db.query(DrugUsage.id).all()}
        existing_gen_ids = {g.id for g in db.query(KnowledgeAIGeneration.id).all()}
        yield
        db.rollback()
        _cleanup_domain_rows(db, existing_ids)
        db.query(KnowledgeAIGeneration).filter(
            ~KnowledgeAIGeneration.id.in_(existing_gen_ids)
        ).delete(synchronize_session=False)
        db.commit()

    def test_two_concurrent_approvals_racing_the_same_generation_only_one_wins(self) -> None:
        setup_db = SessionLocal()
        try:
            ingredient = _make_ingredient(setup_db)
            row = repo.create_draft(
                setup_db,
                DrugUsage,
                authored_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
                drug_ingredient_id=ingredient.id,
                locale="vi",
                audience="patient",
                content="synthetic AI-generated test content — never staged/production",
                origin="ai_synthesized",
                source="Synthetic Test Source",
                version="1.0",
                evidence_level="expert_opinion",
                last_reviewed_at=dt.datetime.now(dt.UTC),
            )
            repo.submit_for_review(setup_db, row, actor_user_id=SystemActor.MEDICATION_AI_SYNTHESIS.value)
            row_id = row.id
            generation = KnowledgeAIGeneration(
                knowledge_table="drug_usage",
                target_row_id=row_id,
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
            setup_db.add(generation)
            setup_db.commit()
            generation_id = generation.id
        finally:
            setup_db.close()

        results: dict[str, tuple[str, object]] = {}
        start = threading.Barrier(2, timeout=15)

        def _attempt(actor_user_id: str) -> None:
            db = SessionLocal()
            try:
                start.wait()
                row_ref = db.get(DrugUsage, row_id)
                approved = repo.approve_row(
                    db, row_ref, actor_user_id=actor_user_id, actor_role=self._ROLE
                )
                results[actor_user_id] = ("success", approved.status)
            except Exception as exc:  # noqa: BLE001 — cross-thread result capture only
                results[actor_user_id] = ("failure", exc)
            finally:
                db.close()

        t1 = threading.Thread(target=_attempt, args=("reviewer-a",))
        t2 = threading.Thread(target=_attempt, args=("reviewer-b",))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        outcomes = [results["reviewer-a"][0], results["reviewer-b"][0]]
        assert outcomes.count("success") == 1, (
            f"exactly one concurrent approval must win the race, got {results}"
        )
        assert outcomes.count("failure") == 1, (
            f"the loser must fail cleanly (TransitionError or "
            f"AIProvenanceIncompleteError), got {results}"
        )

        verify_db = SessionLocal()
        try:
            final_row = verify_db.get(DrugUsage, row_id)
            assert final_row.status == "approved", (
                "the row must end up approved exactly once — never stuck "
                "mid-transition, never approved twice"
            )
            final_generation = verify_db.get(KnowledgeAIGeneration, generation_id)
            assert final_generation.review_status == "promoted", (
                "the winning transaction's promotion must be durably "
                "committed — never left 'pending' after a successful approval"
            )
        finally:
            verify_db.close()

    def test_rollback_leaves_generation_pending_when_row_transition_is_invalid(self, db) -> None:
        """Transaction-rollback proof: `_select_and_promote_ai_generation`
        runs and tentatively promotes the generation BEFORE
        `validate_transition` checks the row's own current status
        (approve_row's own call order). If the row's real, persisted
        status has concurrently moved to something `clinical_review ->
        approved` no longer legally follows from (simulated here via a
        direct SQL UPDATE bypassing the service layer, standing in for a
        concurrent transaction that changed it), `validate_transition`
        raises AFTER the promotion already ran in the same open
        transaction — the whole transaction, including that tentative
        promotion, must roll back. The generation must be left exactly as
        it was: 'pending', never durably promoted without its row being
        approved."""
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="synthetic AI-generated test content — never staged/production",
            origin="ai_synthesized",
            source="Synthetic Test Source",
            version="1.0",
            evidence_level="expert_opinion",
            last_reviewed_at=dt.datetime.now(dt.UTC),
        )
        repo.submit_for_review(db, row, actor_user_id=SystemActor.MEDICATION_AI_SYNTHESIS.value)
        generation = KnowledgeAIGeneration(
            knowledge_table="drug_usage",
            target_row_id=row.id,
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
        db.add(generation)
        db.commit()

        # Simulates a concurrent transaction rejecting the row — raw SQL,
        # bypassing the ORM @validates hooks and the service layer
        # entirely, so the row's real persisted status is now 'rejected'
        # when approve_row re-fetches it, while this test's own stale
        # `row` object still thinks it is 'clinical_review'.
        from sqlalchemy import text as sa_text

        db.execute(
            sa_text("UPDATE drug_usage SET status = 'rejected' WHERE id = :id"),
            {"id": row.id},
        )
        db.commit()

        with pytest.raises(repo.TransitionError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role=self._ROLE)

        db.rollback()
        db.refresh(generation)
        assert generation.review_status == "pending", (
            "the generation's tentative promotion must roll back completely "
            "when the row-level transition it belongs to is illegal"
        )
        db.refresh(row)
        assert row.status == "rejected", "the row's real persisted status is untouched by the failed attempt"


class TestOriginAndStatusValidation:
    @pytest.fixture(autouse=True)
    def _cleanup(self, db):
        existing_ids = {row.id for row in db.query(DrugUsage.id).all()}
        yield
        _cleanup_domain_rows(db, existing_ids)

    @pytest.mark.parametrize("origin_value", ORIGIN_VALUES)
    def test_all_four_governed_origin_values_accepted(self, db, origin_value) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
            origin=origin_value,
        )
        assert row.origin == origin_value

    @pytest.mark.parametrize("status_value", STATUS_VALUES)
    def test_all_six_canonical_status_values_accepted_as_transition_to_status(
        self, db, status_value
    ) -> None:
        """Companion to test_all_four_governed_origin_values_accepted
        above, for the DB-level CHECK constraint added to
        KnowledgeLifecycleTransition.to_status (§C)."""
        transition = KnowledgeLifecycleTransition(
            knowledge_table="drug_usage",
            knowledge_row_id="synthetic-row-id",
            from_status="clinical_review",
            to_status=status_value,
            actor_id="author-1",
            reason_code="standard_transition",
            rationale="Synthetic test rationale.",
            transitioned_at=dt.datetime.now(dt.UTC),
        )
        db.add(transition)
        db.commit()
        assert transition.to_status == status_value
        db.delete(transition)
        db.commit()

    def test_unknown_origin_rejected_by_orm(self, db) -> None:
        ingredient = _make_ingredient(db)
        with pytest.raises(ValueError, match="origin"):
            repo.create_draft(
                db,
                DrugUsage,
                authored_by="author-1",
                drug_ingredient_id=ingredient.id,
                locale="vi",
                audience="patient",
                content="content",
                origin="not_a_governed_value",
            )

    def test_unknown_origin_rejected_by_db(self, db) -> None:
        """Bypasses the ORM `@validates` hook entirely via a raw INSERT to
        prove the DB CHECK constraint is a real, independent backstop —
        same discipline as this file's existing partial-unique-index
        backstop tests."""
        import datetime as _dt

        from sqlalchemy import text as sa_text

        ingredient = _make_ingredient(db)
        with pytest.raises(IntegrityError):
            db.execute(
                sa_text(
                    "INSERT INTO drug_usage (id, drug_ingredient_id, locale, audience, "
                    "content, status, status_changed_by, status_changed_at, authored_by, "
                    "created_at, updated_at, origin) VALUES "
                    "(:id, :ingredient_id, 'vi', 'patient', 'content', 'draft', 'author-1', "
                    ":now, 'author-1', :now, :now, 'not_a_governed_value')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "ingredient_id": ingredient.id,
                    "now": _dt.datetime.now(_dt.UTC),
                },
            )
            db.commit()
        db.rollback()

    def test_legacy_row_backfill_produces_human_authored(self, db) -> None:
        """Every row created through this module's only real write path
        (create_draft) without an explicit `origin` kwarg defaults to
        `human_authored` — the same inferred-legacy-origin marker the
        k2_s0_knowledge_origin migration's server_default backfills every
        pre-Slice-0 row to (ADR-13 Amendment 1 §1 / plan §B2.2). This test
        proves the ORM-level default; the migration's own backfill is
        proven by tests/integration/test_medication_k2_widen_evidence_
        level_migration.py-style Postgres migration tests (§E)."""
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
            # origin intentionally omitted
        )
        assert row.origin == "human_authored"

    def test_new_rows_can_supply_explicit_origin(self, db) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
            origin="source_extracted",
        )
        assert row.origin == "source_extracted"

    def test_ai_synthesized_cannot_be_constructed_as_approved(self, db) -> None:
        """Direct ORM construction (not build_draft, which hardcodes
        status='draft' itself and would collide with an explicit
        status= kwarg at the Python call level before any validation
        logic even runs) — exercises the @validates guard directly."""
        ingredient = _make_ingredient(db)
        with pytest.raises(ValueError, match="ai_synthesized"):
            DrugUsage(
                authored_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
                status="approved",
                status_changed_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
                status_changed_at=dt.datetime.now(dt.UTC),
                drug_ingredient_id=ingredient.id,
                locale="vi",
                audience="patient",
                content="content",
                origin="ai_synthesized",
            )

    def test_invalid_current_lifecycle_status_rejected(self, db) -> None:
        ingredient = _make_ingredient(db)
        with pytest.raises(ValueError, match="status"):
            DrugUsage(
                authored_by="author-1",
                status="not_a_real_status",
                status_changed_by="author-1",
                status_changed_at=dt.datetime.now(dt.UTC),
                drug_ingredient_id=ingredient.id,
                locale="vi",
                audience="patient",
                content="content",
            )

    @pytest.mark.parametrize("bad_value", ["not_a_status", "", "APPROVED", None])
    def test_transition_from_status_constraint_enforced(self, db, bad_value) -> None:
        ingredient = _make_ingredient(db)
        with pytest.raises((ValueError, IntegrityError)):
            transition = KnowledgeLifecycleTransition(
                knowledge_table="drug_usage",
                knowledge_row_id="synthetic-row-id",
                from_status=bad_value,
                to_status="clinical_review",
                actor_id="author-1",
                reason_code="standard_transition",
                rationale="Synthetic test rationale.",
                transitioned_at=dt.datetime.now(dt.UTC),
            )
            db.add(transition)
            db.commit()
        db.rollback()
        _ = ingredient  # only used to keep this test's shape consistent with its siblings

    @pytest.mark.parametrize("bad_value", ["not_a_status", "", "APPROVED", None])
    def test_transition_to_status_constraint_enforced(self, db, bad_value) -> None:
        with pytest.raises((ValueError, IntegrityError)):
            transition = KnowledgeLifecycleTransition(
                knowledge_table="drug_usage",
                knowledge_row_id="synthetic-row-id",
                from_status="clinical_review",
                to_status=bad_value,
                actor_id="author-1",
                reason_code="standard_transition",
                rationale="Synthetic test rationale.",
                transitioned_at=dt.datetime.now(dt.UTC),
            )
            db.add(transition)
            db.commit()
        db.rollback()


class TestAppendOnlyHistoryEnforcement:
    @pytest.fixture(autouse=True)
    def _cleanup(self, db):
        existing_ids = {row.id for row in db.query(DrugUsage.id).all()}
        existing_gen_ids = {g.id for g in db.query(KnowledgeAIGeneration.id).all()}
        yield
        db.rollback()
        _cleanup_domain_rows(db, existing_ids)
        db.query(KnowledgeAIGeneration).filter(
            ~KnowledgeAIGeneration.id.in_(existing_gen_ids)
        ).delete(synchronize_session=False)
        db.commit()

    def test_no_production_service_exposes_update_delete_for_lifecycle_transitions(self) -> None:
        """Grep-guard, mirroring this codebase's existing "no forbidden
        import" convention (e.g. medication_knowledge_import's own scope
        guard): no function in knowledge_repository.py issues an UPDATE or
        DELETE Core statement against KnowledgeLifecycleTransition — every
        write is `db.add(KnowledgeLifecycleTransition(...))` inside
        `_record_transition`, an INSERT, and nothing else."""
        import inspect

        source = inspect.getsource(repo)
        assert "update(KnowledgeLifecycleTransition)" not in source
        assert "delete(KnowledgeLifecycleTransition)" not in source
        assert ".query(KnowledgeLifecycleTransition)" not in source or (
            "delete(" not in source.split(".query(KnowledgeLifecycleTransition)")[1][:200]
        )

    def test_no_production_service_exposes_delete_for_ai_generations(self) -> None:
        """Fix round 1, 2026-07-28 (Codex Round 1 finding #5/#9): this used
        to assert NO update(KnowledgeAIGeneration) existed at all — that
        premise is now intentionally false, since `approve_row` must
        atomically promote the authoritative generation's `review_status`
        (see `_select_and_promote_ai_generation`). What must still hold:
        no DELETE ever, and exactly ONE UPDATE call site — the sanctioned
        promotion, not an incidental or duplicated one. The behavioral
        proof that this one UPDATE touches only `review_status` is
        `test_approval_promotion_only_touches_review_status` on
        `TestAIProvenanceApprovalGuard`."""
        import inspect

        source = inspect.getsource(repo)
        assert "delete(KnowledgeAIGeneration)" not in source
        assert source.count("update(KnowledgeAIGeneration)") == 1, (
            "exactly one UPDATE against KnowledgeAIGeneration is expected — "
            "the review_status promotion inside _select_and_promote_ai_generation"
        )

    def test_retries_create_distinct_generation_rows(self, db) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
            origin="ai_synthesized",
            **_approval_provenance_fields(),
        )
        first_attempt = KnowledgeAIGeneration(
            knowledge_table="drug_usage",
            target_row_id=row.id,
            model_provider="p",
            model_identifier="m",
            prompt_template_id="pt",
            prompt_template_version="1",
            input_source_ids=[],
            input_hash="a" * 64,
            generation_status="failed",
            failure_reason="Synthetic transient failure.",
            created_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
        )
        db.add(first_attempt)
        db.commit()
        retry = KnowledgeAIGeneration(
            knowledge_table="drug_usage",
            target_row_id=row.id,
            model_provider="p",
            model_identifier="m",
            prompt_template_id="pt",
            prompt_template_version="1",
            input_source_ids=[],
            input_hash="b" * 64,
            generation_status="succeeded",
            created_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
        )
        db.add(retry)
        db.commit()

        rows = (
            db.query(KnowledgeAIGeneration)
            .filter_by(knowledge_table="drug_usage", target_row_id=row.id)
            .all()
        )
        assert len(rows) == 2, "retry must be a new row, never an UPDATE of the failed attempt"
        assert first_attempt.id != retry.id
        assert first_attempt.generation_status == "failed"
        assert retry.generation_status == "succeeded"

    def test_supersession_preserves_both_generation_records(self, db) -> None:
        ingredient = _make_ingredient(db)
        row_id = str(uuid.uuid4())
        original = KnowledgeAIGeneration(
            knowledge_table="drug_usage",
            target_row_id=row_id,
            model_provider="p",
            model_identifier="m",
            prompt_template_id="pt",
            prompt_template_version="1",
            input_source_ids=[],
            input_hash="a" * 64,
            generation_status="succeeded",
            created_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
        )
        db.add(original)
        db.commit()
        newer = KnowledgeAIGeneration(
            knowledge_table="drug_usage",
            target_row_id=row_id,
            model_provider="p",
            model_identifier="m",
            prompt_template_id="pt",
            prompt_template_version="2",
            input_source_ids=[],
            input_hash="b" * 64,
            generation_status="succeeded",
            created_by=SystemActor.MEDICATION_AI_SYNTHESIS.value,
        )
        db.add(newer)
        db.commit()
        original.superseded_by_generation_id = newer.id
        db.commit()

        both = (
            db.query(KnowledgeAIGeneration)
            .filter_by(knowledge_table="drug_usage", target_row_id=row_id)
            .all()
        )
        assert {g.id for g in both} == {original.id, newer.id}
        assert original.superseded_by_generation_id == newer.id
        assert newer.superseded_by_generation_id is None
        _ = ingredient

    def test_prior_transition_rows_remain_unchanged_after_later_transitions(self, db) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, row, actor_user_id="author-1")
        submit_transition = (
            db.query(KnowledgeLifecycleTransition)
            .filter_by(knowledge_table="drug_usage", knowledge_row_id=row.id, to_status="clinical_review")
            .one()
        )
        submit_transitioned_at = submit_transition.transitioned_at
        submit_actor = submit_transition.actor_id

        repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role="internal_admin")

        db.refresh(submit_transition)
        assert submit_transition.transitioned_at == submit_transitioned_at
        assert submit_transition.actor_id == submit_actor
        assert submit_transition.from_status == "draft"
        assert submit_transition.to_status == "clinical_review"

        approve_transition = (
            db.query(KnowledgeLifecycleTransition)
            .filter_by(knowledge_table="drug_usage", knowledge_row_id=row.id, to_status="approved")
            .one()
        )
        assert approve_transition.id != submit_transition.id

        _cleanup_domain_rows(db, {r.id for r in db.query(DrugUsage.id).all() if r.id != row.id})

    def test_denied_operations_leave_zero_history_residue(self, db) -> None:
        ingredient = _make_ingredient(db)
        row = repo.create_draft(
            db,
            DrugUsage,
            authored_by="author-1",
            drug_ingredient_id=ingredient.id,
            locale="vi",
            audience="patient",
            content="content",
            **_approval_provenance_fields(),
        )
        repo.submit_for_review(db, row, actor_user_id="author-1")
        before = (
            db.query(KnowledgeLifecycleTransition)
            .filter_by(knowledge_table="drug_usage", knowledge_row_id=row.id)
            .count()
        )
        with pytest.raises(repo.KnowledgeApprovalAuthorizationError):
            repo.approve_row(db, row, actor_user_id="reviewer-1", actor_role="patient")
        with pytest.raises(repo.TransitionError, match="Self-approval"):
            repo.approve_row(db, row, actor_user_id="author-1", actor_role="internal_admin")
        after = (
            db.query(KnowledgeLifecycleTransition)
            .filter_by(knowledge_table="drug_usage", knowledge_row_id=row.id)
            .count()
        )
        assert after == before, "neither denied approval attempt may leave a history row"
