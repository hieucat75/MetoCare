"""Doctor / Clinic / Appointment / CarePlan / Encounter models (Data_Model_Overview §3.1)."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.crypto import EncryptedString
from app.core.database import Base

from ._mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey
from .consultation import DoctorVerificationStatus


class CarePlanStatus(StrEnum):
    """CarePlan lifecycle state machine.

    Valid transitions (C2):
      DRAFT          → PENDING_REVIEW  (any author; required for ai_generated)
      PENDING_REVIEW → APPROVED         (DOCTOR only)
      PENDING_REVIEW → REJECTED         (DOCTOR only)
      APPROVED       → ACTIVE           (DOCTOR only)
      ACTIVE         → SUPERSEDED       (system, when newer version activated)
      ACTIVE         → ARCHIVED         (DOCTOR or admin)
      Any            → ARCHIVED         (DOCTOR or admin)

    AI paths may ONLY create with status=DRAFT and ai_generated=True.
    AI may NOT set PENDING_REVIEW, APPROVED, ACTIVE, SUPERSEDED, or ARCHIVED.
    """

    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"
    REJECTED = "REJECTED"


# Statuses that AI code paths (ai_generated=True) may NEVER set at construction
_AI_CAREPLAN_FORBIDDEN_STATUSES: frozenset[str] = frozenset(
    {
        "PENDING_REVIEW",
        "APPROVED",
        "ACTIVE",
        "SUPERSEDED",
        "ARCHIVED",
        "pending_review",
        "approved",
        "active",
        "superseded",
        "archived",
    }
)


class Clinic(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinics"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(512))
    phone: Mapped[str | None] = mapped_column(String(32))
    # Step 5: Clinic additional fields
    email: Mapped[str | None] = mapped_column(String(255))
    specialty_tags: Mapped[str | None] = mapped_column(Text)  # serialized or comma-separated tags
    operating_hours: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Doctor(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "doctors"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    clinic_id: Mapped[str | None] = mapped_column(ForeignKey("clinics.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(128))
    license_no: Mapped[str | None] = mapped_column(String(64))
    # Step 5: Doctor additional fields
    bio: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    consultation_fee: Mapped[float | None] = mapped_column(Float)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # ------------------------------------------------------------------ #
    # Marketplace listing fields (Doctor Marketplace MVP, T10)           #
    # verification_status is the SOURCE OF TRUTH; is_verified is a legacy #
    # mirror kept in sync on every verification transition.              #
    # ------------------------------------------------------------------ #
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default=DoctorVerificationStatus.PENDING_VERIFICATION,
        nullable=False,
    )
    years_experience: Mapped[int | None] = mapped_column(Integer)
    languages: Mapped[str | None] = mapped_column(String(255))  # comma-separated
    hospital_name: Mapped[str | None] = mapped_column(String(255))
    consultation_methods: Mapped[str | None] = mapped_column(String(255))  # e.g. "chat,video"
    rating_avg: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DoctorClinic(Base):
    """Step 5: doctor_clinic junction table."""

    __tablename__ = "doctor_clinic"

    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), primary_key=True)
    role_at_clinic: Mapped[str | None] = mapped_column(String(64))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    joined_at: Mapped[dt.date] = mapped_column(Date, default=dt.date.today, nullable=False)
    left_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class Appointment(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "appointments"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True, nullable=False)
    scheduled_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="offline")  # online/offline
    status: Mapped[str] = mapped_column(String(24), default="requested")
    # Set when triage escalates a case to a doctor (doctor handoff).
    handoff_reason: Mapped[str | None] = mapped_column(String(255))


class Encounter(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    """Step 4: Encounter model."""

    __tablename__ = "encounters"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    doctor_id: Mapped[str | None] = mapped_column(
        ForeignKey("doctors.id"), index=True, nullable=True
    )
    appointment_id: Mapped[str | None] = mapped_column(
        ForeignKey("appointments.id"), index=True, nullable=True
    )
    encounter_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # pending_review / in_progress / completed / cancelled
    status: Mapped[str] = mapped_column(String(32), default="pending_review", nullable=False)
    chief_complaint: Mapped[str | None] = mapped_column(Text)
    # Nullable — a failed decrypt falls back to None rather than raising.
    notes: Mapped[str | None] = mapped_column(
        EncryptedString(on_decrypt_failure="none")
    )  # PHI: encrypted
    encounter_date: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=dt.datetime.utcnow
    )


class CarePlan(UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin, Base):
    """CarePlan with C2 status-machine enforcement.

    C2 SAFETY INVARIANT:
    - AI code paths MUST use `CarePlan.create_from_ai()` which sets
      status=DRAFT and ai_generated=True.
    - Only DoctorCarePlanService (T5) may transition status to APPROVED/ACTIVE.
    - The @validates hook on status rejects forbidden states when ai_generated=True.
    """

    __tablename__ = "care_plans"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    encounter_id: Mapped[str | None] = mapped_column(
        ForeignKey("encounters.id"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable — a failed decrypt falls back to None rather than raising.
    content: Mapped[str | None] = mapped_column(
        EncryptedString(on_decrypt_failure="none")
    )  # PHI: encrypted content
    status: Mapped[str] = mapped_column(String(32), default=CarePlanStatus.DRAFT, nullable=False)
    approved_by_doctor_id: Mapped[str | None] = mapped_column(
        ForeignKey("doctors.id"), index=True, nullable=True
    )
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # ------------------------------------------------------------------ #
    # C2 GUARD: order-independent via dual @validates                      #
    # ------------------------------------------------------------------ #

    _AI_FORBIDDEN_CP_STATUSES: frozenset[str] = frozenset(
        {
            "PENDING_REVIEW",
            "APPROVED",
            "ACTIVE",
            "SUPERSEDED",
            "ARCHIVED",
        }
    )

    def _check_ai_status(self) -> None:
        """Raise if ai_generated=True and current status is forbidden."""
        status_val = getattr(self, "status", None)
        ai_gen = getattr(self, "ai_generated", False)
        forbidden = self._AI_FORBIDDEN_CP_STATUSES
        if ai_gen and status_val is not None and str(status_val).upper() in forbidden:
            raise ValueError(
                f"AI-generated CarePlan cannot be created with status='{status_val}'. "
                "Only DRAFT is allowed. Use DoctorCarePlanService to transition."
            )

    @validates("status")
    def _validate_status(self, key: str, value: str) -> str:
        """Reject forbidden status if ai_generated is already True (set before status)."""
        if value is None:
            return value  # type: ignore[return-value]
        # Store temporarily so ai_generated validator can also check
        forbidden = self._AI_FORBIDDEN_CP_STATUSES
        if getattr(self, "ai_generated", False) and str(value).upper() in forbidden:
            raise ValueError(
                f"AI-generated CarePlan cannot be created with status='{value}'. "
                "Only DRAFT is allowed. Use DoctorCarePlanService to transition."
            )
        return value

    @validates("ai_generated")
    def _validate_ai_generated(self, key: str, value: bool) -> bool:  # noqa: FBT001
        """When ai_generated flips to True, recheck the current status.

        Catches CarePlan(status='ACTIVE', ai_generated=True) where status is
        assigned first (before ai_generated is set). When ai_generated=True arrives,
        we check whatever status is already stored in the instance __dict__.
        """
        if value:
            # Read status directly from instance __dict__ (bypasses descriptor)
            status_val = self.__dict__.get("status")
            if status_val is not None and str(status_val).upper() in self._AI_FORBIDDEN_CP_STATUSES:
                raise ValueError(
                    f"AI-generated CarePlan cannot be created with status='{status_val}'. "
                    "Only DRAFT is allowed. Use DoctorCarePlanService to transition."
                )
        return value

    @classmethod
    def create_from_ai(
        cls,
        *,
        patient_id: str,
        title: str,
        content: str | None = None,
        encounter_id: str | None = None,
        version: int = 1,
    ) -> CarePlan:
        """Factory for AI-generated care plans.

        Enforces C2: status=DRAFT, ai_generated=True.
        This is the ONLY constructor AI service code paths should call.
        DoctorCarePlanService.approve() transitions to APPROVED/ACTIVE via SQL UPDATE.
        """
        return cls(
            patient_id=patient_id,
            title=title,
            content=content,
            encounter_id=encounter_id,
            version=version,
            ai_generated=True,  # set BEFORE status so @validates can check it
            status=CarePlanStatus.DRAFT,
        )


class DoctorReviewDecision(UUIDPrimaryKey, TimestampMixin, Base):
    """Encrypted store for a doctor's review decision + free-text notes.

    The unified doctor-portal review flow (``services.doctor_portal``) records
    the domain action (lab verified / care plan approved / AI rec accepted) in
    the PHI-FREE ``AuditLog``. The reviewer's ``comment`` and ``internal_note``
    can contain PHI, so — per AuditLog's contract ("never stores sensitive
    content") — they are persisted here instead, encrypted at rest.
    """

    __tablename__ = "doctor_review_decisions"

    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    item_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    patient_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    doctor_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(EncryptedString)  # PHI: encrypted
    internal_note: Mapped[str | None] = mapped_column(EncryptedString)  # PHI: encrypted


class BookingHealthSnapshot(UUIDPrimaryKey, Base):
    """Step 4: BookingHealthSnapshot model (append-only)."""

    __tablename__ = "booking_health_snapshots"

    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id"), index=True, nullable=False
    )
    # Non-nullable — a failed decrypt must raise (never silently become None
    # in a `str` field, which would violate the NOT NULL contract and crash
    # response serialization).
    payload: Mapped[str] = mapped_column(
        EncryptedString(on_decrypt_failure="raise"), nullable=False
    )  # PHI: encrypted snapshot
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False
    )
