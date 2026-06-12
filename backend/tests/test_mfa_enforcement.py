"""Forced MFA enrollment for privileged roles (doctor/admin)."""

from __future__ import annotations

import os

import pyotp
from app.models.user import UserRole
from app.services import auth as auth_service


def _make_doctor(db):
    email = f"doc-{os.urandom(4).hex()}@example.com"
    password = "password123"
    auth_service.register(db, email=email, password=password, role=UserRole.DOCTOR)
    return email, password


def test_doctor_blocked_until_mfa_enrolled(client, db):
    email, password = _make_doctor(db)

    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    body = login.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    # A protected/other endpoint is blocked while enrollment is owed.
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

    ok = client.post("/api/v1/ai/triage", json={"symptom_text": "khỏe"}, headers=new_headers)
    assert ok.status_code == 200


def test_patient_not_forced_to_enroll(client):
    email = f"pat-{os.urandom(4).hex()}@example.com"
    reg = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    # Patient reaches a normal endpoint without enrolling MFA.
    ok = client.post("/api/v1/ai/triage", json={"symptom_text": "khỏe"}, headers=headers)
    assert ok.status_code == 200
