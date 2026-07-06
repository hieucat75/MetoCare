"""Regression tests: Fernet ciphertext must never leak through user-facing APIs.

Staging bug (2026-07-06): a super-admin row held an undecryptable Fernet token
in `full_name` (double-encrypted by the PHI migration job after being written
with a foreign key). `EncryptedString`'s legacy-plaintext tolerance returned
the raw token, and the admin sidebar rendered "gAAAA…" verbatim.

Covers:
  - is_fernet_token shape detection
  - ORM read unwraps double-encrypted values back to plaintext
  - ORM read returns None (not ciphertext) for foreign-key tokens
  - /auth/me and /admin/users never expose gAAAA… values
  - accounts with no full_name still serialize cleanly (null, not error)
"""

from __future__ import annotations

import os

import pytest
from app.core import crypto
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.schemas.auth import UserOut
from cryptography.fernet import Fernet
from sqlalchemy import text


def _seed_user(db, *, full_name: str | None, role: UserRole = UserRole.SUPER_ADMIN) -> User:
    user = User(
        email=f"phi-leak-{os.urandom(4).hex()}@metocare.internal",
        password_hash="x",
        role=role,
        full_name=full_name,
    )
    db.add(user)
    db.commit()
    return user


def _set_raw_full_name(db, user_id: str, raw_value: str) -> None:
    """Write a raw column value, bypassing the ORM's transparent encryption."""
    db.execute(
        text("UPDATE users SET full_name = :v WHERE id = :id"),
        {"v": raw_value, "id": user_id},
    )
    db.commit()


def _foreign_ciphertext(plaintext: str = "Pham Trung Hieu") -> str:
    """A Fernet token encrypted with a key the app does NOT have."""
    return Fernet(Fernet.generate_key()).encrypt(plaintext.encode()).decode()


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=user.id, role=user.role.value, mfa=True)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# is_fernet_token
# ---------------------------------------------------------------------------


def test_is_fernet_token_matches_real_tokens():
    assert crypto.is_fernet_token(crypto.encrypt("any value"))
    assert crypto.is_fernet_token(_foreign_ciphertext())


@pytest.mark.parametrize(
    "value",
    [None, "", "Nguyễn Văn A", "gAAAA", "gAAAA-too-short", "admin@example.com"],
)
def test_is_fernet_token_rejects_plaintext(value):
    assert not crypto.is_fernet_token(value)


# ---------------------------------------------------------------------------
# EncryptedString read behaviour
# ---------------------------------------------------------------------------


def test_orm_read_unwraps_double_encrypted_value(db):
    user = _seed_user(db, full_name="placeholder")
    # Simulate the staging corruption: ciphertext encrypted a second time.
    _set_raw_full_name(db, user.id, crypto.encrypt(crypto.encrypt("Pham Trung Hieu")))

    db.expire_all()
    assert db.get(User, user.id).full_name == "Pham Trung Hieu"


def test_orm_read_never_returns_foreign_ciphertext(db):
    user = _seed_user(db, full_name="placeholder")
    _set_raw_full_name(db, user.id, _foreign_ciphertext())

    db.expire_all()
    assert db.get(User, user.id).full_name is None


def test_orm_read_still_tolerates_legacy_plaintext(db):
    user = _seed_user(db, full_name="placeholder")
    _set_raw_full_name(db, user.id, "Legacy Plaintext Name")

    db.expire_all()
    assert db.get(User, user.id).full_name == "Legacy Plaintext Name"


# ---------------------------------------------------------------------------
# Serialization layer (defense in depth)
# ---------------------------------------------------------------------------


def test_userout_validator_strips_ciphertext():
    out = UserOut(id="u1", role="super_admin", full_name=crypto.encrypt("x"))
    assert out.full_name is None


def test_auth_me_with_missing_full_name_returns_null(client, db):
    user = _seed_user(db, full_name=None)
    r = client.get("/api/v1/auth/me", headers=_auth_headers(user))
    assert r.status_code == 200
    assert r.json()["full_name"] is None


def test_auth_me_never_returns_ciphertext(client, db):
    user = _seed_user(db, full_name="placeholder")
    _set_raw_full_name(db, user.id, _foreign_ciphertext())

    r = client.get("/api/v1/auth/me", headers=_auth_headers(user))
    assert r.status_code == 200
    full_name = r.json()["full_name"]
    assert full_name is None or not full_name.startswith("gAAAA")


def test_admin_users_list_never_returns_ciphertext(client, db):
    admin = _seed_user(db, full_name="Quản trị viên", role=UserRole.INTERNAL_ADMIN)
    corrupt = _seed_user(db, full_name="placeholder")
    _set_raw_full_name(db, corrupt.id, _foreign_ciphertext())

    r = client.get("/api/v1/admin/users?limit=200", headers=_auth_headers(admin))
    assert r.status_code == 200
    rows = r.json()
    corrupt_row = next(row for row in rows if row["id"] == corrupt.id)
    assert corrupt_row["full_name"] is None
    for row in rows:
        assert not (row["full_name"] or "").startswith("gAAAA")
