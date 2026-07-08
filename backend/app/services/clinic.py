"""Clinic CRUD + lifecycle (Clinic SaaS Phase C0).

Thin data-access + lifecycle-transition layer behind the `/clinics` routes —
no business logic in route handlers (project convention). Every mutation is
audited via `app.services.audit.record` with `clinic_id` populated
(TENANT_ARCHITECTURE.md §2.10). No hard delete anywhere — every terminal
state is a `status` flip on the row (BR-M01-03).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.care import Clinic
from app.models.clinic import ClinicMembership, ClinicMembershipStatus, ClinicRole
from app.services import audit
from app.services.clinic_subscription import create_trial_subscription

_SETTINGS_FIELDS = (
    "legal_name",
    "tax_code",
    "license_no",
    "clinic_type",
    "branding",
    "cancellation_policy",
    "queue_config",
    "overbooking_policy",
    "name",
    "address",
    "phone",
    "email",
)


def _filter_settings(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if k in _SETTINGS_FIELDS and v is not None}


def create_clinic(db: Session, *, owner_user_id: str, name: str, **settings_fields) -> Clinic:
    """Onboard a new clinic (BR-M01/M04 onboarding flow):

    - Clinic row created in `trial` status.
    - The caller becomes its Owner (ACTIVE ClinicMembership, roles=["owner"]).
    - A default trial ClinicSubscription row is created.

    Caller (the route) commits the transaction.
    """
    clinic = Clinic(name=name, status="trial", **_filter_settings(settings_fields))
    db.add(clinic)
    db.flush()

    membership = ClinicMembership(
        user_id=owner_user_id,
        clinic_id=clinic.id,
        roles=[ClinicRole.OWNER],
        branch_ids=[],
        status=ClinicMembershipStatus.ACTIVE,
        is_primary=True,
        joined_at=dt.date.today(),
    )
    db.add(membership)
    db.flush()

    create_trial_subscription(db, clinic_id=clinic.id)

    audit.record(
        db,
        actor_type="user",
        actor_id=owner_user_id,
        action="clinic_create",
        resource_type="clinic",
        resource_id=clinic.id,
        clinic_id=clinic.id,
    )
    return clinic


def get_clinic(db: Session, clinic_id: str) -> Clinic | None:
    return db.get(Clinic, clinic_id)


def list_clinics(
    db: Session, *, skip: int = 0, limit: int = 50, status_filter: str | None = None
) -> tuple[list[Clinic], int]:
    """Platform-admin listing (paginated) — used by the platform-override
    surface, never by ordinary clinic-role routes."""
    conditions = [Clinic.status == status_filter] if status_filter else []
    total = db.execute(
        select(func.count()).select_from(Clinic).where(*conditions)
    ).scalar_one()
    items = list(
        db.execute(
            select(Clinic)
            .where(*conditions)
            .order_by(Clinic.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars()
    )
    return items, total


def update_clinic_settings(db: Session, *, clinic: Clinic, actor_id: str, **fields) -> Clinic:
    changed = _filter_settings(fields)
    for key, value in changed.items():
        setattr(clinic, key, value)
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_update",
        resource_type="clinic",
        resource_id=clinic.id,
        clinic_id=clinic.id,
    )
    return clinic


def deactivate_clinic(db: Session, *, clinic: Clinic, actor_id: str) -> Clinic:
    """Owner-initiated voluntary closure — terminal state, never a hard delete."""
    clinic.status = "deactivated"
    clinic.deactivated_at = utcnow()
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_deactivate",
        resource_type="clinic",
        resource_id=clinic.id,
        clinic_id=clinic.id,
        severity="warning",
    )
    return clinic


def suspend_clinic(db: Session, *, clinic: Clinic, actor_id: str) -> Clinic:
    """Platform-only policy-violation suspension (via `require_platform_override`,
    which already writes its own `platform_cross_tenant_access` audit row —
    this is the additional, action-specific audit entry)."""
    clinic.status = "suspended"
    db.flush()
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor_id,
        action="clinic_suspend",
        resource_type="clinic",
        resource_id=clinic.id,
        clinic_id=clinic.id,
        severity="warning",
    )
    return clinic


def restore_clinic(db: Session, *, clinic: Clinic, actor_id: str) -> Clinic:
    """Platform-only restore from suspended/deactivated back to active."""
    clinic.status = "active"
    clinic.restored_at = utcnow()
    clinic.deactivated_at = None
    db.flush()
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor_id,
        action="clinic_restore",
        resource_type="clinic",
        resource_id=clinic.id,
        clinic_id=clinic.id,
        severity="warning",
    )
    return clinic
