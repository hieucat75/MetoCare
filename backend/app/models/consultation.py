"""Consultation bounded context — Doctor Marketplace MVP.

New aggregate for paid, verified-doctor consultations with consultation-scoped,
audited, read-only access to patient data.  Kept separate from the T21 booking
layer (``BookingAppointment`` may optionally reference a ``Consultation``, never
the reverse).

Immutability / safety invariants (enforced by services + absence of write paths):
- ``ConsultationNote`` is append-only (no update/delete function exists anywhere).
- Doctors never get a write path to patient-owned health records.
- Patient data is reachable only through an active ``ConsultationAccessGrant``.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.crypto import EncryptedString
from app.core.database import Base

from ._mixins import _NOW, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey

# ---------------------------------------------------------------------------
# Enums (StrEnum, UPPERCASE values — matches CarePlanStatus convention)
# ---------------------------------------------------------------------------


class ConsultationStatus(StrEnum):
    """Consultation lifecycle state machine.

    Allowed transitions (enforced in app.services.consultation):
      REQUESTED   → CONFIRMED | PAID | CANCELLED
      CONFIRMED   → PAID | CANCELLED
      PAID        → IN_PROGRESS | COMPLETED | CANCELLED
      IN_PROGRESS → COMPLETED | CANCELLED
      COMPLETED   → (terminal)
      CANCELLED   → (terminal)
    """

    REQUESTED = "REQUESTED"
    CONFIRMED = "CONFIRMED"
    PAID = "PAID"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ConsultationType(StrEnum):
    CHAT = "CHAT"
    VIDEO = "VIDEO"  # placeholder — not wired for MVP
    IN_PERSON = "IN_PERSON"  # placeholder — not wired for MVP


class PaymentStatus(StrEnum):
    UNPAID = "UNPAID"
    PAID = "PAID"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"


class PaymentProvider(StrEnum):
    MANUAL = "MANUAL"
    MOCK = "MOCK"
    FUTURE_GATEWAY = "FUTURE_GATEWAY"


class DoctorVerificationStatus(StrEnum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    VERIFIED = "VERIFIED"
    SUSPENDED = "SUSPENDED"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# Consultation aggregate root
# ---------------------------------------------------------------------------


class Consultation(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "consultations"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    # References the Doctor aggregate (doctors.id), NOT users.id.
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)

    consultation_type: Mapped[str] = mapped_column(
        String(16), default=ConsultationType.CHAT, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default=ConsultationStatus.REQUESTED, nullable=False
    )
    # Snapshot of doctor.consultation_fee at creation time — immutable thereafter.
    consultation_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Data-sharing consent captured at booking (required to create).
    data_consent_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    data_consent_accepted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The ONLY link to the booking layer (nullable, optional).
    booking_appointment_id: Mapped[str | None] = mapped_column(
        ForeignKey("booking_appointments.id"), index=True, nullable=True
    )

    # Lifecycle stamps
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


# ---------------------------------------------------------------------------
# Payment (one per consultation for MVP)
# ---------------------------------------------------------------------------


class ConsultationPayment(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "consultation_payments"

    consultation_id: Mapped[str] = mapped_column(
        ForeignKey("consultations.id"), index=True, nullable=False, unique=True
    )
    consultation_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    platform_fee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    doctor_payout: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="VND", nullable=False)
    payment_status: Mapped[str] = mapped_column(
        String(16), default=PaymentStatus.UNPAID, nullable=False
    )
    payment_provider: Mapped[str] = mapped_column(
        String(24), default=PaymentProvider.MOCK, nullable=False
    )
    # For a future real gateway (transaction/charge id). Unused by MOCK.
    provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Notes — APPEND-ONLY (no update/delete path anywhere)
# ---------------------------------------------------------------------------


class ConsultationNote(UUIDPrimaryKey, TimestampMixin, Base):
    """Doctor's recommendation note. PHI content is encrypted at rest.

    APPEND-ONLY: there is intentionally no update or delete function anywhere in
    the codebase. A correction is a new note, never an edit.
    """

    __tablename__ = "consultation_notes"

    consultation_id: Mapped[str] = mapped_column(
        ForeignKey("consultations.id"), index=True, nullable=False
    )
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    # Non-nullable — a failed decrypt must raise (never silently become None
    # in a `str` field, which would violate the NOT NULL contract and crash
    # response serialization). Explicit example from the security review.
    content: Mapped[str] = mapped_column(
        EncryptedString(on_decrypt_failure="raise"), nullable=False
    )  # PHI: encrypted
    note_type: Mapped[str] = mapped_column(String(32), default="recommendation", nullable=False)


# ---------------------------------------------------------------------------
# Reviews (one per consultation)
# ---------------------------------------------------------------------------


class ConsultationReview(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "consultation_reviews"

    consultation_id: Mapped[str] = mapped_column(
        ForeignKey("consultations.id"), index=True, nullable=False, unique=True
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    @validates("rating")
    def _validate_rating(self, key: str, value: int) -> int:
        if value is None or int(value) < 1 or int(value) > 5:
            raise ValueError("rating must be an integer between 1 and 5")
        return int(value)


# ---------------------------------------------------------------------------
# Consultation-scoped read-access grant
# ---------------------------------------------------------------------------


class ConsultationAccessGrant(UUIDPrimaryKey, TimestampMixin, Base):
    """Scoped, revocable read access from a doctor to a patient's data.

    ``is_active`` is True iff the grant is granted AND not revoked AND not
    expired. Access is revoked (revoked_at set) when the consultation is
    COMPLETED or CANCELLED, so subsequent summary reads return 403.
    """

    __tablename__ = "consultation_access_grants"

    consultation_id: Mapped[str] = mapped_column(
        ForeignKey("consultations.id"), index=True, nullable=False
    )
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    granted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW, nullable=False
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_active(self, *, now: dt.datetime | None = None) -> bool:
        """Return True iff granted AND not revoked AND not expired."""
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            reference = now or dt.datetime.now(dt.UTC)
            expires = self.expires_at
            # Tolerate naive datetimes stored by SQLite.
            if expires.tzinfo is None:
                reference = reference.replace(tzinfo=None)
            if expires <= reference:
                return False
        return True
