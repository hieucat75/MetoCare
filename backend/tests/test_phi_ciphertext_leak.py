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
from app.core.crypto import UndecryptablePHIError
from app.core.security import create_access_token
from app.models.consultation import ConsultationNote
from app.models.user import User, UserRole
from app.schemas.auth import UserOut
from app.services import consultation as consultation_svc
from app.services import consultation_note, consultation_payment
from cryptography.fernet import Fernet
from sqlalchemy import text

from tests.consultation_factories import create_doctor, create_patient


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


# ---------------------------------------------------------------------------
# Nested-decryption max depth (finding 7)
# ---------------------------------------------------------------------------


def test_decrypt_recovers_plaintext_at_max_depth_boundary(db):
    """Encrypting exactly _MAX_DECRYPT_DEPTH times must still fully unwrap."""
    user = _seed_user(db, full_name="placeholder")
    wrapped = "Nguyễn Văn Sâu"
    for _ in range(crypto._MAX_DECRYPT_DEPTH):
        wrapped = crypto.encrypt(wrapped)
    _set_raw_full_name(db, user.id, wrapped)

    db.expire_all()
    assert db.get(User, user.id).full_name == "Nguyễn Văn Sâu"


def test_decrypt_beyond_max_depth_returns_none_not_ciphertext(db):
    """Wrapping one layer past the bound must fail safe to None — never
    surface the still-encrypted token to the caller."""
    user = _seed_user(db, full_name="placeholder")
    wrapped = "Nguyễn Văn Sâu Quá Mức"
    for _ in range(crypto._MAX_DECRYPT_DEPTH + 1):
        wrapped = crypto.encrypt(wrapped)
    _set_raw_full_name(db, user.id, wrapped)

    db.expire_all()
    result = db.get(User, user.id).full_name
    assert result is None
    assert result != "Nguyễn Văn Sâu Quá Mức"


# ---------------------------------------------------------------------------
# Logs must never contain plaintext/ciphertext (finding 5 + 7)
# ---------------------------------------------------------------------------


def test_undecryptable_ciphertext_log_never_includes_the_value(db, caplog):
    user = _seed_user(db, full_name="placeholder")
    token = _foreign_ciphertext("Thông tin nhạy cảm không được lộ")
    _set_raw_full_name(db, user.id, token)

    db.expire_all()
    with caplog.at_level("WARNING", logger="app.core.crypto"):
        assert db.get(User, user.id).full_name is None

    log_text = "\n".join(r.message for r in caplog.records)
    assert token not in log_text
    assert "Thông tin nhạy cảm" not in log_text


# ---------------------------------------------------------------------------
# on_decrypt_failure="raise" for required (non-nullable) PHI fields
# ---------------------------------------------------------------------------


def _seed_corrupted_note(db) -> tuple:
    doctor = create_doctor(db)
    _user, profile = create_patient(db)
    c = consultation_svc.create_consultation(
        db, patient_id=profile.id, doctor_id=doctor.id, data_consent_accepted=True
    )
    consultation_payment.pay_mock(db, c, patient_profile_id=profile.id)
    note = consultation_note.add_note(
        db, consultation_id=c.id, doctor_user_id=doctor.user_id, content="Uống thuốc đều"
    )
    db.execute(
        text("UPDATE consultation_notes SET content = :v WHERE id = :i"),
        {"v": _foreign_ciphertext("nội dung nhạy cảm"), "i": note.id},
    )
    db.commit()
    return doctor, c, note


def test_required_field_raises_instead_of_returning_none(db):
    """ConsultationNote.content is non-nullable and on_decrypt_failure='raise'
    — undecryptable ciphertext must raise, never silently become None (which
    would violate the NOT NULL contract on the `str` field)."""
    _doctor, _c, note = _seed_corrupted_note(db)

    db.expire_all()
    with pytest.raises(UndecryptablePHIError):
        _ = db.get(ConsultationNote, note.id).content


def test_required_field_api_returns_controlled_error_not_raw_500(client, db):
    """The GET /consultations/{id}/notes endpoint reading a corrupted
    ConsultationNote.content must return the app's controlled JSON error body
    (via the UndecryptablePHIError exception handler), not an unhandled crash."""
    doctor, c, _note = _seed_corrupted_note(db)

    doctor_token = create_access_token(subject=doctor.user_id, role="doctor", mfa=True)
    r = client.get(
        f"/api/v1/consultations/{c.id}/notes",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "PHI_DECRYPTION_FAILED"
    assert "nội dung nhạy cảm" not in r.text
    assert "gAAAA" not in r.text
