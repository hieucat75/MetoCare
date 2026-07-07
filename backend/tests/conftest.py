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
os.environ["MCP_AI_MODE"] = "mock"
os.environ["MCP_OCR_MODE"] = "mock"
# PR-B: the patient-facing AI/OCR feature flags default OFF (no real AI for MVP).
# Tests that exercise those features run with them ON; dedicated tests flip them
# OFF via monkeypatch to assert the 503 fail-closed behaviour.
os.environ["FEATURE_AI_ASSISTANT"] = "true"
os.environ["FEATURE_OCR"] = "true"
os.environ["FEATURE_AI_RECOMMENDATION"] = "true"
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
