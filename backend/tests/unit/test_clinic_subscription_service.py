"""Clinic subscription/entitlement service unit tests (Clinic SaaS Phase C0, M04).

Extends `tests/api/test_clinic_saas_api.py`'s API-level subscription smoke
coverage with DB-level invariant tests that have no HTTP surface to drive
them through (the partial unique index is only ever violated by a direct
ORM insert — no route lets a caller create a second "current" subscription
row for the same clinic)."""

from __future__ import annotations

import os

import pytest
from app.models.care import Clinic
from app.models.clinic import ClinicSubscription, ClinicSubscriptionStatus
from app.services.clinic_subscription import (
    create_trial_subscription,
    get_current_subscription,
    get_entitlements,
    get_plan_by_code,
)
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def clinic(db):
    row = Clinic(name=f"Sub-Service-Test-{os.urandom(4).hex()}", status="trial")
    db.add(row)
    db.commit()
    return row


def test_create_trial_subscription_sets_trial_status_and_expiry(db, clinic):
    subscription = create_trial_subscription(db, clinic_id=clinic.id)
    db.commit()

    assert subscription.status == ClinicSubscriptionStatus.TRIAL
    assert subscription.expires_at is not None
    assert subscription.expires_at > subscription.started_at


def test_partial_unique_index_blocks_second_current_subscription(db, clinic):
    """DATA_MODEL.md §8: at most one *current* (trial|active) subscription row
    per clinic. A second ACTIVE row for the same clinic while a TRIAL row is
    still current must violate the partial unique index at commit time."""
    create_trial_subscription(db, clinic_id=clinic.id)
    db.commit()

    plan = get_plan_by_code(db, "basic")
    assert plan is not None

    duplicate = ClinicSubscription(
        clinic_id=clinic.id, plan_id=plan.id, status=ClinicSubscriptionStatus.ACTIVE
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # The original trial row is still the sole current subscription.
    current = get_current_subscription(db, clinic_id=clinic.id)
    assert current is not None
    assert current.status == ClinicSubscriptionStatus.TRIAL


def test_expired_subscription_does_not_violate_unique_index(db, clinic):
    """Historical (expired/cancelled) rows are unconstrained — only
    trial|active rows compete for the partial unique slot."""
    trial = create_trial_subscription(db, clinic_id=clinic.id)
    db.commit()

    trial.status = ClinicSubscriptionStatus.EXPIRED
    db.commit()

    plan = get_plan_by_code(db, "basic")
    renewal = ClinicSubscription(
        clinic_id=clinic.id, plan_id=plan.id, status=ClinicSubscriptionStatus.ACTIVE
    )
    db.add(renewal)
    db.commit()  # must NOT raise — expired row doesn't hold the unique slot

    current = get_current_subscription(db, clinic_id=clinic.id)
    assert current is not None
    assert current.id == renewal.id
    assert current.status == ClinicSubscriptionStatus.ACTIVE


def test_entitlements_fail_closed_when_no_current_subscription(db, clinic):
    """No current subscription (e.g. expired with no renewal) degrades to the
    most restrictive entitlement set rather than raising — a read-side
    business gate, not an authorization check."""
    entitlements = get_entitlements(db, clinic_id=clinic.id)
    assert entitlements.max_branches == 0
    assert entitlements.max_doctors == 0
    assert entitlements.max_active_patients == 0
    assert entitlements.copilot_quota_per_month == 0
    assert entitlements.crm_automation_enabled is False
    assert entitlements.advanced_reports_enabled is False
    assert entitlements.api_sso_enabled is False


def test_entitlements_resolve_from_current_plan(db, clinic):
    create_trial_subscription(db, clinic_id=clinic.id)
    db.commit()
    entitlements = get_entitlements(db, clinic_id=clinic.id)
    assert entitlements.max_branches >= 1
    assert entitlements.max_doctors >= 1
