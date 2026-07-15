"""Draft-only repository/service layer for the 5 ADR-13 knowledge tables (K1-S3).

Scope lock (PTH, K1-S3 GO): create/edit draft content only. There is no
function anywhere in this module that can set a row's status to 'approved'
— `validate_transition` implements ADR-13's full transition rule set
(including the clinical_review -> approved rule) as a pure, directly
testable function, but nothing calls it with a target of 'approved' from a
real write path. That path does not exist yet; adding it is a separate,
future PR requiring an actual Clinical Advisor role, which this codebase
does not have wired up (per ADR-13's own "Production Schema Must Not Encode
Test Data" section: "the service-layer role capable of approving content
does not exist in test/CI environments at all").

`drug_interactions` is out of scope — not one of the 5 tables this module
touches (deferred to its own ADR-02-compliant PR, per K1-M01/K1-S2).

No API route, no frontend, no AI wiring touches this module.
"""

from __future__ import annotations

import datetime as dt
from typing import TypeVar

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.drug_knowledge_content import (
    DrugContraindication,
    DrugMonitoring,
    DrugPatientEducation,
    DrugSideEffect,
    DrugUsage,
)
from app.models.drug_knowledge_core import DrugClass, DrugIngredient
from app.models.drug_knowledge_governance import ClinicalSpecialty, KnowledgeReviewSpecialty

KnowledgeModel = TypeVar(
    "KnowledgeModel",
    DrugUsage,
    DrugPatientEducation,
    DrugSideEffect,
    DrugMonitoring,
    DrugContraindication,
)

# Maps each of the 5 in-scope model classes to its table name — must match
# KNOWLEDGE_TABLES in drug_knowledge_governance.py (that tuple is the DB
# CHECK constraint's source of truth; this dict is this module's own,
# kept in sync by hand since the two files can't share a live import
# without a circular dependency).
KNOWLEDGE_TABLE_NAME: dict[type, str] = {
    DrugUsage: "drug_usage",
    DrugPatientEducation: "drug_patient_education",
    DrugSideEffect: "drug_side_effects",
    DrugMonitoring: "drug_monitoring",
    DrugContraindication: "drug_contraindications",
}

# ADR-13: "No transition ever skips clinical_review — a draft row can never
# become approved directly, even by an admin." Only these pairs are legal.
_ALLOWED_TRANSITIONS = {
    ("draft", "clinical_review"),
    ("clinical_review", "approved"),
    ("approved", "deprecated"),
    ("deprecated", "retired"),
}


class TransitionError(ValueError):
    """Raised when a lifecycle status transition violates ADR-13."""


def validate_transition(
    current_status: str,
    new_status: str,
    *,
    authored_by: str,
    actor_user_id: str,
    specialty_complete: bool = False,
) -> None:
    """Pure validation of one ADR-13 lifecycle transition. Raises
    TransitionError if illegal; returns None if legal. Does not touch the
    database or mutate any row — callers are responsible for applying the
    transition only after this passes.
    """
    if (current_status, new_status) not in _ALLOWED_TRANSITIONS:
        raise TransitionError(
            f"Illegal transition {current_status!r} -> {new_status!r}. "
            f"Allowed transitions: {sorted(_ALLOWED_TRANSITIONS)}."
        )
    if new_status == "approved":
        # ADR-13: "status_changed_by (the approver) may never equal
        # authored_by (who wrote/last edited the row)."
        if actor_user_id == authored_by:
            raise TransitionError(
                "Self-approval is blocked: the approver cannot be the same "
                "identity as the row's authored_by. (ADR-13 provides a "
                "logged, PTH-approved override for this — not implemented "
                "in K1-S3.)"
            )
        if not specialty_complete:
            raise TransitionError(
                "Cannot approve: not every specialty required by this "
                "ingredient's drug_class has a recorded review "
                "(knowledge_review_specialties row)."
            )


def create_draft(
    db: Session,
    model_cls: type[KnowledgeModel],
    *,
    authored_by: str,
    **fields: object,
) -> KnowledgeModel:
    """Insert a new row with status='draft'. Always an INSERT — this is the
    only way to create OR "edit" content in this module: editing existing
    content means calling this again with the same business-key fields and
    new content, producing a second row, never an UPDATE of the first
    (ADR-13 append-only; verified by test_create_new_version_does_not_overwrite).
    """
    now = dt.datetime.now(dt.UTC)
    row = model_cls(
        authored_by=authored_by,
        status="draft",
        status_changed_by=authored_by,
        status_changed_at=now,
        **fields,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row


def submit_for_review(
    db: Session,
    row: KnowledgeModel,
    *,
    actor_user_id: str,
) -> KnowledgeModel:
    """draft -> clinical_review. ADR-13: any authenticated content author
    may do this — no specialty or self-approval check applies here (those
    only gate clinical_review -> approved, which this module never performs).

    Uses an atomic UPDATE ... WHERE status = 'draft' (matching this
    codebase's existing optimistic-concurrency convention in
    app/services/medication.py) rather than validate-then-write against the
    in-memory `row.status` — Codex review correctly flagged that two
    concurrent callers could otherwise both pass validation against a
    stale in-memory read and both commit, silently double-transitioning
    a row.
    """
    validate_transition(
        row.status, "clinical_review", authored_by=row.authored_by, actor_user_id=actor_user_id
    )
    model_cls = type(row)
    now = dt.datetime.now(dt.UTC)
    result = db.execute(
        update(model_cls)
        .where(model_cls.id == row.id, model_cls.status == "draft")
        .values(status="clinical_review", status_changed_by=actor_user_id, status_changed_at=now)
    )
    if result.rowcount != 1:
        db.rollback()
        raise TransitionError(
            f"Row {row.id!r} was not in 'draft' status at commit time — "
            "another transition won the race. Re-fetch and re-check before retrying."
        )
    db.commit()
    db.refresh(row)
    return row


def record_specialty_review(
    db: Session,
    *,
    knowledge_table: str,
    knowledge_row_id: str,
    specialty_id: str,
    reviewed_by: str,
) -> KnowledgeReviewSpecialty:
    """Record that one specialty has reviewed one knowledge row. Does not
    itself transition anything to 'approved' — see module docstring."""
    review = KnowledgeReviewSpecialty(
        knowledge_table=knowledge_table,
        knowledge_row_id=knowledge_row_id,
        specialty_id=specialty_id,
        reviewed_by=reviewed_by,
        reviewed_at=dt.datetime.now(dt.UTC),
    )
    db.add(review)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(review)
    return review


def check_specialty_completeness(db: Session, row: KnowledgeModel) -> bool:
    """True iff every specialty code in the row's ingredient's drug_class
    .required_specialties has at least one knowledge_review_specialties row
    for this exact row. Pure read — does not mutate anything.

    Fails closed (returns False), never raises, if the ingredient, its
    class, or a referenced specialty is missing — Codex review correctly
    flagged that `db.get()` returning None would otherwise crash with an
    AttributeError on the next attribute access. Production FKs prevent
    the ingredient/class case in practice, but `knowledge_review_specialties
    .specialty_id` is not FK-enforced against a live row being deleted
    later, so this stays defensive rather than trusting the constraint.
    """
    model_cls = type(row)
    table_name = KNOWLEDGE_TABLE_NAME[model_cls]

    ingredient = db.get(DrugIngredient, row.drug_ingredient_id)
    if ingredient is None:
        return False
    drug_class = db.get(DrugClass, ingredient.drug_class_id)
    if drug_class is None:
        return False
    required_codes = set(drug_class.required_specialties or [])
    if not required_codes:
        return True

    reviewed = (
        db.query(KnowledgeReviewSpecialty)
        .filter_by(knowledge_table=table_name, knowledge_row_id=row.id)
        .all()
    )
    reviewed_codes = set()
    for r in reviewed:
        specialty = db.get(ClinicalSpecialty, r.specialty_id)
        if specialty is None:
            continue
        reviewed_codes.add(specialty.code)

    return required_codes.issubset(reviewed_codes)


def list_published(
    db: Session,
    model_cls: type[KnowledgeModel],
    **business_key_filter: object,
) -> list[KnowledgeModel]:
    """Query intended for future patient-facing consumption (not wired to any
    API in K1-S3) — filters status='approved' unconditionally, matching
    ADR-13's "GET /medications/{id}/knowledge filters status='approved'
    unconditionally — not a parameter clients can override" rule. In K1-S3
    this always returns an empty list (nothing can reach 'approved' yet) —
    the point of testing it is to prove the filter itself is correct, not
    that it happens to be empty because no approved rows exist.
    """
    return (
        db.query(model_cls)
        .filter_by(status="approved", **business_key_filter)
        .all()
    )
