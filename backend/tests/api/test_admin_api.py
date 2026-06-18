"""T17 — Admin API tests.

Covers:
  GET  /admin/audit-logs     — requires INTERNAL_ADMIN or SUPER_ADMIN + MFA
  POST /admin/unlock-account — requires INTERNAL_ADMIN or SUPER_ADMIN + MFA

Token strategy:
  - Admin tokens are minted with ``mfa=True`` so they pass the ``require_mfa``
    dependency.
  - Non-admin tokens (patient / doctor) do NOT have the admin role → 403.
  - Missing / invalid token → 401.
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(db):
    """Seed an INTERNAL_ADMIN user and return auth headers with MFA."""
    user = User(
        email=f"admin-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="Internal Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="internal_admin", mfa=True)
    return {
        "user_id": user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def super_admin_user(db):
    """Seed a SUPER_ADMIN user and return auth headers with MFA."""
    user = User(
        email=f"superadmin-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="Super Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="super_admin", mfa=True)
    return {
        "user_id": user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def doctor_user(db):
    """Seed a DOCTOR user."""
    user = User(
        email=f"doctor-admin-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Test",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {
        "user_id": user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


# ---------------------------------------------------------------------------
# GET /admin/audit-logs tests
# ---------------------------------------------------------------------------


def test_admin_reads_audit_logs(client, admin_user):
    """INTERNAL_ADMIN + MFA token → 200, returns a list."""
    r = client.get("/api/v1/admin/audit-logs", headers=admin_user["headers"])
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_super_admin_reads_audit_logs(client, super_admin_user):
    """SUPER_ADMIN + MFA token → 200, returns a list."""
    r = client.get("/api/v1/admin/audit-logs", headers=super_admin_user["headers"])
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_patient_cannot_read_audit_logs(client, patient):
    """PATIENT token → 403."""
    r = client.get("/api/v1/admin/audit-logs", headers=patient["headers"])
    assert r.status_code == 403, r.text


def test_doctor_cannot_read_audit_logs(client, doctor_user):
    """DOCTOR token → 403."""
    r = client.get("/api/v1/admin/audit-logs", headers=doctor_user["headers"])
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_read_audit_logs(client):
    """No token → 401."""
    r = client.get("/api/v1/admin/audit-logs")
    assert r.status_code == 401, r.text


def test_audit_log_limit_param(client, admin_user):
    """limit query param is accepted; response is a list (may be empty)."""
    r = client.get("/api/v1/admin/audit-logs?limit=5", headers=admin_user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) <= 5


# ---------------------------------------------------------------------------
# POST /admin/unlock-account tests
# ---------------------------------------------------------------------------


def test_admin_unlocks_account(client, admin_user):
    """INTERNAL_ADMIN + MFA → 200, message='account unlocked'."""
    r = client.post(
        "/api/v1/admin/unlock-account",
        headers=admin_user["headers"],
        json={"email": "victim@example.com"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "account unlocked"


def test_patient_cannot_unlock_account(client, patient):
    """PATIENT token → 403."""
    r = client.post(
        "/api/v1/admin/unlock-account",
        headers=patient["headers"],
        json={"email": "victim@example.com"},
    )
    assert r.status_code == 403, r.text


def test_doctor_cannot_unlock_account(client, doctor_user):
    """DOCTOR token → 403."""
    r = client.post(
        "/api/v1/admin/unlock-account",
        headers=doctor_user["headers"],
        json={"email": "victim@example.com"},
    )
    assert r.status_code == 403, r.text


def test_unlock_nonexistent_account_succeeds(client, admin_user):
    """Unlocking an unknown email is idempotent → 200, message='account unlocked'."""
    r = client.post(
        "/api/v1/admin/unlock-account",
        headers=admin_user["headers"],
        json={"email": "nobody-ever-registered@example.com"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "account unlocked"


def test_unauthenticated_cannot_unlock_account(client):
    """No token → 401."""
    r = client.post(
        "/api/v1/admin/unlock-account",
        json={"email": "victim@example.com"},
    )
    assert r.status_code == 401, r.text
