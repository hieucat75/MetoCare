"""Unit tests for K1-S3: draft-only knowledge repository/service layer.

Business-logic tests (not SQL-dialect-specific), so these run against the
shared SQLite test DB via the existing `db` fixture (tests/conftest.py) —
no PostgreSQL integration marker needed, unlike the migration test files.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.drug_knowledge_content import (
    DrugContraindication,
    DrugMonitoring,
    DrugPatientEducation,
    DrugSideEffect,
    DrugUsage,
)
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.models.drug_knowledge_governance import ClinicalSpecialty
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
