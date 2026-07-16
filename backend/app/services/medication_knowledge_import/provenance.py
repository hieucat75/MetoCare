"""Database-backed provenance checks — read-only, no writes anywhere here.

Resolves a knowledge file's human-readable medication identity against the
real ADR-01 relational core (fail closed if the ingredient doesn't exist —
this is exactly where the Calcium gap in
docs/medication-management/MEDICATION_PHASE_A_PR_A1_IMPLEMENTATION_PLAN.md
Section 1 surfaces at Phase-B time), and checks a declared specialty code
against real `clinical_specialties` rows.

Everything that can be validated from the file alone (types, required
fields, controlled vocabularies not tied to a DB table) lives in schema.py
and validators.py instead — this module exists only for checks that
genuinely need a database session.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.drug_knowledge_core import DrugIngredient
from app.models.drug_knowledge_governance import ClinicalSpecialty


class IdentityResolutionError(ValueError):
    """Raised when a knowledge file's medication_identity does not resolve
    to a real drug_ingredients row. Fail closed — never guesses or creates
    a row (see K1-S2's own migration philosophy: raise, don't proceed)."""


def resolve_medication_identity(db: Session, name_inn: str) -> DrugIngredient:
    """Resolve `metadata.medication_identity.name_inn` to a real
    DrugIngredient row. Exact match only (drug_ingredients.name_inn is a
    verbatim salt-form string per K1-S2's convention — no fuzzy matching,
    since a near-miss here would silently attach content to the wrong
    ingredient)."""
    ingredient = db.query(DrugIngredient).filter_by(name_inn=name_inn).one_or_none()
    if ingredient is None:
        raise IdentityResolutionError(
            f"no drug_ingredients row for name_inn={name_inn!r} — cannot import "
            "knowledge content for a medication that does not exist in the "
            "relational core. See MEDICATION_PHASE_A_BLOCKING_FINDINGS.md for "
            "the Calcium case: this is expected to reject until a real "
            "ingredient row is added via its own PR, never by guessing one here."
        )
    return ingredient


def check_specialty_exists(db: Session, code: str) -> bool:
    """True iff `code` has a real, active clinical_specialties row.

    Distinct from validators.ALLOWED_SPECIALTY_CODES (a fixed Python
    allowlist checked without a DB session): this is the DB-existence half
    of specialty validation, and will correctly return False for every
    code until the table is seeded (Finding 2,
    MEDICATION_PHASE_A_BLOCKING_FINDINGS.md) — that is expected, not a bug,
    until the seed lands.
    """
    return (
        db.query(ClinicalSpecialty).filter_by(code=code, is_active=True).one_or_none()
        is not None
    )
