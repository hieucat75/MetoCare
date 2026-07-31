"""Test fixtures.

IMPORTANT: configure a throwaway SQLite database and mock modes via env vars
*before* importing the app, so no real infra / provider / PHI is ever touched.
"""

from __future__ import annotations

import os
import tempfile

# Must run before any `app.*` import (engine is built at import time).
_DB_DIR = tempfile.mkdtemp(prefix="mcp_test_")
os.environ["MCP_DATABASE_URL"] = f"sqlite:///{_DB_DIR}/test.sqlite3"
os.environ["MCP_ENV"] = "test"
# Environment-scoped auth relaxation for the test suite (dev/test only; the
# startup guard forbids relaxed auth in staging/production).
os.environ["MCP_PASSWORD_MIN_LENGTH"] = "6"
os.environ["MCP_PASSWORD_REQUIRE_COMPLEXITY"] = "false"
os.environ["MCP_AI_MODE"] = "mock"
os.environ["MCP_OCR_MODE"] = "mock"
# PR-B: the patient-facing AI/OCR feature flags default OFF (no real AI for MVP).
# Tests that exercise those features run with them ON; dedicated tests flip them
# OFF via monkeypatch to assert the 503 fail-closed behaviour.
os.environ["FEATURE_AI_ASSISTANT"] = "true"
os.environ["FEATURE_OCR"] = "true"
os.environ["FEATURE_AI_RECOMMENDATION"] = "true"
# Clinic SaaS Phase C0: default OFF (fail-closed); tests exercising the module
# turn it ON here, dedicated tests flip it OFF via monkeypatch for the 503 check.
os.environ["FEATURE_CLINIC_SAAS"] = "true"
# Drive the OCR pipeline deterministically in tests; the background worker is
# exercised by a dedicated async test, not the shared TestClient app.
os.environ["MCP_OCR_WORKER_ENABLED"] = "false"

import pytest  # noqa: E402
from app.core.database import SessionLocal, create_all  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402
from app.models.patient import PatientProfile  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    create_all()
    _seed_subscription_plans()
    yield


def _seed_subscription_plans() -> None:
    """`create_all()` builds schema only (no data), unlike Alembic in
    production — migration c0_m7_subscription_plan.py seeds the 4 standard
    tiers there. Mirror that seed here so tests exercise the same "trial plan
    always exists" invariant `create_trial_subscription()` depends on."""
    from app.models.clinic import SubscriptionPlan

    session = SessionLocal()
    try:
        if session.query(SubscriptionPlan).count() > 0:
            return
        plans = [
            SubscriptionPlan(
                code="trial",
                name="Dùng thử",
                entitlements={
                    "max_branches": 1,
                    "max_doctors": 2,
                    "max_active_patients": 100,
                    "copilot_quota_per_month": 50,
                    "crm_automation_enabled": False,
                    "advanced_reports_enabled": False,
                    "api_sso_enabled": False,
                },
            ),
            SubscriptionPlan(
                code="basic",
                name="Cơ bản",
                entitlements={
                    "max_branches": 1,
                    "max_doctors": 5,
                    "max_active_patients": 500,
                    "copilot_quota_per_month": 200,
                    "crm_automation_enabled": False,
                    "advanced_reports_enabled": False,
                    "api_sso_enabled": False,
                },
            ),
            SubscriptionPlan(
                code="professional",
                name="Chuyên nghiệp",
                entitlements={
                    "max_branches": 3,
                    "max_doctors": 20,
                    "max_active_patients": 3000,
                    "copilot_quota_per_month": 1000,
                    "crm_automation_enabled": True,
                    "advanced_reports_enabled": True,
                    "api_sso_enabled": False,
                },
            ),
            SubscriptionPlan(
                code="enterprise",
                name="Doanh nghiệp",
                entitlements={
                    "max_branches": 999,
                    "max_doctors": 999,
                    "max_active_patients": 999999,
                    "copilot_quota_per_month": 999999,
                    "crm_automation_enabled": True,
                    "advanced_reports_enabled": True,
                    "api_sso_enabled": True,
                },
            ),
        ]
        session.add_all(plans)
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _default_meto_consent(request, monkeypatch):
    """Grant all Meto consent categories by default so existing pipeline tests run
    without every test having to seed consent. Tests that exercise the real
    fail-closed consent gate opt out with @pytest.mark.real_consent.

    Patches the names as bound in the consuming modules (import-time binding),
    not the definition site.
    """
    if not request.node.get_closest_marker("real_consent"):
        from app.ai.consent_policy import CONSENT_CATEGORIES

        monkeypatch.setattr(
            "app.ai.context.builder.load_granted_categories",
            lambda db, user_id: set(CONSENT_CATEGORIES),
        )
        monkeypatch.setattr(
            "app.services.meto_chat.is_granted",
            lambda db, user_id, category: True,
        )
    yield


@pytest.fixture(autouse=True)
def _reset_ratelimit():
    """Clear rate-limit + lockout state before each test so it never leaks."""
    from app.core.ratelimit import reset_all

    reset_all()
    yield


@pytest.fixture(autouse=True)
def _reset_llm():
    """Drop the LLM gateway + provider singletons so cost-guard/cache state and
    any per-test config override never leak between tests."""
    from app.llm import reset_gateway, reset_provider
    from app.rag import reset_retriever
    from app.services import notifications
    from app.services.lab_pipeline import get_worker

    reset_gateway()
    reset_provider()
    reset_retriever()
    get_worker().reset()
    notifications.reset()
    yield


@pytest.fixture(autouse=True)
def _mdi_registry_defaults():
    """Guarantee the concrete MDI extractors/promoters are registered before every
    test. Individual MDI tests reset the global registries in their own teardown;
    without this, a wiped registry would leak into any later test that exercises a
    real prescription confirm — an order-dependent flake. Restores defaults after
    each test too, so state is deterministic regardless of collection order."""
    from app.services.mdi.bootstrap import register_defaults

    register_defaults()
    yield
    register_defaults()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def patient(db):
    """Seed a synthetic (NOT real) patient + owner user. Returns ids + token."""
    user = User(
        email=f"test-{os.urandom(4).hex()}@example.com",
        password_hash="x",  # fixture mints tokens directly; no password login here
        role=UserRole.PATIENT,
        full_name="Nguyễn Văn Test",
    )
    db.add(user)
    db.flush()
    profile = PatientProfile(user_id=user.id, full_name="Nguyễn Văn Test", waist_cm=95)
    db.add(profile)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "patient_id": profile.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def token_for():
    """Factory: mint a bearer-header dict for an arbitrary user id + role.

    Defaults to an MFA-verified token so role-gated tests aren't blocked by the
    MFA gate; pass mfa=False to exercise the MFA requirement explicitly.
    """

    def _make(user_id: str, role: str = "patient", mfa: bool = True) -> dict[str, str]:
        token = create_access_token(subject=user_id, role=role, mfa=mfa)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mfa_enforced(monkeypatch):
    """Turn MFA enforcement ON for one test (default is OFF — relaxed policy).

    get_settings() is lru_cached, so the cache must be cleared around the env
    override. Teardown clears it again; the next get_settings() call after
    monkeypatch undoes the env var rebuilds the default (enforcement-off)
    settings.
    """
    from app.core.config import get_settings

    monkeypatch.setenv("MCP_MFA_ENFORCEMENT_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
