"""Tests for GET /admin/stats — platform-wide dashboard counts.

Covers:
  - Non-admin (patient / doctor) → 403
  - Unauthenticated → 401
  - INTERNAL_ADMIN + MFA → 200 with all 8 integer fields present
  - SUPER_ADMIN + MFA → 200
"""

from __future__ import annotations

import os

import pytest
from app.core.security import create_access_token
from app.models.user import User, UserRole

STAT_FIELDS = (
    "total_users",
    "active_patients",
    "active_doctors",
    "total_clinics",
    "ai_sessions_today",
    "pending_reviews",
    "flagged_ai_sessions",
    "audit_events_today",
)


@pytest.fixture
def admin_user(db):
    """Seed an INTERNAL_ADMIN user and return auth headers with MFA."""
    user = User(
        email=f"admin-stats-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.INTERNAL_ADMIN,
        full_name="Internal Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="internal_admin", mfa=True)
    return {"headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def super_admin_user(db):
    """Seed a SUPER_ADMIN user and return auth headers with MFA."""
    user = User(
        email=f"superadmin-stats-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
        full_name="Super Admin",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="super_admin", mfa=True)
    return {"headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def doctor_user(db):
    """Seed a DOCTOR user (not authorised for admin stats)."""
    user = User(
        email=f"doctor-stats-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.DOCTOR,
        full_name="Dr. Test",
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id, role="doctor", mfa=True)
    return {"headers": {"Authorization": f"Bearer {token}"}}


def test_admin_reads_stats(client, admin_user):
    """INTERNAL_ADMIN + MFA → 200 with all 8 integer fields present."""
    r = client.get("/api/v1/admin/stats", headers=admin_user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    for field in STAT_FIELDS:
        assert field in body, f"missing field: {field}"
        assert isinstance(body[field], int), f"{field} is not int: {body[field]!r}"


def test_super_admin_reads_stats(client, super_admin_user):
    """SUPER_ADMIN + MFA → 200."""
    r = client.get("/api/v1/admin/stats", headers=super_admin_user["headers"])
    assert r.status_code == 200, r.text
    assert set(STAT_FIELDS).issubset(r.json().keys())


def test_patient_cannot_read_stats(client, patient):
    """PATIENT token → 403."""
    r = client.get("/api/v1/admin/stats", headers=patient["headers"])
    assert r.status_code == 403, r.text


def test_doctor_cannot_read_stats(client, doctor_user):
    """DOCTOR token → 403."""
    r = client.get("/api/v1/admin/stats", headers=doctor_user["headers"])
    assert r.status_code == 403, r.text


def test_unauthenticated_cannot_read_stats(client):
    """No token → 401."""
    r = client.get("/api/v1/admin/stats")
    assert r.status_code == 401, r.text
