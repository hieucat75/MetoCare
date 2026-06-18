"""Rate limiting + account lockout tests."""

from __future__ import annotations

import os

from app.core.config import get_settings
from app.core.ratelimit import InMemoryRateLimiter, LockoutManager

# --------------------------------------------------------------------------- #
# Unit
# --------------------------------------------------------------------------- #

def test_token_bucket_limits_then_refills():
    rl = InMemoryRateLimiter()
    allowed = [rl.allow("k", capacity=3, refill_per_sec=0, now=0) for _ in range(5)]
    assert allowed == [True, True, True, False, False]
    # 2 seconds later at 1 token/sec -> 2 tokens refilled.
    assert rl.allow("k", capacity=3, refill_per_sec=1, now=2) is True


def test_lockout_manager_locks_and_cools_down():
    lm = LockoutManager()
    for _ in range(5):
        lm.record_failure("u", now=0)
    assert lm.is_locked("u", max_failures=5, cooldown_seconds=900, now=0) is True
    # cooldown elapsed -> unlocked.
    assert lm.is_locked("u", max_failures=5, cooldown_seconds=900, now=901) is False


def test_lockout_reset_clears_counter():
    lm = LockoutManager()
    for _ in range(5):
        lm.record_failure("u2", now=0)
    lm.reset("u2")
    assert lm.is_locked("u2", max_failures=5, cooldown_seconds=900, now=0) is False


# --------------------------------------------------------------------------- #
# Integration
# --------------------------------------------------------------------------- #

def _register(client, role="patient"):
    email = f"rl-{os.urandom(4).hex()}@example.com"
    pw = "password123"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": pw, "role": role})
    assert r.status_code == 201, r.text
    return email, pw


def test_rate_limit_returns_429(client):
    settings = get_settings()
    original = settings.ratelimit_auth_capacity
    settings.ratelimit_auth_capacity = 3
    try:
        codes = [
            client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"}).status_code
            for _ in range(6)
        ]
    finally:
        settings.ratelimit_auth_capacity = original
    assert codes[0] == 401  # invalid token, but within limit
    assert 429 in codes  # limit eventually tripped


def test_account_lockout_after_failures(client):
    email, pw = _register(client)
    settings = get_settings()
    for _ in range(settings.lockout_max_failures):
        r = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 401
    # Next attempt is locked, even with the correct password.
    locked = client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    assert locked.status_code == 423


def test_lockout_reset_on_successful_login(client):
    email, pw = _register(client)
    for _ in range(3):  # below threshold
        client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
    ok = client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    assert ok.status_code == 200  # success resets the counter
    # A single failure afterwards must not be locked (counter was reset).
    again = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
    assert again.status_code == 401


def test_admin_can_unlock_account(client, token_for):
    email, pw = _register(client)
    settings = get_settings()
    for _ in range(settings.lockout_max_failures):
        client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
    assert client.post(
        "/api/v1/auth/login", json={"email": email, "password": pw}
    ).status_code == 423

    unlock = client.post(
        "/api/v1/admin/unlock-account",
        headers=token_for("admin-1", "internal_admin", mfa=True),
        json={"email": email},
    )
    assert unlock.status_code == 200, unlock.text

    assert client.post(
        "/api/v1/auth/login", json={"email": email, "password": pw}
    ).status_code == 200


def test_non_auth_endpoint_not_rate_limited(client):
    for _ in range(30):
        assert client.get("/api/v1/health").status_code == 200
