"""K2 Slice 1 — read-only medication knowledge retrieval
(MEDICATION_K2_KNOWLEDGE_API_IMPLEMENTATION_PLAN.md).

  GET /api/v1/patient/medications/{medication_id}/knowledge
      — PATIENT, own medication only
  GET /api/v1/doctor/ingredients/{drug_ingredient_id}/knowledge
      — DOCTOR, verification_status=VERIFIED

Both routes are read-only: they call K1.6's read service through
`medication_knowledge_response.py` and never create/update/approve/reject/
delete any medication-knowledge row. Gated behind
`FeatureFlag.MEDICATION_KNOWLEDGE_RETRIEVAL` (ADR-15 §K.1) at the router
level — 503 when disabled, before any handler code runs. Rate-limited via
the existing `enforce_rate_limit` mechanism (K2 plan §4), one action key
per endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, enforce_rate_limit, get_session, require_roles
from app.api.deps_medication_knowledge import (
    require_medication_knowledge_read_enabled,
    require_own_medication,
    require_verified_doctor,
)
from app.models.clinical import Medication
from app.models.user import UserRole
from app.schemas.medication_knowledge import (
    DoctorIngredientKnowledgeOut,
    PatientMedicationKnowledgeOut,
)
from app.services import audit
from app.services.medication_knowledge_response import (
    build_doctor_response,
    build_patient_response,
    resolve_ingredient_ids,
)

router = APIRouter(
    tags=["medication_knowledge"],
    dependencies=[Depends(require_medication_knowledge_read_enabled)],
)


@router.get(
    "/patient/medications/{medication_id}/knowledge",
    response_model=PatientMedicationKnowledgeOut,
    response_model_exclude_unset=True,
    summary="Approved medication knowledge for the caller's own medication",
)
def get_patient_medication_knowledge(
    request: Request,
    response: Response,
    user: CurrentUser = Depends(require_roles(UserRole.PATIENT)),
    medication: Medication = Depends(require_own_medication),
    db: Session = Depends(get_session),
) -> PatientMedicationKnowledgeOut:
    """K2 plan §2.1 endpoint #1. Role check (`require_roles`) runs before
    the object-level ownership check (`require_own_medication`) — declared
    in that order deliberately, matching §4's "role check, THEN object-level
    check" sequencing: a non-PATIENT caller must get 403, never a 404 from
    an ownership lookup it should never have reached. `medication` is
    already ownership-checked (§4, §12 — 404 for both "doesn't exist" and
    "belongs to someone else"). A null/unmatched `drug_product_id` resolves
    to zero ingredients, which is a normal 200 with every category
    empty/null (§1.3 fact 2, §8) — never a 404/500.
    """
    enforce_rate_limit(request, "medication_knowledge_patient_read")

    ingredient_ids = resolve_ingredient_ids(db, medication.drug_product_id)
    result = build_patient_response(db, ingredient_ids)

    # §11: patient-scoped response, never shared-cacheable.
    response.headers["Cache-Control"] = "private, no-store"

    # §11: PHI-minimized audit — ids/metadata only, never knowledge content.
    audit.record(
        db,
        actor_type=user.role,
        actor_id=user.id,
        action="read_medication_knowledge",
        resource_type="medication",
        resource_id=medication.id,
        outcome="success",
        severity="info",
        details={"drug_ingredient_ids": ingredient_ids},
    )
    db.commit()

    return result


@router.get(
    "/doctor/ingredients/{drug_ingredient_id}/knowledge",
    response_model=DoctorIngredientKnowledgeOut,
    response_model_exclude_unset=True,
    summary="Approved medication knowledge for a drug ingredient (clinical reference)",
)
def get_doctor_ingredient_knowledge(
    request: Request,
    drug_ingredient_id: str,
    _user: CurrentUser = Depends(require_roles(UserRole.DOCTOR)),
    _verified: None = Depends(require_verified_doctor),
    db: Session = Depends(get_session),
) -> DoctorIngredientKnowledgeOut:
    """K2 plan §2.1 endpoint #2. No object-level check — `drug_ingredient_id`
    is not patient-scoped (§4, §12). No audit log (§11, PTH decision
    2026-07-22 — no PHI, no patient object).
    """
    enforce_rate_limit(request, "medication_knowledge_doctor_read")
    return build_doctor_response(db, drug_ingredient_id)
