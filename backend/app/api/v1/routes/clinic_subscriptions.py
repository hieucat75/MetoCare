"""Subscription plan catalog + clinic subscription/entitlements read routes
(Clinic SaaS Phase C0, M04). No real billing/payment integration — read-side
entitlement gating only, per the explicit C0 scope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.api.deps_clinic_saas import require_clinic_saas_enabled
from app.api.deps_tenant import TenantContext, get_tenant_context
from app.core.rbac import assert_path_clinic_matches_tenant, require_clinic_roles
from app.models.clinic import ClinicRole, SubscriptionPlan
from app.schemas.clinic_subscription import (
    ClinicSubscriptionDetailOut,
    ClinicSubscriptionOut,
    EntitlementsOut,
    SubscriptionPlanOut,
)
from app.services import clinic_subscription as subscription_service

router = APIRouter(
    tags=["clinic_subscriptions"], dependencies=[Depends(require_clinic_saas_enabled)]
)

# RBAC_MATRIX.md M04: Owner full, Admin/Accountant read-only.
_READ_ROLES = (ClinicRole.OWNER, ClinicRole.ADMIN, ClinicRole.ACCOUNTANT)


@router.get("/subscription-plans", response_model=list[SubscriptionPlanOut])
def list_subscription_plans(
    _user: CurrentUser = Depends(current_user), db: Session = Depends(get_session)
) -> list[SubscriptionPlanOut]:
    """Read-only plan catalog for any authenticated user — no clinic scope
    needed, this is a platform-wide, not clinic-owned, resource."""
    plans = subscription_service.list_plans(db)
    return [SubscriptionPlanOut.model_validate(p) for p in plans]


@router.get(
    "/clinics/{clinic_id}/subscription",
    response_model=ClinicSubscriptionDetailOut,
)
def get_clinic_subscription(
    clinic_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicSubscriptionDetailOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_READ_ROLES)
    subscription = subscription_service.get_current_subscription(db, clinic_id=clinic_id)
    plan = db.get(SubscriptionPlan, subscription.plan_id) if subscription else None
    entitlements = subscription_service.get_entitlements(db, clinic_id=clinic_id)
    return ClinicSubscriptionDetailOut(
        subscription=(
            ClinicSubscriptionOut.model_validate(subscription) if subscription else None
        ),
        plan=SubscriptionPlanOut.model_validate(plan) if plan else None,
        entitlements=EntitlementsOut(**entitlements.__dict__),
    )
