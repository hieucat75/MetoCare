"""Consultation bounded-context schemas (T10).

Patients never see payout internals beyond the price they pay; payout/fee fields
are exposed only where appropriate (doctor/admin flows use the model directly).
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from app.models.consultation import ConsultationType

# ---------------------------------------------------------------------------
# Consultation
# ---------------------------------------------------------------------------


class DataSharingConsentIn(BaseModel):
    """The patient's explicit consent, as captured by the booking modal.

    ``accepted`` must be literally ``True``; there is no other accepted value,
    so a client cannot book by omitting the field or sending a falsy one.
    """

    accepted: Literal[True] = Field(
        ..., description="Must be true — the patient pressed 'Đồng ý và tiếp tục'."
    )
    categories: list[str] = Field(
        ...,
        min_length=1,
        max_length=16,
        description=(
            "Category keys the patient granted. Unrecognised keys are dropped "
            "server-side; at least one recognised key is required."
        ),
    )
    consent_version: str = Field(
        ...,
        min_length=1,
        max_length=16,
        description=(
            "Consent version the client rendered. REQUIRED, and rejected when it "
            "does not match the server's current version. Optional would defeat "
            "the check entirely: the stale client this exists to catch is "
            "precisely the one that predates the field and would omit it."
        ),
    )
    policy_version: str = Field(
        ...,
        min_length=1,
        max_length=16,
        description=(
            "Copy version the client rendered. REQUIRED and stored as reported, "
            "not overwritten with the server's — the record has to say which "
            "words were actually on screen, which is the whole point of keeping "
            "it."
        ),
    )
    source: str | None = Field(default=None, max_length=32, description="'web' | 'mobile'")
    client_app_version: str | None = Field(default=None, max_length=32)
    locale: str | None = Field(default=None, max_length=32)


class ConsultationCreate(BaseModel):
    doctor_id: str
    consultation_type: ConsultationType = ConsultationType.CHAT
    data_consent_accepted: bool = Field(
        ..., description="Patient must accept data-sharing consent to book."
    )
    data_sharing_consent: DataSharingConsentIn = Field(
        ...,
        description=(
            "Required. The consultation-specific sharing consent recorded at "
            "booking; a consultation is never created without it."
        ),
    )
    chief_complaint: str | None = Field(default=None, max_length=2000)
    patient_note: str | None = Field(default=None, max_length=4000)
    booking_appointment_id: str | None = None


class DataSharingConsentRestore(BaseModel):
    """Re-grant a previously revoked consent, optionally narrowing categories.

    Re-sharing is a consent decision in its own right, so the client must have
    rendered the terms and echo which version it showed — the same rule booking
    follows. Without it, a one-tap "Chia sẻ lại" could record agreement to terms
    the patient never saw.

    Omitting ``categories`` re-grants exactly what was granted before; the server
    intersects with the previous grant either way, so this can only ever narrow.
    """

    accepted: Literal[True] = Field(
        ..., description="Must be true — the patient pressed the consent action."
    )
    consent_version: str = Field(..., min_length=1, max_length=16)
    policy_version: str = Field(..., min_length=1, max_length=16)
    categories: list[str] | None = Field(default=None, max_length=16)


class ConsentCategoryOut(BaseModel):
    key: str
    label: str


class DataSharingConsentPolicyOut(BaseModel):
    """Server-authored copy + category list for the booking consent modal.

    Clients render this verbatim so the words the patient reads are the words
    recorded against their grant.
    """

    consent_version: str
    policy_version: str
    purpose: str
    title: str
    body: str
    accept_label: str
    decline_label: str
    categories: list[ConsentCategoryOut]


class DataSharingConsentOut(BaseModel):
    """A recorded consent, as shown to the patient in Privacy settings."""

    id: str
    consultation_id: str
    doctor_id: str
    purpose: str
    consent_version: str
    policy_version: str
    categories: list[str]
    granted_at: dt.datetime
    revoked_at: dt.datetime | None
    is_active: bool
    source: str | None = None

    model_config = {"from_attributes": True}


class ConsultationOut(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    consultation_type: str
    status: str
    consultation_price: float
    data_consent_accepted: bool
    data_consent_accepted_at: dt.datetime | None
    # NOTE (product/security review): chief_complaint/patient_note are patient
    # free-text ("reason for visit") and are currently visible to the assigned
    # doctor before an access grant is issued. Behavior left unchanged pending
    # product sign-off on pre-grant visibility of this reason-for-visit text.
    chief_complaint: str | None
    patient_note: str | None
    booking_appointment_id: str | None
    confirmed_at: dt.datetime | None
    paid_at: dt.datetime | None
    started_at: dt.datetime | None
    completed_at: dt.datetime | None
    cancelled_at: dt.datetime | None
    cancel_reason: str | None
    created_at: dt.datetime | None = None
    disclaimer: str | None = None

    model_config = {"from_attributes": True}


class ConsultationCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


class PaymentOut(BaseModel):
    """Doctor/admin-facing payment view — includes payout + fee internals."""

    id: str
    consultation_id: str
    consultation_price: float
    platform_fee: float
    doctor_payout: float
    currency: str
    payment_status: str
    payment_provider: str
    paid_at: dt.datetime | None
    refunded_at: dt.datetime | None

    model_config = {"from_attributes": True}


class PatientPaymentOut(BaseModel):
    """Patient-facing payment view — only what the patient pays.

    Intentionally omits ``platform_fee`` and ``doctor_payout``: patients never
    see payout internals beyond the price they pay.
    """

    consultation_id: str
    consultation_price: float
    currency: str
    payment_status: str
    paid_at: dt.datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


class NoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=8000)
    note_type: str = Field(default="recommendation", max_length=32)
    # 'draft' (Lưu nháp) or 'finalized' (Hoàn tất). Always creates a new row —
    # never edits an existing one, preserving the append-only invariant.
    status: str = Field(default="finalized", pattern="^(draft|finalized)$")


class NoteOut(BaseModel):
    id: str
    consultation_id: str
    doctor_id: str
    content: str
    note_type: str
    status: str
    finalized_at: dt.datetime | None = None
    created_at: dt.datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    id: str
    consultation_id: str
    patient_id: str
    doctor_id: str
    rating: int
    feedback: str | None
    created_at: dt.datetime | None = None

    model_config = {"from_attributes": True}
