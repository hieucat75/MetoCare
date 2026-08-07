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
from app.core.clock import utcnow
from app.core.config import MARKETPLACE_DISCLAIMER
from app.domain import consultation_consent_policy as consent_policy
from app.models.consultation import Consultation, ConsultationStatus
from app.models.patient import PatientProfile
from app.models.user import UserRole
from app.schemas.common import Message
from app.schemas.consultation import (
    ConsentCategoryOut,
    ConsultationCancel,
    ConsultationCreate,
    ConsultationOut,
    DataSharingConsentOut,
    DataSharingConsentPolicyOut,
    DataSharingConsentRestore,
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
    consultation_consent,
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

# Statuses where a doctor is still expected to be working the consultation, and
# so where re-granting consent should reopen their access.
_LIVE_STATUSES = frozenset({ConsultationStatus.PAID, ConsultationStatus.IN_PROGRESS})


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


def _for_doctor(db: Session, consultation) -> ConsultationOut:
    """Doctor-facing view, with reason-for-visit text withdrawn once revoked.

    ``chief_complaint`` and ``patient_note`` are patient-authored health text.
    While sharing is active the patient wrote them into this consultation for
    this doctor to read, so they are shown. Once the patient REVOKES sharing,
    they are protected data like any other and must stop being readable —
    otherwise revocation would close the summary and the copilot while leaving
    the doctor polling this endpoint for the patient's own description of their
    condition.

    Consultations with no consent row at all (booked before this feature) keep
    their previous behaviour here; they are already denied every PHI surface.
    """
    out = _with_disclaimer(consultation)
    record = consultation_consent.get_for_consultation(db, consultation.id)
    if record is not None and not record.is_active_at(
        utcnow(), current_consent_version=consent_policy.CONSENT_VERSION
    ):
        return out.model_copy(update={"chief_complaint": None, "patient_note": None})
    return out


# ---------------------------------------------------------------------------
# Data-sharing consent policy (copy the booking modal renders)
# ---------------------------------------------------------------------------
#
# Declared BEFORE "/{consultation_id}" so the literal path is not captured by
# the path parameter.
#


@router.get("/data-sharing-policy", response_model=DataSharingConsentPolicyOut)
def get_data_sharing_policy(
    user: CurrentUser = Depends(_patient_only),
) -> DataSharingConsentPolicyOut:
    """Return the server-authored consent copy + grantable categories.

    Clients render this verbatim rather than shipping their own translation, so
    the words shown to the patient are exactly the words versioned against the
    grant we store.
    """
    return DataSharingConsentPolicyOut(
        consent_version=consent_policy.CONSENT_VERSION,
        policy_version=consent_policy.POLICY_VERSION,
        purpose=consent_policy.PURPOSE_DOCTOR_CONSULTATION,
        title=consent_policy.CONSENT_COPY["title"],
        body=consent_policy.CONSENT_COPY["body"],
        accept_label=consent_policy.CONSENT_COPY["accept_label"],
        decline_label=consent_policy.CONSENT_COPY["decline_label"],
        categories=[
            ConsentCategoryOut(key=key, label=consent_policy.CATEGORY_LABEL[key])
            for key in consent_policy.CATEGORIES
        ],
    )


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
    consent_in = payload.data_sharing_consent
    # A client that rendered an older version of the consent screen showed the
    # patient different terms from the ones we would record. Reject rather than
    # silently upgrade the grant to the current version. Both stamps are
    # required by the schema, so this check cannot be skipped by omission.
    if (
        consent_in.consent_version != consent_policy.CONSENT_VERSION
        or consent_in.policy_version != consent_policy.POLICY_VERSION
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Consent version is out of date. Please reload and review the "
                "sharing terms again."
            ),
        )
    consultation = consult_svc.create_consultation(
        db,
        patient_id=profile.id,
        doctor_id=payload.doctor_id,
        consultation_type=payload.consultation_type,
        data_consent_accepted=payload.data_consent_accepted,
        consent_categories=consent_in.categories,
        consent_source=consent_in.source,
        consent_client_app_version=consent_in.client_app_version,
        consent_locale=consent_in.locale,
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
        return [_for_doctor(db, r) for r in rows]
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
            return _for_doctor(db, consultation)
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
    access = consultation_access.assert_doctor_can_view(
        db, doctor=doctor, consultation_id=consultation_id
    )
    return build_summary(
        db,
        patient_id=access.patient_id,
        doctor_id=doctor.id,
        allowed_categories=access.allowed_categories,
    )


# ---------------------------------------------------------------------------
# Data-sharing consent — patient read + revoke
# ---------------------------------------------------------------------------


def _consent_out(record) -> DataSharingConsentOut:
    return DataSharingConsentOut(
        id=record.id,
        consultation_id=record.consultation_id,
        doctor_id=record.doctor_id,
        purpose=record.purpose,
        consent_version=record.consent_version,
        policy_version=record.policy_version,
        categories=sorted(record.granted_categories()),
        granted_at=record.granted_at,
        revoked_at=record.revoked_at,
        is_active=record.is_active_at(
            utcnow(), current_consent_version=consent_policy.CONSENT_VERSION
        ),
        source=record.source,
    )


def _own_consent_or_404(db: Session, consultation_id: str, patient_profile_id: str):
    """Load the consent for a consultation the CALLER owns.

    Cross-patient reads are answered 404, not 403: a patient must not be able to
    probe which consultation ids exist, or which doctor another patient booked.
    """
    record = consultation_consent.get_for_consultation(db, consultation_id)
    if record is None or record.patient_id != patient_profile_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data-sharing consent not found for this consultation.",
        )
    return record


@router.get("/{consultation_id}/data-sharing-consent", response_model=DataSharingConsentOut)
def get_data_sharing_consent(
    consultation_id: str,
    user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_session),
) -> DataSharingConsentOut:
    """Return the patient's own recorded consent for this consultation.

    Patient-only by design: a doctor must not be able to enumerate what a
    patient did or did not share — they simply receive the permitted data, or a
    403.
    """
    profile = _resolve_patient_profile(db, user.id)
    return _consent_out(_own_consent_or_404(db, consultation_id, profile.id))


@router.delete("/{consultation_id}/data-sharing-consent", response_model=Message)
def revoke_data_sharing_consent(
    consultation_id: str,
    user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_session),
) -> Message:
    """Withdraw sharing for this consultation. Takes effect immediately.

    Behaviour for an ACTIVE (IN_PROGRESS / PAID) consultation is deliberate and
    explicit:

    - The consultation is **not** cancelled. Cancelling is a separate decision
      with refund consequences, and it is the patient's to make.
    - The doctor's ``ConsultationAccessGrant`` is revoked in the same
      transaction, so an already-issued token or an open session cannot keep
      reading PHI — access is not merely denied at the next consent check, the
      care-relationship grant behind it is closed too.
    - Notes the doctor already wrote, the payment, and the audit trail all
      remain. Withdrawing data sharing is not a deletion request.
    """
    profile = _resolve_patient_profile(db, user.id)
    record = _own_consent_or_404(db, consultation_id, profile.id)
    # Load the consultation BEFORE mutating anything. A soft-deleted one raises
    # 404 here, where nothing has been staged; doing it afterwards would roll
    # back the revocation and answer 404 while leaving the consent active — a
    # withdrawal that silently did not happen.
    consultation = db.get(Consultation, consultation_id)

    # Idempotent: a second revoke is a no-op success, so a retried request or a
    # double-tap cannot 409 at a patient trying to withdraw consent.
    newly_revoked = consultation_consent.revoke(db, record=record, actor_id=profile.id)
    if newly_revoked and consultation is not None:
        consultation_access.revoke_on_end(db, consultation)
    db.commit()
    return Message(message="revoked")


@router.post("/{consultation_id}/data-sharing-consent", response_model=DataSharingConsentOut)
def restore_data_sharing_consent(
    consultation_id: str,
    payload: DataSharingConsentRestore | None = None,
    user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_session),
) -> DataSharingConsentOut:
    """Re-grant sharing the patient previously withdrew on this consultation.

    Withdrawing must be safe to do, which means it must be reversible. Without
    this, a mis-tapped revoke on a paid, in-progress consultation leaves the
    patient having bought a session the doctor can never be informed for — the
    consultation is deliberately not cancelled, so re-booking is not a remedy.

    The doctor's access grant is re-opened only while the consultation is still
    live (PAID / IN_PROGRESS). Re-consenting to a finished or cancelled
    consultation records the decision but reopens nothing, because the care
    relationship itself has ended.
    """
    profile = _resolve_patient_profile(db, user.id)
    record = _own_consent_or_404(db, consultation_id, profile.id)
    consultation = consult_svc.get_consultation_or_404(db, consultation_id)

    consultation_consent.restore(
        db,
        record=record,
        actor_id=profile.id,
        categories=payload.categories if payload else None,
    )
    if consultation.status in _LIVE_STATUSES:
        existing = consultation_access.get_active_grant(
            db,
            doctor_id=consultation.doctor_id,
            consultation_id=consultation.id,
            patient_id=consultation.patient_id,
        )
        if existing is None:
            consultation_access.create_grant(db, consultation)
    db.commit()
    db.refresh(record)
    return _consent_out(record)


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
        status_=payload.status,
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
