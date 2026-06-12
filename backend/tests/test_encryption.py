"""Field-level PHI encryption tests."""

from __future__ import annotations

import os

import pytest
from app.core import crypto
from app.core.crypto import EncryptionConfigError
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services.phi_migration import encrypt_existing_phi
from sqlalchemy import text


def test_encrypt_decrypt_roundtrip():
    token = crypto.encrypt("Nguyễn Văn Test")
    assert token != "Nguyễn Văn Test"
    assert crypto.decrypt(token) == "Nguyễn Văn Test"


def test_try_decrypt_on_plaintext_returns_none():
    assert crypto.try_decrypt("this-is-not-ciphertext") is None


def test_orm_field_is_ciphertext_at_rest(db):
    user = User(
        email=f"enc-{os.urandom(4).hex()}@example.com",
        password_hash="x",
        role=UserRole.PATIENT,
        full_name="Trần Thị PHI",
    )
    db.add(user)
    db.commit()

    # Raw DB value must be ciphertext (not the plaintext name).
    raw = db.execute(
        text("SELECT full_name FROM users WHERE id = :id"), {"id": user.id}
    ).scalar_one()
    assert raw != "Trần Thị PHI"
    assert crypto.decrypt(raw) == "Trần Thị PHI"

    # ORM read transparently decrypts.
    db.expire(user)
    assert db.get(User, user.id).full_name == "Trần Thị PHI"


def test_profile_phi_fields_encrypted(db):
    u = User(email=f"p-{os.urandom(4).hex()}@example.com",
             password_hash="x", role=UserRole.PATIENT)
    db.add(u)
    db.flush()
    p = PatientProfile(
        user_id=u.id, full_name="BN Test", dob="1990-05-01",
        phone="0900000000", address="123 Đường Test", allergies="penicillin",
    )
    db.add(p)
    db.commit()
    for col in ("full_name", "dob", "phone", "address", "allergies"):
        raw = db.execute(
            text(f"SELECT {col} FROM patient_profiles WHERE id = :id"), {"id": p.id}
        ).scalar_one()
        assert crypto.try_decrypt(raw) is not None, f"{col} not encrypted at rest"
    # ORM round-trips the values.
    db.expire(p)
    fresh = db.get(PatientProfile, p.id)
    assert fresh.dob == "1990-05-01"
    assert fresh.phone == "0900000000"


def test_key_rotation_decrypts_old_ciphertext():
    from cryptography.fernet import Fernet, MultiFernet

    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    old_token = Fernet(old_key).encrypt(b"secret-phi").decode()
    # New primary + old key retained -> can still decrypt old ciphertext.
    rotated = MultiFernet([Fernet(new_key), Fernet(old_key)])
    assert rotated.decrypt(old_token.encode()).decode() == "secret-phi"


def test_encrypt_existing_phi_migrates_plaintext(db):
    # Insert a row with PLAINTEXT directly (bypassing ORM encryption).
    u = User(email=f"legacy-{os.urandom(4).hex()}@example.com",
             password_hash="x", role=UserRole.PATIENT)
    db.add(u)
    db.commit()
    db.execute(
        text("UPDATE users SET full_name = :v WHERE id = :id"),
        {"v": "Legacy Plaintext", "id": u.id},
    )
    db.commit()

    # Sanity: stored value is plaintext now.
    raw = db.execute(text("SELECT full_name FROM users WHERE id = :id"), {"id": u.id}).scalar_one()
    assert raw == "Legacy Plaintext"

    n = encrypt_existing_phi(db)
    assert n >= 1

    raw2 = db.execute(text("SELECT full_name FROM users WHERE id = :id"), {"id": u.id}).scalar_one()
    assert raw2 != "Legacy Plaintext"
    assert crypto.decrypt(raw2) == "Legacy Plaintext"


def test_missing_key_raises(monkeypatch):
    from app.core.config import get_settings

    crypto._cipher.cache_clear()
    get_settings.cache_clear()
    monkeypatch.setenv("MCP_ENCRYPTION_KEYS", "")
    with pytest.raises(EncryptionConfigError):
        crypto.encrypt("x")
    # restore cached settings/cipher for other tests
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
