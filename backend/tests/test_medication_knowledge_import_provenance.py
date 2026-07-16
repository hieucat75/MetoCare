"""Unit tests for Phase A / PR-A1a: provenance.py.

Runs against the shared SQLite test DB via the existing `db` fixture
(tests/conftest.py), matching K1-S3's own convention — these are
business-logic tests, not SQL-dialect-specific ones. Uses only synthetic
ingredients/classes/specialties, never real catalog data (Phase A does not
touch real clinical content).
"""

from __future__ import annotations

import uuid

import pytest
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.models.drug_knowledge_governance import ClinicalSpecialty
from app.services.medication_knowledge_import.provenance import (
    IdentityResolutionError,
    check_specialty_exists,
    resolve_medication_identity,
)


def _make_ingredient(db) -> DrugIngredient:
    suffix = uuid.uuid4().hex[:8]
    drug_class = DrugClass(name=f"test-class-{suffix}", required_specialties=[])
    db.add(drug_class)
    db.flush()
    ingredient = DrugIngredient(name_inn=f"test-ingredient-{suffix}", drug_class_id=drug_class.id)
    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)
    return ingredient


def test_resolves_existing_ingredient(db) -> None:
    ingredient = _make_ingredient(db)
    resolved = resolve_medication_identity(db, ingredient.name_inn)
    assert resolved.id == ingredient.id


def test_fails_closed_for_unknown_identity(db) -> None:
    """The Calcium case: no row exists, so this must raise — never guess
    or silently create one. See MEDICATION_PHASE_A_BLOCKING_FINDINGS.md."""
    with pytest.raises(IdentityResolutionError, match="no drug_ingredients row"):
        resolve_medication_identity(db, "calcium")


def test_specialty_check_false_when_unseeded(db) -> None:
    """Expected today: clinical_specialties has zero rows in real
    deployments (Finding 2) — this must return False, not raise or
    silently pass."""
    assert check_specialty_exists(db, "endocrinology") is False


def test_specialty_check_true_once_seeded(db) -> None:
    specialty = ClinicalSpecialty(
        code="endocrinology",
        display_name_vi="Nội tiết",
        display_name_en="Endocrinology",
        is_active=True,
    )
    db.add(specialty)
    db.commit()
    assert check_specialty_exists(db, "endocrinology") is True


def test_specialty_check_false_when_inactive(db) -> None:
    specialty = ClinicalSpecialty(
        code="retired_specialty",
        display_name_vi="x",
        display_name_en="x",
        is_active=False,
    )
    db.add(specialty)
    db.commit()
    assert check_specialty_exists(db, "retired_specialty") is False


def test_provenance_checks_write_nothing(db) -> None:
    """A1a is read-only — confirm neither check inserts any row anywhere."""
    ingredient = _make_ingredient(db)
    before_ingredients = db.query(DrugIngredient).count()
    before_specialties = db.query(ClinicalSpecialty).count()

    resolve_medication_identity(db, ingredient.name_inn)
    check_specialty_exists(db, "endocrinology")

    assert db.query(DrugIngredient).count() == before_ingredients
    assert db.query(ClinicalSpecialty).count() == before_specialties
