"""Auth + RBAC tests (JWT, Argon2, role gate)."""

from __future__ import annotations

from app.core.security import create_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("s3cret-pass")
    assert h != "s3cret-pass"
    assert h.startswith("$argon2")
    assert verify_password("s3cret-pass", h) is True
    assert verify_password("wrong", h) is False


def _register(client, email, password="password123", role="patient"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test", "role": role},
    )


def test_register_login_me_flow(client):
    r = _register(client, "flow@example.com")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "patient"
    token = body["access_token"]

    # duplicate registration is rejected
    assert _register(client, "flow@example.com").status_code == 409

    # login returns a token
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "flow@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["user_id"] == body["user_id"]

    # bad password rejected
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": "flow@example.com", "password": "nope"},
    )
    assert bad.status_code == 401

    # /me with the token
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "flow@example.com"


def test_public_registration_cannot_self_elevate(client):
    # Requesting role=internal_admin via public endpoint is downgraded to patient.
    r = _register(client, "wannabe-admin@example.com", role="internal_admin")
    assert r.status_code == 201
    assert r.json()["role"] == "patient"


def test_me_requires_valid_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401  # no token
    bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


def test_rbac_patient_cannot_access_admin_endpoint(client, token_for):
    r = client.get("/api/v1/admin/audit-logs", headers=token_for("u-patient", "patient"))
    assert r.status_code == 403


def test_rbac_admin_can_access_admin_endpoint(client, token_for):
    r = client.get("/api/v1/admin/audit-logs", headers=token_for("u-admin", "internal_admin"))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_expired_token_rejected(client):
    expired = create_access_token(subject="u1", role="patient", expires_minutes=-1)
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
