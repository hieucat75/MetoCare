"""T25 — Admin User Management API tests.

Covers:
  GET    /admin/users                     — list users
  GET    /admin/users/{user_id}           — get user detail
  PATCH  /admin/users/{user_id}/role      — update role (SUPER_ADMIN only)
  DELETE /admin/users/{user_id}           — deactivate user
  GET    /admin/users/{user_id}/audit-log — per-user audit log

RBAC matrix:
  - INTERNAL_ADMIN: can list/get/deactivate, cannot update role
  - SUPER_ADMIN: full access
  - DOCTOR / PATIENT / AI_SERVICE: 403 on all user endpoints
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
def super_admin(db):
    """Seed a SUPER_ADMIN user; returns auth dict."""
    user = User(
        email=f"sa-t25-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="Super Admin T25",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="super_admin", mfa=True)
    return {
        "user_id": user.id,
        "user": user,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def internal_admin(db):
    """Seed an INTERNAL_ADMIN user; returns auth dict."""
    user = User(
        email=f"ia-t25-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="Internal Admin T25",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="internal_admin", mfa=True)
    return {
        "user_id": user.id,
        "user": user,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def regular_user(db):
    """Seed a regular PATIENT user to act on."""
    user = User(
        email=f"patient-t25-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Test Patient T25",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="patient")
    return {
        "user_id": user.id,
        "user": user,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def doctor_user(db):
    """Seed a DOCTOR user."""
    user = User(
        email=f"doctor-t25-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor")
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def ai_service_user(db):
    """Seed an AI_SERVICE account."""
    user = User(
        email=f"ai-t25-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.AI_SERVICE,
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="ai_service")
    return {
        "user_id": user.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


# ---------------------------------------------------------------------------
# Test 1 — SUPER_ADMIN can list users → 200, list
# ---------------------------------------------------------------------------


def test_super_admin_lists_users(client, super_admin):
    """SUPER_ADMIN can list all users; response is a list."""
    r = client.get("/api/v1/admin/users", headers=super_admin["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)


# ---------------------------------------------------------------------------
# Test 2 — INTERNAL_ADMIN can list users → 200 (allowed)
# ---------------------------------------------------------------------------


def test_internal_admin_lists_users(client, internal_admin):
    """INTERNAL_ADMIN can also list users."""
    r = client.get("/api/v1/admin/users", headers=internal_admin["headers"])
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Test 3 — DOCTOR cannot list users → 403
# ---------------------------------------------------------------------------


def test_doctor_cannot_list_users(client, doctor_user):
    """DOCTOR token → 403 on GET /admin/users."""
    r = client.get("/api/v1/admin/users", headers=doctor_user["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# Test 4 — PATIENT cannot list users → 403
# ---------------------------------------------------------------------------


def test_patient_cannot_list_users(client, regular_user):
    """PATIENT token → 403 on GET /admin/users."""
    r = client.get("/api/v1/admin/users", headers=regular_user["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# Test 5 — SUPER_ADMIN gets user detail → 200
# ---------------------------------------------------------------------------


def test_super_admin_gets_user_detail(client, super_admin, regular_user):
    """SUPER_ADMIN can fetch a specific user by id."""
    uid = regular_user["user_id"]
    r = client.get(f"/api/v1/admin/users/{uid}", headers=super_admin["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == uid
    assert "email" in body
    assert "role" in body
    assert "is_active" in body


# ---------------------------------------------------------------------------
# Test 6 — SUPER_ADMIN updates user role → 200, new role reflected
# ---------------------------------------------------------------------------


def test_super_admin_updates_user_role(client, super_admin, regular_user):
    """SUPER_ADMIN can change a user's role."""
    uid = regular_user["user_id"]
    r = client.patch(
        f"/api/v1/admin/users/{uid}/role",
        headers=super_admin["headers"],
        json={"role": "doctor"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "doctor"
    assert body["id"] == uid


# ---------------------------------------------------------------------------
# Test 7 — INTERNAL_ADMIN cannot update role → 403
# ---------------------------------------------------------------------------


def test_internal_admin_cannot_update_role(client, internal_admin, regular_user):
    """INTERNAL_ADMIN does not have permission to change roles."""
    uid = regular_user["user_id"]
    r = client.patch(
        f"/api/v1/admin/users/{uid}/role",
        headers=internal_admin["headers"],
        json={"role": "doctor"},
    )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# Test 8 — SUPER_ADMIN deactivates user → 200, is_active=False
# ---------------------------------------------------------------------------


def test_super_admin_deactivates_user(client, super_admin, regular_user):
    """SUPER_ADMIN can deactivate a non-super-admin user."""
    uid = regular_user["user_id"]
    r = client.delete(f"/api/v1/admin/users/{uid}", headers=super_admin["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_active"] is False
    assert body["id"] == uid


# ---------------------------------------------------------------------------
# Test 9 — SUPER_ADMIN cannot deactivate self → 400
# ---------------------------------------------------------------------------


def test_super_admin_cannot_deactivate_self(client, super_admin):
    """A SUPER_ADMIN cannot soft-delete their own account (→ 400)."""
    uid = super_admin["user_id"]
    r = client.delete(f"/api/v1/admin/users/{uid}", headers=super_admin["headers"])
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# Test 10 — SUPER_ADMIN gets user audit log → 200, list
# ---------------------------------------------------------------------------


def test_super_admin_gets_user_audit_log(client, super_admin, regular_user):
    """SUPER_ADMIN can retrieve the audit log for a specific user."""
    uid = regular_user["user_id"]
    r = client.get(f"/api/v1/admin/users/{uid}/audit-log", headers=super_admin["headers"])
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Test 11 — AI_SERVICE → 403 on all admin endpoints
# ---------------------------------------------------------------------------


def test_ai_service_blocked_on_admin_endpoints(client, ai_service_user, regular_user):
    """AI_SERVICE role must be denied on all admin user endpoints."""
    uid = regular_user["user_id"]
    headers = ai_service_user["headers"]

    endpoints = [
        ("GET", "/api/v1/admin/users"),
        ("GET", f"/api/v1/admin/users/{uid}"),
        ("PATCH", f"/api/v1/admin/users/{uid}/role"),
        ("DELETE", f"/api/v1/admin/users/{uid}"),
        ("GET", f"/api/v1/admin/users/{uid}/audit-log"),
    ]
    for method, path in endpoints:
        r = client.request(method, path, headers=headers, json={"role": "patient"})
        assert r.status_code == 403, f"{method} {path} expected 403, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# Bonus: SUPER_ADMIN cannot deactivate another SUPER_ADMIN → 403
# ---------------------------------------------------------------------------


def test_super_admin_cannot_deactivate_another_super_admin(client, super_admin, db):
    """A SUPER_ADMIN cannot deactivate another SUPER_ADMIN account."""
    other = User(
        email=f"sa2-t25-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
    )
    db.add(other)
    db.commit()

    r = client.delete(f"/api/v1/admin/users/{other.id}", headers=super_admin["headers"])
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# Bonus: Get non-existent user → 404
# ---------------------------------------------------------------------------


def test_get_nonexistent_user_returns_404(client, super_admin):
    """Getting a user that doesn't exist → 404."""
    r = client.get(
        "/api/v1/admin/users/00000000-0000-0000-0000-000000000000",
        headers=super_admin["headers"],
    )
    assert r.status_code == 404, r.text
