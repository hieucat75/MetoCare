"""Clinic subscription + entitlements resolution (Clinic SaaS Phase C0).

No real billing/payment integration (explicitly out of scope for C0) — this
module only manages the subscription/entitlement *data model* and the
read-side gate on top of it. `Entitlements` is never persisted per-clinic
(DATA_MODEL.md §8 / TENANT_ARCHITECTURE.md §2.8) — always resolved fresh from
the clinic's current `ClinicSubscription` -> `SubscriptionPlan.entitlements`
at read time, so plan-limit changes take effect everywhere without a drift-
prone per-clinic copy (DRY).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.clinic import (
    ClinicSubscription,
    ClinicSubscriptionStatus,
    SubscriptionPlan,
)

TRIAL_PLAN_CODE = "trial"
TRIAL_DURATION_DAYS = 30

_CURRENT_STATUSES = (ClinicSubscriptionStatus.TRIAL, ClinicSubscriptionStatus.ACTIVE)


@dataclass(frozen=True)
class Entitlements:
    max_branches: int
    max_doctors: int
    max_active_patients: int
    copilot_quota_per_month: int
    crm_automation_enabled: bool
    advanced_reports_enabled: bool
    api_sso_enabled: bool


def get_plan_by_code(db: Session, code: str) -> SubscriptionPlan | None:
    return db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.code == code)
    ).scalar_one_or_none()


def list_plans(db: Session) -> list[SubscriptionPlan]:
    return list(
        db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.code)).scalars()
    )


def create_trial_subscription(db: Session, *, clinic_id: str) -> ClinicSubscription:
    """Create the default trial subscription row for a newly onboarded clinic
    (BR-M01/M04 onboarding flow: "a new clinic is created in trial status
    with a default trial subscription row"). Caller owns the commit."""
    plan = get_plan_by_code(db, TRIAL_PLAN_CODE)
    if plan is None:
        raise RuntimeError(
            "subscription_plans has no seeded 'trial' row — migration "
            "c0_m7_subscription_plan must run before any clinic can be onboarded."
        )
    subscription = ClinicSubscription(
        clinic_id=clinic_id,
        plan_id=plan.id,
        started_at=utcnow(),
        expires_at=utcnow() + dt.timedelta(days=TRIAL_DURATION_DAYS),
        status=ClinicSubscriptionStatus.TRIAL,
    )
    db.add(subscription)
    db.flush()
    return subscription


def get_current_subscription(db: Session, *, clinic_id: str) -> ClinicSubscription | None:
    """The one *current* (trial|active) subscription row per the partial
    unique index on `clinic_id` (DATA_MODEL.md §8)."""
    return (
        db.execute(
            select(ClinicSubscription)
            .where(
                ClinicSubscription.clinic_id == clinic_id,
                ClinicSubscription.status.in_(_CURRENT_STATUSES),
            )
            .order_by(ClinicSubscription.started_at.desc())
        )
        .scalars()
        .first()
    )


def get_entitlements(db: Session, *, clinic_id: str) -> Entitlements:
    """Resolve the effective entitlement set for a clinic.

    No current subscription (e.g. expired with no renewal yet) fails CLOSED
    to the most restrictive entitlement set — this is a read-side business
    gate, not an authorization check, so it degrades rather than raises.
    """
    subscription = get_current_subscription(db, clinic_id=clinic_id)
    if subscription is None:
        return Entitlements(
            max_branches=0,
            max_doctors=0,
            max_active_patients=0,
            copilot_quota_per_month=0,
            crm_automation_enabled=False,
            advanced_reports_enabled=False,
            api_sso_enabled=False,
        )
    plan = db.get(SubscriptionPlan, subscription.plan_id)
    ent = plan.entitlements if plan else {}
    return Entitlements(
        max_branches=ent.get("max_branches", 0),
        max_doctors=ent.get("max_doctors", 0),
        max_active_patients=ent.get("max_active_patients", 0),
        copilot_quota_per_month=ent.get("copilot_quota_per_month", 0),
        crm_automation_enabled=ent.get("crm_automation_enabled", False),
        advanced_reports_enabled=ent.get("advanced_reports_enabled", False),
        api_sso_enabled=ent.get("api_sso_enabled", False),
    )
