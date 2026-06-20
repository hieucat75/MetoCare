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


# ---------------------------------------------------------------------------
# PR-F — change password, account update (email + notification prefs)
# ---------------------------------------------------------------------------


def _auth_headers(client, email):
    body = _register(client, email).json()
    return {"Authorization": f"Bearer {body['access_token']}"}


def test_change_password_success_and_relogin(client):
    h = _auth_headers(client, "cp-ok@example.com")
    r = client.post(
        "/api/v1/auth/change-password",
        headers=h,
        json={"current_password": "password123", "new_password": "newpass456"},
    )
    assert r.status_code == 200, r.text
    # Old password no longer works; new one does.
    old = client.post(
        "/api/v1/auth/login",
        json={"email": "cp-ok@example.com", "password": "password123"},
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/login",
        json={"email": "cp-ok@example.com", "password": "newpass456"},
    )
    assert new.status_code == 200, new.text


def test_change_password_wrong_current_rejected(client):
    h = _auth_headers(client, "cp-bad@example.com")
    r = client.post(
        "/api/v1/auth/change-password",
        headers=h,
        json={"current_password": "wrongpass", "new_password": "newpass456"},
    )
    assert r.status_code == 400, r.text


def test_update_account_notification_prefs(client):
    h = _auth_headers(client, "acct-prefs@example.com")
    # defaults are all True
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["notify_medication"] is True
    r = client.patch(
        "/api/v1/auth/account",
        headers=h,
        json={"notify_medication": False, "notify_lab_results": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["notify_medication"] is False
    assert body["notify_lab_results"] is False
    assert body["notify_doctor_messages"] is True  # untouched
    # persisted
    me2 = client.get("/api/v1/auth/me", headers=h).json()
    assert me2["notify_medication"] is False


def test_update_account_email_change(client):
    h = _auth_headers(client, "acct-email@example.com")
    r = client.patch(
        "/api/v1/auth/account", headers=h, json={"email": "acct-email-new@example.com"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "acct-email-new@example.com"


def test_update_account_duplicate_email_rejected(client):
    _register(client, "taken@example.com")
    h = _auth_headers(client, "acct-dup@example.com")
    r = client.patch("/api/v1/auth/account", headers=h, json={"email": "taken@example.com"})
    assert r.status_code == 409, r.text


# ---------------------------------------------------------------------------
# Patient phone-based registration + login (and no admin/doctor regression)
# ---------------------------------------------------------------------------


def _register_phone(client, phone, password="password123", full_name="Phone User"):
    return client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "password": password, "full_name": full_name},
    )


def test_patient_phone_register_and_login(client):
    """Register with a local VN number; login with a differently-formatted one
    (both normalize to the same +84 row)."""
    r = _register_phone(client, "0901234567")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "patient"

    # /me shows phone (normalized) + null email
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200, me.text
    assert me.json()["phone"] == "+84901234567"
    assert me.json()["email"] is None
    assert me.json()["patient_profile_id"]  # patient profile auto-created

    # login with +84 / spaced format → same account
    li = client.post(
        "/api/v1/auth/login",
        json={"phone": "+84 901 234 567", "password": "password123"},
    )
    assert li.status_code == 200, li.text
    assert li.json()["role"] == "patient"


def test_phone_register_rejects_invalid_number(client):
    r = _register_phone(client, "012345")  # not a valid VN mobile
    assert r.status_code == 422, r.text


def test_phone_register_duplicate_rejected(client):
    assert _register_phone(client, "0912345678").status_code == 201
    # same number, different local format → 409 (normalized collision)
    dup = _register_phone(client, "+84912345678")
    assert dup.status_code == 409, dup.text


def test_register_requires_exactly_one_identifier(client):
    # neither
    r0 = client.post("/api/v1/auth/register", json={"password": "password123"})
    assert r0.status_code == 422, r0.text
    # both
    r2 = client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "phone": "0901234567", "password": "password123"},
    )
    assert r2.status_code == 422, r2.text


def test_admin_email_login_still_works(client, db):
    """Regression: an email-based (non-patient) account still logs in by email."""
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    admin = User(
        email="admin-regress@example.com",
        password_hash=hash_password("password123"),
        role=UserRole.INTERNAL_ADMIN,
        full_name="Admin",
    )
    db.add(admin)
    db.commit()

    li = client.post(
        "/api/v1/auth/login",
        json={"email": "admin-regress@example.com", "password": "password123"},
    )
    assert li.status_code == 200, li.text
    assert li.json()["role"] == "internal_admin"


def test_wrong_phone_password_401(client):
    _register_phone(client, "0987654321")
    bad = client.post("/api/v1/auth/login", json={"phone": "0987654321", "password": "wrong"})
    assert bad.status_code == 401, bad.text
