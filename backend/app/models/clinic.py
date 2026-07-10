"""Clinic SaaS Phase C0 — multi-tenant foundation models.

New tables per `docs/clinic-saas/DATA_MODEL.md` §2-8: `ClinicBranch`,
`ClinicMembership`, `ClinicInvitation`, `ClinicService`,
`ClinicPatientRelationship`, `SubscriptionPlan`, `ClinicSubscription`.

None of these columns carry PHI — patient identity/clinical content stays on
`PatientProfile`/clinical tables (untouched here); this module only records
tenant/membership/catalog/subscription metadata.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base

from ._mixins import _NOW, TimestampMixin, UUIDPrimaryKey


class ClinicRole(StrEnum):
    """The 7 clinic-tenant roles (RBAC_MATRIX.md §1) — distinct axis from
    `UserRole` (platform role). Stored as a JSON array on `ClinicMembership.roles`
    / `ClinicInvitation.roles`, not a DB enum column (multi-role per membership)."""

    OWNER = "owner"
    ADMIN = "admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    RECEPTIONIST = "receptionist"
    CARE_COORDINATOR = "care_coordinator"
    ACCOUNTANT = "accountant"


class ClinicBranchStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ClinicMembershipStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class ClinicInvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ClinicServiceStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ClinicServiceType(StrEnum):
    SINGLE = "single"
    PACKAGE = "package"


class ClinicPatientRelationshipStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MERGED = "merged"


class ClinicSubscriptionStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ClinicAppointmentStatus(StrEnum):
    """Full BRD lifecycle (m07-appointment.md §7.5). M07 only routes a
    subset of transitions (confirm/cancel/reschedule/no_show,
    no_show->arrived); arrived->in_queue->in_consultation->completed are
    M08/M09's own action endpoints — the shared validator already knows
    these are valid so M08/M09 can reuse it (M07_IMPLEMENTATION_PLAN.md §4)."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    IN_QUEUE = "in_queue"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class ClinicAppointmentSource(StrEnum):
    """APPT-01 — every appointment records which channel created it."""

    RECEPTION = "reception"
    DOCTOR = "doctor"
    PATIENT = "patient"
    CARE_COORDINATOR = "care_coordinator"
    MARKETPLACE = "marketplace"
    API_PARTNER = "api_partner"


class ClinicBranch(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinic_branches"

    clinic_id: Mapped[str] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[dict | None] = mapped_column(JSON)
    phone: Mapped[str | None] = mapped_column(String(32))
    working_hours: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=ClinicBranchStatus.ACTIVE, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("clinic_id", "name", name="uq_clinic_branches_clinic_name"),
        Index("ix_clinic_branches_clinic_status", "clinic_id", "status"),
    )


class ClinicMembership(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinic_memberships"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    clinic_id: Mapped[str] = mapped_column(
        ForeignKey("clinics.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Non-empty array of ClinicRole values, app-enforced (see services/clinic_membership.py).
    roles: Mapped[list] = mapped_column(JSON, nullable=False)
    # Array of ClinicBranch.id; empty until branches exist.
    branch_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    doctor_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default=ClinicMembershipStatus.INVITED, nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    joined_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    left_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    invited_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "clinic_id", name="uq_clinic_memberships_user_clinic"),
        Index("ix_clinic_memberships_clinic_status", "clinic_id", "status"),
        Index("ix_clinic_memberships_user_status", "user_id", "status"),
    )


class ClinicInvitation(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinic_invitations"

    clinic_id: Mapped[str] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    invited_email: Mapped[str | None] = mapped_column(String(255))
    invited_phone: Mapped[str | None] = mapped_column(String(20))
    roles: Mapped[list] = mapped_column(JSON, nullable=False)
    branch_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=ClinicInvitationStatus.PENDING, nullable=False
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invited_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    accepted_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "invited_email IS NOT NULL OR invited_phone IS NOT NULL",
            name="ck_clinic_invitations_email_or_phone",
        ),
        # Partial unique indexes (DATA_MODEL.md §4): only one live `pending`
        # invite per (clinic, email/phone) at a time; historical
        # accepted/revoked/expired rows are unconstrained.
        Index(
            "uq_clinic_invitations_pending_email",
            "clinic_id",
            "invited_email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index(
            "uq_clinic_invitations_pending_phone",
            "clinic_id",
            "invited_phone",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )


class ClinicService(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinic_services"

    clinic_id: Mapped[str] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # null = all branches; non-null = restricted to these ClinicBranch.id values.
    branch_ids: Mapped[list | None] = mapped_column(JSON)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # BRD m05-services-pricing.md §5.3: unique in tenant, [A-Z0-9-]. Nullable at
    # DB layer (partial unique index below); required at Create-schema layer,
    # matching the project's "validate at service/schema layer" convention.
    code: Mapped[str | None] = mapped_column(String(32))
    specialty: Mapped[str | None] = mapped_column(String(64))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    # Array of Doctor.id (not ClinicMembership.id) scoped to this clinic's
    # active doctor memberships — validated in the service layer, mirrors
    # assert_branch_ids_belong_to_clinic's pattern for branch_ids.
    doctor_ids: Mapped[list | None] = mapped_column(JSON)
    type: Mapped[str] = mapped_column(
        String(16), default=ClinicServiceType.SINGLE, nullable=False
    )
    # Codex second-pass review P1: money must not round-trip through float —
    # `Decimal` end-to-end (Python + Numeric(12,2) DB type) avoids binary
    # floating-point precision loss on currency values.
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    package_visit_count: Mapped[int | None] = mapped_column(Integer)
    # type=package only (§5.3 "Gói chăm sóc bổ sung"). 3/6/12-month chronic-care
    # packages: included_items = {visit_count, lab_read_count, teleconsult_count};
    # benefits = {med_reminder, followup_reminder, metric_tracking} (booleans).
    duration_months: Mapped[int | None] = mapped_column(Integer)
    included_items: Mapped[dict | None] = mapped_column(JSON)
    benefits: Mapped[dict | None] = mapped_column(JSON)
    cancellation_refund_policy: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(16), default=ClinicServiceStatus.ACTIVE, nullable=False
    )

    __table_args__ = (
        Index("ix_clinic_services_clinic_status", "clinic_id", "status"),
        Index(
            "uq_clinic_services_clinic_code",
            "clinic_id",
            "code",
            unique=True,
            postgresql_where=text("code IS NOT NULL"),
            sqlite_where=text("code IS NOT NULL"),
        ),
        # Codex second-pass review P1: name uniqueness (BR-M05 §5.3 "Unique
        # trong tenant") was only a service-layer check-then-insert, racy
        # under concurrency. A real DB constraint makes the race safe; the
        # service layer's pre-check stays as a friendly-error fast path.
        # Index, not UniqueConstraint: SQLite can't ALTER/DROP a named
        # constraint without batch mode, but a plain unique index drops
        # cleanly on both SQLite and Postgres (same pattern as the `code`
        # index above).
        Index("uq_clinic_services_clinic_name", "clinic_id", "name", unique=True),
    )


class ClinicPatientRelationship(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinic_patient_relationships"

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    clinic_id: Mapped[str] = mapped_column(
        ForeignKey("clinics.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=ClinicPatientRelationshipStatus.ACTIVE, nullable=False
    )
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW, nullable=False
    )
    # Clinic SaaS C1 M06: clinic-only operational note, no PHI (same
    # discipline as AuditLog.details — reference/business text, never
    # clinical content; clinical notes live on M09's Encounter/Notes model).
    internal_notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "clinic_id", "patient_code", name="uq_clinic_patient_rel_clinic_code"
        ),
        UniqueConstraint(
            "clinic_id", "patient_id", name="uq_clinic_patient_rel_clinic_patient"
        ),
    )


class SubscriptionPlan(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "subscription_plans"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # {max_branches, max_doctors, max_active_patients, copilot_quota_per_month,
    #  crm_automation_enabled, advanced_reports_enabled, api_sso_enabled}
    entitlements: Mapped[dict] = mapped_column(JSON, nullable=False)


class ClinicSubscription(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "clinic_subscriptions"

    clinic_id: Mapped[str] = mapped_column(
        ForeignKey("clinics.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW, nullable=False
    )
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), default=ClinicSubscriptionStatus.TRIAL, nullable=False
    )

    __table_args__ = (
        # At most one *current* (trial|active) subscription per clinic; unlimited
        # historical expired/cancelled rows (DATA_MODEL.md §8 deviation — keeps
        # plan-change history instead of UPDATE-in-place).
        Index(
            "uq_clinic_subscriptions_current",
            "clinic_id",
            unique=True,
            postgresql_where=text("status IN ('trial', 'active')"),
            sqlite_where=text("status IN ('trial', 'active')"),
        ),
    )


class ClinicAppointment(UUIDPrimaryKey, TimestampMixin, Base):
    """Clinic-scoped appointment (Clinic SaaS C1 M07). A third, deliberately
    separate table from the legacy `Appointment` (`care.py`, doctor-handoff/
    encounter-flow entity) and the marketplace `BookingAppointment` (T21,
    clinic-agnostic, keyed to `users.id`) — see
    `docs/clinic-saas/M07_IMPLEMENTATION_PLAN.md` §1. No consultation/
    marketplace code path is modified by this model.
    """

    __tablename__ = "clinic_appointments"

    clinic_id: Mapped[str] = mapped_column(
        ForeignKey("clinics.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    branch_id: Mapped[str] = mapped_column(
        ForeignKey("clinic_branches.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Nullable — BRD: "required trừ dịch vụ không cần bác sĩ".
    doctor_id: Mapped[str | None] = mapped_column(
        ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=True
    )
    service_id: Mapped[str] = mapped_column(
        ForeignKey("clinic_services.id", ondelete="RESTRICT"), nullable=False
    )
    # Snapshotted at create — same Decimal-end-to-end precision discipline as
    # ClinicService.price (Codex second-pass review P1 precedent).
    price_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    start_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=ClinicAppointmentStatus.PENDING, nullable=False
    )
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_source: Mapped[str] = mapped_column(String(20), nullable=False)
    # Bare reference, no FK — M11 Care Plan doesn't exist yet (same bare-
    # reference convention as AuditLog.resource_id).
    linked_care_plan_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Self-FK: "đổi lịch = Cancelled(cũ) + lịch mới liên kết" (BRD §7.5) — the
    # chain of appointments IS the reschedule history, no separate history
    # table (same "no redundant history table" discipline as M05's
    # price-audit-via-AuditLog decision).
    reschedule_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("clinic_appointments.id", ondelete="RESTRICT"), nullable=True
    )
    # Plain scheduling note, non-PHI — clinical content stays out of scope,
    # belongs to M09 Encounter.notes (same precedent as legacy
    # BookingAppointment.notes).
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_clinic_appointments_clinic_branch_start",
            "clinic_id",
            "branch_id",
            "start_time",
        ),
        Index(
            "ix_clinic_appointments_clinic_doctor_start",
            "clinic_id",
            "doctor_id",
            "start_time",
        ),
        Index("ix_clinic_appointments_clinic_status", "clinic_id", "status"),
        # AC-M07-02's DB-level double-booking guarantee: catches exact-
        # start-time collisions for a doctor across all non-terminal
        # statuses. Scope-bounded (documented in M07_IMPLEMENTATION_PLAN.md
        # §2) — free-form overlapping-but-different-start-time bookings are
        # only caught by the service layer's best-effort pre-check, since a
        # true range-overlap EXCLUDE constraint is Postgres-only and would
        # break the SQLite upgrade/downgrade/upgrade verification.
        Index(
            "uq_clinic_appointments_doctor_start",
            "doctor_id",
            "start_time",
            unique=True,
            postgresql_where=text(
                "status NOT IN ('cancelled', 'no_show') AND doctor_id IS NOT NULL"
            ),
            sqlite_where=text(
                "status NOT IN ('cancelled', 'no_show') AND doctor_id IS NOT NULL"
            ),
        ),
    )
