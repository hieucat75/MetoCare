"""MFA enforcement policy tests.

Temporary relaxed authentication policy for the build/test phase:
MCP_MFA_ENFORCEMENT_ENABLED defaults to false, so NO role is forced to
enroll MFA and the require_mfa endpoint gates are no-ops. Setting the flag
to true restores the previous mandatory policy for MFA_REQUIRED_ROLES.
Voluntary enrollment (enroll/verify/TOTP login) works in both modes.
"""

from __future__ import annotations

import os

import pyotp
from app.core.security import decode_token
from app.models.user import UserRole
from app.services import auth as auth_service


def _register(db, role: UserRole, prefix: str):
    email = f"{prefix}-{os.urandom(4).hex()}@example.com"
    password = "password123"
    auth_service.register(db, email=email, password=password, role=role)
    return email, password


def _login(client, email: str, password: str):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Default policy (enforcement OFF): no role is forced into MFA
# ---------------------------------------------------------------------------


def test_no_role_is_forced_to_enroll_by_default(client, db):
    for role, prefix in [
        (UserRole.DOCTOR, "doc"),
        (UserRole.INTERNAL_ADMIN, "iadm"),
        (UserRole.SUPER_ADMIN, "sadm"),
        (UserRole.CLINIC_ADMIN, "cadm"),
        (UserRole.MEDICAL_REVIEWER, "rev"),
    ]:
        email, password = _register(db, role, prefix)
        body = _login(client, email, password)
        claims = decode_token(body["access_token"]) or {}
        assert not claims.get("mfa_enrollment_required"), role
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200


def test_admin_reaches_admin_endpoint_without_mfa_by_default(client, db):
    email, password = _register(db, UserRole.INTERNAL_ADMIN, "adm")
    body = _login(client, email, password)
    assert body["mfa"] is False
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/api/v1/admin/stats", headers=headers).status_code == 200


def test_doctor_reaches_protected_endpoint_without_mfa(client, db):
    email, password = _register(db, UserRole.DOCTOR, "doc")
    body = _login(client, email, password)
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    ok = client.post("/api/v1/ai/triage", json={"symptom_text": "khỏe"}, headers=headers)
    assert ok.status_code == 200


# ---------------------------------------------------------------------------
# Voluntary MFA stays fully functional while enforcement is off
# ---------------------------------------------------------------------------


def test_voluntary_enrollment_and_totp_login_still_work(client, db):
    email, password = _register(db, UserRole.DOCTOR, "vol")
    body = _login(client, email, password)
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    enroll = client.post("/api/v1/auth/mfa/enroll", headers=headers)
    assert enroll.status_code == 200
    secret = enroll.json()["secret"]
    verify = client.post(
        "/api/v1/auth/mfa/verify", headers=headers, json={"totp_code": pyotp.TOTP(secret).now()}
    )
    assert verify.status_code == 200

    # Once enrolled, login REQUIRES the TOTP code (this is authentication of
    # an enrolled account, not policy enforcement).
    no_code = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert no_code.status_code == 401
    with_code = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "totp_code": pyotp.TOTP(secret).now()},
    )
    assert with_code.status_code == 200
    assert with_code.json()["mfa"] is True


# ---------------------------------------------------------------------------
# Enforcement ON (MCP_MFA_ENFORCEMENT_ENABLED=true): previous policy returns
# ---------------------------------------------------------------------------


def test_flag_on_internal_admin_blocked_until_mfa_enrolled(client, db, mfa_enforced):
    email, password = _register(db, UserRole.INTERNAL_ADMIN, "eadm")

    body = _login(client, email, password)
    headers = {"Authorization": f"Bearer {body['access_token']}"}

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

    relogin = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "totp_code": pyotp.TOTP(secret).now()},
    )
    assert relogin.status_code == 200
    new_headers = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
    assert client.get("/api/v1/admin/stats", headers=new_headers).status_code == 200


def test_flag_on_require_mfa_gate_rejects_unverified_admin_session(client, db):
    # Register + login while enforcement is OFF (token carries mfa=False and
    # no enrollment claim), then flip the flag ON mid-test: the require_mfa
    # gate must reject the session.
    from app.core.config import get_settings

    email, password = _register(db, UserRole.INTERNAL_ADMIN, "gadm")
    body = _login(client, email, password)
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    import os as _os

    _os.environ["MCP_MFA_ENFORCEMENT_ENABLED"] = "true"
    get_settings.cache_clear()
    try:
        r = client.get("/api/v1/admin/stats", headers=headers)
        assert r.status_code == 403
    finally:
        _os.environ.pop("MCP_MFA_ENFORCEMENT_ENABLED", None)
        get_settings.cache_clear()


def test_flag_on_doctor_still_not_forced(client, db, mfa_enforced):
    # Doctors stay exempt from forced enrollment even when enforcement is on
    # (sales-led onboarding decision, PR #86).
    email, password = _register(db, UserRole.DOCTOR, "edoc")
    body = _login(client, email, password)
    claims = decode_token(body["access_token"]) or {}
    assert not claims.get("mfa_enrollment_required")
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    ok = client.post("/api/v1/ai/triage", json={"symptom_text": "khỏe"}, headers=headers)
    assert ok.status_code == 200


def test_patient_not_forced_to_enroll(client):
    email = f"pat-{os.urandom(4).hex()}@example.com"
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    ok = client.post("/api/v1/ai/triage", json={"symptom_text": "khỏe"}, headers=headers)
    assert ok.status_code == 200
