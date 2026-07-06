"""Forced MFA enrollment for privileged roles (admin) — doctors are exempt."""

from __future__ import annotations

import os

import pyotp
from app.models.user import UserRole
from app.services import auth as auth_service


def _register(db, role: UserRole, prefix: str):
    email = f"{prefix}-{os.urandom(4).hex()}@example.com"
    password = "password123"
    auth_service.register(db, email=email, password=password, role=role)
    return email, password


def test_doctor_not_forced_to_enroll(client, db):
    # Mandatory doctor MFA was dropped for sales-led onboarding: a fresh
    # doctor logs in and reaches protected endpoints immediately.
    email, password = _register(db, UserRole.DOCTOR, "doc")

    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    ok = client.post("/api/v1/ai/triage", json={"symptom_text": "khỏe"}, headers=headers)
    assert ok.status_code == 200

    # Voluntary enrollment still works for doctors who want MFA.
    enroll = client.post("/api/v1/auth/mfa/enroll", headers=headers)
    assert enroll.status_code == 200
    secret = enroll.json()["secret"]
    verify = client.post(
        "/api/v1/auth/mfa/verify", headers=headers, json={"totp_code": pyotp.TOTP(secret).now()}
    )
    assert verify.status_code == 200


def test_internal_admin_blocked_until_mfa_enrolled(client, db):
    email, password = _register(db, UserRole.INTERNAL_ADMIN, "adm")

    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Any non-allowlisted endpoint is blocked while enrollment is owed.
    blocked = client.post("/api/v1/ai/triage", json={"symptom_text": "khỏe"}, headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "mfa_enrollment_required"

    # Allowlisted endpoints still work (so the user CAN enroll).
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    enroll = client.post("/api/v1/auth/mfa/enroll", headers=headers)
    assert enroll.status_code == 200
    secret = enroll.json()["secret"]
    verify = client.post(
        "/api/v1/auth/mfa/verify", headers=headers, json={"totp_code": pyotp.TOTP(secret).now()}
    )
    assert verify.status_code == 200

    # Re-login with MFA -> token no longer requires enrollment.
    relogin = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "totp_code": pyotp.TOTP(secret).now()},
    )
    assert relogin.status_code == 200
    new_headers = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
    assert client.get("/api/v1/admin/stats", headers=new_headers).status_code == 200


def test_patient_not_forced_to_enroll(client):
    email = f"pat-{os.urandom(4).hex()}@example.com"
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    # Patient reaches a normal endpoint without enrolling MFA.
    ok = client.post("/api/v1/ai/triage", json={"symptom_text": "khỏe"}, headers=headers)
    assert ok.status_code == 200
