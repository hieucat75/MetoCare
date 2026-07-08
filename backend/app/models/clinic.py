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


class ClinicPatientRelationshipStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MERGED = "merged"


class ClinicSubscriptionStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


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
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    package_visit_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(16), default=ClinicServiceStatus.ACTIVE, nullable=False
    )

    __table_args__ = (Index("ix_clinic_services_clinic_status", "clinic_id", "status"),)


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
