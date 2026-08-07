"""Meto Clinical Copilot API — doctor-facing AI decision-support (never
decision-making). Mounted under the same ``/doctor`` prefix + RBAC as
``doctor_portal`` (DOCTOR / MEDICAL_REVIEWER).

Endpoints:
- POST /doctor/patients/{patient_id}/ai-summary
- POST /doctor/patients/{patient_id}/ai-analysis
- POST /doctor/patients/{patient_id}/ai-questions
- POST /doctor/patients/{patient_id}/ai-advice

Per-request gate order (cheapest / safest checks first):
1. Feature flag (``CLINICAL_COPILOT``) — 503 before any DB/provider work.
2. Scope: consultation-scoped (``assert_doctor_can_view``) when a
   ``consultation_id`` is supplied, else the same patient-page gate the
   clinical timeline uses (``doctor_portal._require_timeline_access``),
   followed by ``assert_doctor_clinic_scope_for_patient`` — additive
   clinic-membership check that closes the cross-clinic gap in
   ``docs/clinic-saas/THREAT_MODEL.md`` §10 (a no-op until a patient is
   actually linked to a clinic via ``ClinicPatientRelationship``).
3. Consent: ``ConsentGuard`` for ``ai_use`` / ``clinical_copilot`` — 403 on
   ``ConsentDenied``.
4. Service call — ``CopilotUnavailable`` (every provider down) → 503 friendly
   message, never the raw exception.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, get_session, require_roles
from app.api.v1.routes.doctor_portal import _require_timeline_access
from app.core.feature_flags import FeatureFlag, is_enabled
from app.core.rbac import assert_doctor_clinic_scope_for_patient
from app.models.user import UserRole
from app.schemas.clinical_copilot import (
    ClinicalAdviceOut,
    ClinicalAnalysisOut,
    ClinicalCopilotRequest,
    ClinicalQuestionsOut,
    ClinicalSummaryOut,
)
from app.services import clinical_copilot as clinical_copilot_svc
from app.services.clinical_copilot import UNGATED, CopilotDataGate
from app.services.consent_guard import ConsentDenied, ConsentGuard
from app.services.consultation_access import assert_doctor_can_view
from app.services.doctor import get_doctor_by_user_id

router = APIRouter(prefix="/doctor", tags=["clinical_copilot"])

_portal_roles = require_roles(UserRole.DOCTOR, UserRole.MEDICAL_REVIEWER)

_FEATURE_UNAVAILABLE_DETAIL = "Meto phân tích hồ sơ hiện chưa khả dụng."
_CONSENT_DENIED_DETAIL = "Bệnh nhân chưa cấp quyền sử dụng tính năng AI cho hồ sơ này."
_NOT_A_DOCTOR_DETAIL = "Chỉ bác sĩ mới có thể sử dụng tính năng này."
_CONSULTATION_MISMATCH_DETAIL = "consultation_id không thuộc về patient_id trong đường dẫn."
_MALFORMED_OUTPUT_DETAIL = "Meto không thể xử lý phản hồi AI cho yêu cầu này. Vui lòng thử lại."


def _authorize(
    db: Session, *, patient_id: str, consultation_id: str | None, user: CurrentUser
) -> tuple[str | None, CopilotDataGate]:
    """Run the full gate chain.

    Returns the consultation's chief_complaint (or None) so callers can thread it
    into the LLM prompt without re-querying, PLUS the consent gate describing
    which data categories this request may read. The copilot is the richest PHI
    path in the feature, so it must honour the same consultation-specific
    consent as the patient summary — an unfiltered copilot would hand a doctor,
    and a third-party LLM, exactly the categories the patient withheld.
    """
    if not is_enabled(FeatureFlag.CLINICAL_COPILOT):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_FEATURE_UNAVAILABLE_DETAIL,
        )

    chief_complaint: str | None = None
    # Ungated by default: the patient-page / clinic-scoped path below has its own
    # authorization and is not governed by consultation consent.
    gate = UNGATED
    if consultation_id:
        doctor = get_doctor_by_user_id(db, user.id)
        if doctor is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=_NOT_A_DOCTOR_DETAIL
            )
        # Gates on BOTH the care relationship and the patient's
        # consultation-specific sharing consent; raises 403 without either.
        access = assert_doctor_can_view(db, doctor=doctor, consultation_id=consultation_id)
        consultation = access.consultation
        gate = CopilotDataGate(allowed=access.allowed_categories)
        if consultation.patient_id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_CONSULTATION_MISMATCH_DETAIL,
            )
        chief_complaint = consultation.chief_complaint
    else:
        _require_timeline_access(db, patient_id=patient_id, user=user)
        assert_doctor_clinic_scope_for_patient(
            db, doctor_user_id=user.id, patient_id=patient_id
        )

    try:
        ConsentGuard(db).require(
            patient_id=patient_id,
            consent_type="ai_use",
            data_scope="clinical_copilot",
            actor_id=user.id,
            actor_type="doctor",
        )
    except ConsentDenied as exc:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=_CONSENT_DENIED_DETAIL
        ) from exc
    db.commit()
    return chief_complaint, gate


@router.post("/patients/{patient_id}/ai-summary", response_model=ClinicalSummaryOut)
def post_ai_summary(
    patient_id: str,
    payload: ClinicalCopilotRequest = ClinicalCopilotRequest(),
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> ClinicalSummaryOut:
    chief_complaint, gate = _authorize(
        db, patient_id=patient_id, consultation_id=payload.consultation_id, user=user
    )
    return clinical_copilot_svc.get_summary(
        db,
        doctor_user_id=user.id,
        patient_id=patient_id,
        consultation_id=payload.consultation_id,
        chief_complaint=chief_complaint,
        gate=gate,
    )


@router.post("/patients/{patient_id}/ai-analysis", response_model=ClinicalAnalysisOut)
async def post_ai_analysis(
    patient_id: str,
    payload: ClinicalCopilotRequest = ClinicalCopilotRequest(),
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> ClinicalAnalysisOut:
    chief_complaint, gate = await run_in_threadpool(
        _authorize, db, patient_id=patient_id, consultation_id=payload.consultation_id, user=user
    )
    try:
        return await clinical_copilot_svc.get_analysis(
            db,
            doctor_user_id=user.id,
            patient_id=patient_id,
            consultation_id=payload.consultation_id,
            chief_complaint=chief_complaint,
            gate=gate,
        )
    except clinical_copilot_svc.CopilotUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_FEATURE_UNAVAILABLE_DETAIL,
        ) from exc
    except clinical_copilot_svc.CopilotMalformedOutput as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_MALFORMED_OUTPUT_DETAIL,
        ) from exc


@router.post("/patients/{patient_id}/ai-questions", response_model=ClinicalQuestionsOut)
async def post_ai_questions(
    patient_id: str,
    payload: ClinicalCopilotRequest = ClinicalCopilotRequest(),
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> ClinicalQuestionsOut:
    chief_complaint, gate = await run_in_threadpool(
        _authorize, db, patient_id=patient_id, consultation_id=payload.consultation_id, user=user
    )
    try:
        return await clinical_copilot_svc.get_questions(
            db,
            doctor_user_id=user.id,
            patient_id=patient_id,
            consultation_id=payload.consultation_id,
            chief_complaint=chief_complaint,
            gate=gate,
        )
    except clinical_copilot_svc.CopilotUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_FEATURE_UNAVAILABLE_DETAIL,
        ) from exc
    except clinical_copilot_svc.CopilotMalformedOutput as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_MALFORMED_OUTPUT_DETAIL,
        ) from exc


@router.post("/patients/{patient_id}/ai-advice", response_model=ClinicalAdviceOut)
async def post_ai_advice(
    patient_id: str,
    payload: ClinicalCopilotRequest = ClinicalCopilotRequest(),
    user: CurrentUser = Depends(_portal_roles),
    db: Session = Depends(get_session),
) -> ClinicalAdviceOut:
    chief_complaint, gate = await run_in_threadpool(
        _authorize, db, patient_id=patient_id, consultation_id=payload.consultation_id, user=user
    )
    try:
        return await clinical_copilot_svc.get_advice(
            db,
            doctor_user_id=user.id,
            patient_id=patient_id,
            consultation_id=payload.consultation_id,
            chief_complaint=chief_complaint,
            gate=gate,
        )
    except clinical_copilot_svc.CopilotUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_FEATURE_UNAVAILABLE_DETAIL,
        ) from exc
    except clinical_copilot_svc.CopilotMalformedOutput as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_MALFORMED_OUTPUT_DETAIL,
        ) from exc
