"""Consultation bounded-context schemas (T10).

Patients never see payout internals beyond the price they pay; payout/fee fields
are exposed only where appropriate (doctor/admin flows use the model directly).
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.models.consultation import ConsultationType

# ---------------------------------------------------------------------------
# Consultation
# ---------------------------------------------------------------------------


class ConsultationCreate(BaseModel):
    doctor_id: str
    consultation_type: ConsultationType = ConsultationType.CHAT
    data_consent_accepted: bool = Field(
        ..., description="Patient must accept data-sharing consent to book."
    )
    chief_complaint: str | None = Field(default=None, max_length=2000)
    patient_note: str | None = Field(default=None, max_length=4000)
    booking_appointment_id: str | None = None


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
