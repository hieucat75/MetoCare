"""Consultation routes (T10) — Doctor Marketplace consultations.

RBAC and ownership are enforced in the service layer; routes resolve the caller's
patient/doctor identity and translate to service calls. The doctor patient-summary
endpoint is the only path to patient data and is scoped + audited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    current_user,
    get_session,
    require_roles,
)
from app.core.config import MARKETPLACE_DISCLAIMER
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.consultation import (
    ConsultationCancel,
    ConsultationCreate,
    ConsultationOut,
    NoteCreate,
    NoteOut,
    PatientPaymentOut,
    ReviewCreate,
    ReviewOut,
)
from app.schemas.patient import PatientSummaryOut
from app.services import (
    consultation as consult_svc,
)
from app.services import (
    consultation_access,
    consultation_note,
    consultation_payment,
    consultation_review,
)
from app.services.doctor import get_doctor_by_user_id
from app.services.patient_summary import build_summary

router = APIRouter(prefix="/consultations", tags=["consultations"])

_patient_only = require_roles(UserRole.PATIENT)
_doctor_only = require_roles(UserRole.DOCTOR)

_ADMIN_ROLES = frozenset({UserRole.INTERNAL_ADMIN.value, UserRole.SUPER_ADMIN.value})


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------


def _resolve_patient_profile(db: Session, user_id: str) -> PatientProfile:
    profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user_id)
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient profile not found."
        )
    return profile


def _with_disclaimer(consultation) -> ConsultationOut:
    out = ConsultationOut.model_validate(consultation)
    return out.model_copy(update={"disclaimer": MARKETPLACE_DISCLAIMER})


# ---------------------------------------------------------------------------
# Create + list + detail
# ---------------------------------------------------------------------------


@router.post("", response_model=ConsultationOut, status_code=status.HTTP_201_CREATED)
def create_consultation(
    payload: ConsultationCreate,
    user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_session),
) -> ConsultationOut:
    profile = _resolve_patient_profile(db, user.id)
    consultation = consult_svc.create_consultation(
        db,
        patient_id=profile.id,
        doctor_id=payload.doctor_id,
        consultation_type=payload.consultation_type,
        data_consent_accepted=payload.data_consent_accepted,
        chief_complaint=payload.chief_complaint,
        patient_note=payload.patient_note,
        booking_appointment_id=payload.booking_appointment_id,
    )
    return _with_disclaimer(consultation)


@router.get("", response_model=list[ConsultationOut])
def list_consultations(
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[ConsultationOut]:
    if user.role == UserRole.PATIENT.value:
        profile = _resolve_patient_profile(db, user.id)
        rows = consult_svc.list_patient_consultations(db, profile.id)
    elif user.role == UserRole.DOCTOR.value:
        doctor = get_doctor_by_user_id(db, user.id)
        if doctor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Doctor profile not found."
            )
        rows = consult_svc.list_doctor_consultations(db, doctor.id)
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients and doctors can list consultations.",
        )
    return [_with_disclaimer(r) for r in rows]


@router.get("/{consultation_id}", response_model=ConsultationOut)
def get_consultation(
    consultation_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> ConsultationOut:
    consultation = consult_svc.get_consultation_or_404(db, consultation_id)
    if user.role in _ADMIN_ROLES:
        return _with_disclaimer(consultation)
    if user.role == UserRole.PATIENT.value:
        profile = _resolve_patient_profile(db, user.id)
        if consultation.patient_id == profile.id:
            return _with_disclaimer(consultation)
    if user.role == UserRole.DOCTOR.value:
        doctor = get_doctor_by_user_id(db, user.id)
        if doctor is not None and consultation.doctor_id == doctor.id:
            return _with_disclaimer(consultation)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this consultation."
    )


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


@router.post("/{consultation_id}/pay", response_model=PatientPaymentOut)
def pay_consultation(
    consultation_id: str,
    user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_session),
) -> PatientPaymentOut:
    profile = _resolve_patient_profile(db, user.id)
    consultation = consult_svc.get_consultation_or_404(db, consultation_id)
    payment = consultation_payment.pay_mock(
        db, consultation, patient_profile_id=profile.id
    )
    # Patients never see payout/platform-fee internals — only what they pay.
    return PatientPaymentOut.model_validate(payment)


# ---------------------------------------------------------------------------
# Doctor transitions
# ---------------------------------------------------------------------------


@router.post("/{consultation_id}/confirm", response_model=ConsultationOut)
def confirm_consultation(
    consultation_id: str,
    user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_session),
) -> ConsultationOut:
    consultation = consult_svc.confirm(db, consultation_id, doctor_user_id=user.id)
    return _with_disclaimer(consultation)


@router.post("/{consultation_id}/start", response_model=ConsultationOut)
def start_consultation(
    consultation_id: str,
    user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_session),
) -> ConsultationOut:
    consultation = consult_svc.start(db, consultation_id, doctor_user_id=user.id)
    return _with_disclaimer(consultation)


@router.post("/{consultation_id}/complete", response_model=ConsultationOut)
def complete_consultation(
    consultation_id: str,
    user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_session),
) -> ConsultationOut:
    consultation = consult_svc.complete(db, consultation_id, doctor_user_id=user.id)
    return _with_disclaimer(consultation)


@router.post("/{consultation_id}/cancel", response_model=ConsultationOut)
def cancel_consultation(
    consultation_id: str,
    payload: ConsultationCancel | None = None,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> ConsultationOut:
    if user.role not in (UserRole.PATIENT.value, UserRole.DOCTOR.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients and doctors can cancel consultations.",
        )
    patient_profile_id = None
    if user.role == UserRole.PATIENT.value:
        patient_profile_id = _resolve_patient_profile(db, user.id).id
    consultation = consult_svc.cancel(
        db,
        consultation_id,
        actor_user_id=user.id,
        actor_role=user.role,
        patient_profile_id=patient_profile_id,
        reason=payload.reason if payload else None,
    )
    return _with_disclaimer(consultation)


# ---------------------------------------------------------------------------
# Scoped + audited patient summary (doctor only)
# ---------------------------------------------------------------------------


@router.get("/{consultation_id}/patient-summary", response_model=PatientSummaryOut)
def get_patient_summary(
    consultation_id: str,
    user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_session),
) -> PatientSummaryOut:
    doctor = get_doctor_by_user_id(db, user.id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Doctor profile not found."
        )
    consultation = consultation_access.assert_doctor_can_view(
        db, doctor=doctor, consultation_id=consultation_id
    )
    return build_summary(db, patient_id=consultation.patient_id, doctor_id=doctor.id)


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@router.post(
    "/{consultation_id}/notes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
)
def add_note(
    consultation_id: str,
    payload: NoteCreate,
    user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_session),
) -> NoteOut:
    note = consultation_note.add_note(
        db,
        consultation_id=consultation_id,
        doctor_user_id=user.id,
        content=payload.content,
        note_type=payload.note_type,
    )
    return NoteOut.model_validate(note)


@router.get("/{consultation_id}/notes", response_model=list[NoteOut])
def list_notes(
    consultation_id: str,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> list[NoteOut]:
    patient_profile_id = None
    if user.role == UserRole.PATIENT.value:
        patient_profile_id = _resolve_patient_profile(db, user.id).id
    notes = consultation_note.list_notes(
        db,
        consultation_id=consultation_id,
        requester_role=user.role,
        requester_user_id=user.id,
        patient_profile_id=patient_profile_id,
    )
    return [NoteOut.model_validate(n) for n in notes]


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


@router.post(
    "/{consultation_id}/review", response_model=ReviewOut, status_code=status.HTTP_201_CREATED
)
def create_review(
    consultation_id: str,
    payload: ReviewCreate,
    user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_session),
) -> ReviewOut:
    profile = _resolve_patient_profile(db, user.id)
    review = consultation_review.create_review(
        db,
        consultation_id=consultation_id,
        patient_profile_id=profile.id,
        rating=payload.rating,
        feedback=payload.feedback,
    )
    return ReviewOut.model_validate(review)
