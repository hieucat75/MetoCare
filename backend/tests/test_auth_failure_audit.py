"""WS4-F3 — failed authentication must leave an attributable, PHI-free trace.

Before this fix only *successful* logins were audited: `auth.authenticate()`
raises before reaching its `audit.record` call, and the lockout / rate-limit
branches emitted no log, metric or audit entry at all. Brute force and
credential stuffing were visible only as anonymous status-code counts.
"""

from __future__ import annotations

import hashlib

import pytest
from app.core.config import get_settings
from app.core.metrics import registry
from app.core.security import hash_password
from app.models.governance import AuditLog
from app.models.user import User, UserRole
from sqlalchemy import select


def _login_denials(db) -> list[AuditLog]:
    return list(
        db.execute(
            select(AuditLog).where(AuditLog.action == "login", AuditLog.outcome == "deny")
        )
        .scalars()
        .all()
    )


@pytest.fixture
def login_user(db):
    email = f"ws4f3-{hashlib.sha256(str(id(db)).encode()).hexdigest()[:10]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("CorrectHorse1"),
        role=UserRole.PATIENT,
        full_name="Nguyễn Văn Test",
    )
    db.add(user)
    db.commit()
    return {"email": email, "user_id": user.id}


def _expected_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def test_bad_credentials_are_audited_with_a_hashed_key(client, db, login_user):
    before = len(_login_denials(db))
    r = client.post(
        "/api/v1/auth/login", json={"email": login_user["email"], "password": "WrongPass9"}
    )
    assert r.status_code == 401

    rows = _login_denials(db)
    assert len(rows) == before + 1
    entry = rows[-1]
    assert entry.outcome == "deny"
    assert entry.severity == "warning"
    assert entry.actor_id is None
    assert entry.details["reason"] == "bad_credentials"
    assert entry.details["key_hash"] == _expected_hash(login_user["email"].lower())


def test_failed_login_audit_never_stores_the_raw_identifier(client, db, login_user):
    client.post(
        "/api/v1/auth/login", json={"email": login_user["email"], "password": "WrongPass9"}
    )
    entry = _login_denials(db)[-1]
    serialized = repr(entry.details)
    assert login_user["email"] not in serialized
    assert login_user["email"].split("@")[0] not in serialized


def test_failed_login_increments_the_auth_failures_counter(client, db, login_user):
    registry.reset()
    client.post(
        "/api/v1/auth/login", json={"email": login_user["email"], "password": "WrongPass9"}
    )
    rendered = registry.render()
    assert "auth_failures_total" in rendered
    assert 'reason="bad_credentials"' in rendered


def test_lockout_branch_is_audited_and_counted(client, db, login_user):
    settings = get_settings()
    registry.reset()
    for _ in range(settings.lockout_max_failures):
        client.post(
            "/api/v1/auth/login", json={"email": login_user["email"], "password": "WrongPass9"}
        )
    r = client.post(
        "/api/v1/auth/login", json={"email": login_user["email"], "password": "CorrectHorse1"}
    )
    assert r.status_code == 423

    locked = [e for e in _login_denials(db) if e.details.get("reason") == "locked"]
    assert locked, "the 423 lockout branch must emit an audit entry"
    assert locked[-1].severity == "warning"
    assert locked[-1].details["key_hash"] == _expected_hash(login_user["email"].lower())
    assert 'reason="locked"' in registry.render()


def test_rate_limited_login_is_audited_and_counted(client, db, login_user, monkeypatch):
    settings = get_settings()
    registry.reset()
    capacity = settings.ratelimit_auth_capacity
    last = None
    for _ in range(capacity + 2):
        last = client.post(
            "/api/v1/auth/login",
            json={"email": login_user["email"], "password": "WrongPass9"},
        )
    assert last is not None and last.status_code == 429

    throttled = [e for e in _login_denials(db) if e.details.get("reason") == "rate_limited"]
    assert throttled, "the 429 rate-limit branch must emit an audit entry"
    assert throttled[-1].severity == "warning"
    assert 'reason="rate_limited"' in registry.render()


def test_successful_login_is_still_audited_as_success(client, db, login_user):
    r = client.post(
        "/api/v1/auth/login", json={"email": login_user["email"], "password": "CorrectHorse1"}
    )
    assert r.status_code == 200
    rows = (
        db.execute(
            select(AuditLog).where(
                AuditLog.action == "login",
                AuditLog.outcome == "success",
                AuditLog.actor_id == login_user["user_id"],
            )
        )
        .scalars()
        .all()
    )
    assert rows
