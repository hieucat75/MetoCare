"""Refresh-token rotation + MFA (TOTP) tests. No external calls."""

from __future__ import annotations

import os

import pyotp


def _register(client, email=None, password="password123", role="patient"):
    email = email or f"mfa-{os.urandom(4).hex()}@example.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "role": role},
    )
    assert r.status_code == 201, r.text
    return email, password, r.json()


# --------------------------------------------------------------------------- #
# Refresh tokens
# --------------------------------------------------------------------------- #


def test_refresh_rotation_chain(client):
    _, _, tok = _register(client)
    t0 = tok["refresh_token"]

    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": t0})
    assert r1.status_code == 200, r1.text
    t1 = r1.json()["refresh_token"]
    assert t1 != t0

    # The newest token continues to rotate cleanly.
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": t1})
    assert r2.status_code == 200
    assert r2.json()["refresh_token"] not in (t0, t1)
    # (Reuse of a rotated token is covered in test_reuse_detection.)


def test_logout_revokes_refresh_token(client):
    _, _, tok = _register(client)
    headers = {"Authorization": f"Bearer {tok['access_token']}"}

    out = client.post(
        "/api/v1/auth/logout",
        headers=headers,
        json={"refresh_token": tok["refresh_token"]},
    )
    assert out.status_code == 200

    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert reuse.status_code == 401


def test_refresh_rejects_garbage(client):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-token"})
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# MFA (TOTP)
# --------------------------------------------------------------------------- #


def _enroll_mfa(client, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    enroll = client.post("/api/v1/auth/mfa/enroll", headers=headers)
    assert enroll.status_code == 200, enroll.text
    body = enroll.json()
    secret = body["secret"]
    code = pyotp.TOTP(secret).now()
    verify = client.post("/api/v1/auth/mfa/verify", headers=headers, json={"totp_code": code})
    assert verify.status_code == 200, verify.text
    return secret, body["backup_codes"]


def test_mfa_enroll_then_login_requires_code(client):
    email, password, tok = _register(client)
    secret, _ = _enroll_mfa(client, tok["access_token"])

    # Login without a code now fails.
    no_code = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert no_code.status_code == 401

    # Login with a valid TOTP succeeds and yields an MFA-verified token.
    code = pyotp.TOTP(secret).now()
    ok = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "totp_code": code},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["mfa"] is True


def test_mfa_backup_code_login(client):
    email, password, tok = _register(client)
    _, backup_codes = _enroll_mfa(client, tok["access_token"])

    backup = backup_codes[0]
    ok = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "backup_code": backup},
    )
    assert ok.status_code == 200
    assert ok.json()["mfa"] is True

    # A backup code is single-use.
    reuse = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "backup_code": backup},
    )
    assert reuse.status_code == 401


def test_invalid_totp_at_verify_rejected(client):
    _, _, tok = _register(client)
    headers = {"Authorization": f"Bearer {tok['access_token']}"}
    client.post("/api/v1/auth/mfa/enroll", headers=headers)
    bad = client.post("/api/v1/auth/mfa/verify", headers=headers, json={"totp_code": "000000"})
    # 000000 is overwhelmingly unlikely to be valid for a fresh secret.
    assert bad.status_code == 400


# --------------------------------------------------------------------------- #
# MFA gate on sensitive (admin) endpoints
# --------------------------------------------------------------------------- #


def test_admin_endpoint_requires_mfa(client, token_for):
    no_mfa = client.get(
        "/api/v1/admin/audit-logs", headers=token_for("u-admin", "internal_admin", mfa=False)
    )
    assert no_mfa.status_code == 403  # MFA required

    with_mfa = client.get(
        "/api/v1/admin/audit-logs", headers=token_for("u-admin", "internal_admin", mfa=True)
    )
    assert with_mfa.status_code == 200
