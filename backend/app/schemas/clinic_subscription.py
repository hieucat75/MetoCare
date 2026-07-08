"""Subscription plan + clinic subscription / entitlements schemas
(Clinic SaaS Phase C0, M04). Read-only surface — no real billing integration.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class SubscriptionPlanOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    code: str
    name: str
    entitlements: dict


class ClinicSubscriptionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    clinic_id: str
    plan_id: str
    started_at: dt.datetime
    expires_at: dt.datetime | None
    status: str


class EntitlementsOut(BaseModel):
    max_branches: int
    max_doctors: int
    max_active_patients: int
    copilot_quota_per_month: int
    crm_automation_enabled: bool
    advanced_reports_enabled: bool
    api_sso_enabled: bool


class ClinicSubscriptionDetailOut(BaseModel):
    subscription: ClinicSubscriptionOut | None
    plan: SubscriptionPlanOut | None
    entitlements: EntitlementsOut
