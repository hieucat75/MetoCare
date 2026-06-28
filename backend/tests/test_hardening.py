"""P2-HARDENING-1 tests (+ Codex changes-requested fixes).

Covers: refresh cleanup policy (preserve revoked-unexpired for reuse detection),
maintenance job, Redis backend (atomic TTL + namespaced reset), email blind index.
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import os

import pytest
from app.core import crypto
from app.core.clock import utcnow
from app.core.ratelimit import RedisRateLimiter
from app.jobs.maintenance import run_maintenance
from app.models.auth_tokens import RefreshToken
from app.models.user import UserRole
from app.services import auth

# --------------------------------------------------------------------------- #
# FIX 1 [P1] — Refresh cleanup: delete ONLY expired; preserve revoked-unexpired
# --------------------------------------------------------------------------- #


def _add_refresh(db, *, jti, expires_at, revoked_at=None):
    db.add(
        RefreshToken(
            user_id="u-" + os.urandom(3).hex(),
            jti=jti,
            expires_at=expires_at,
            revoked_at=revoked_at,
            family_id="fam-" + os.urandom(3).hex(),
            generation=0,
            mfa=False,
        )
    )


def test_cleanup_deletes_expired_keeps_revoked_unexpired(db):
    now = dt.datetime(2026, 6, 14)
    tag = os.urandom(4).hex()
    future = now + dt.timedelta(days=30)
    past = now - dt.timedelta(days=1)
    long_ago = now - dt.timedelta(days=30)

    # 1) revoked but UNEXPIRED (revoked long ago) -> PRESERVE (reuse detection needs it)
    _add_refresh(db, jti=f"revfut-{tag}", expires_at=future, revoked_at=long_ago)
    # 2) expired + revoked -> DELETE
    _add_refresh(db, jti=f"exprev-{tag}", expires_at=past, revoked_at=long_ago)
    # 3) expired, not revoked -> DELETE
    _add_refresh(db, jti=f"exp-{tag}", expires_at=past)
    # 4) active unexpired -> PRESERVE
    _add_refresh(db, jti=f"live-{tag}", expires_at=future)
    db.commit()

    deleted = auth.cleanup_expired_refresh_tokens(db, now=now)
    assert deleted >= 2

    remaining = {
        r.jti for r in db.query(RefreshToken).filter(RefreshToken.jti.like(f"%-{tag}")).all()
    }
    assert f"revfut-{tag}" in remaining  # revoked-unexpired preserved
    assert f"live-{tag}" in remaining
    assert f"exprev-{tag}" not in remaining
    assert f"exp-{tag}" not in remaining


def test_cleanup_is_idempotent(db):
    now = dt.datetime(2026, 6, 14)
    auth.cleanup_expired_refresh_tokens(db, now=now)
    assert auth.cleanup_expired_refresh_tokens(db, now=now) == 0


def test_reuse_detection_survives_cleanup(db):
    """The whole point of FIX 1: cleanup must NOT delete the revoked-unexpired
    token, so a replayed (rotated) token is still detected as reuse."""
    email = f"reuse-clean-{os.urandom(4).hex()}@example.com"
    user = auth.register(db, email=email, password="password123", role=UserRole.PATIENT)
    _access, refresh = auth.issue_tokens(db, user, mfa=False)

    # rotate: old `refresh` is now revoked but still unexpired
    _a2, r2, _u = auth.refresh_session(db, refresh)

    # cleanup runs (e.g. nightly) — must keep the revoked-unexpired row
    auth.cleanup_expired_refresh_tokens(db, now=utcnow())

    # replay the rotated token -> reuse detected, family revoked
    with pytest.raises(auth.AuthError):
        auth.refresh_session(db, refresh)
    # the new token of the family is now dead too
    with pytest.raises(auth.AuthError):
        auth.refresh_session(db, r2)


# --------------------------------------------------------------------------- #
# C — Maintenance job
# --------------------------------------------------------------------------- #


def test_run_maintenance_returns_summary(db):
    summary = run_maintenance(db, now=dt.datetime(2026, 6, 14))
    assert "audit_retention_purged" in summary
    assert "refresh_tokens_deleted" in summary
    assert isinstance(summary["audit_retention_purged"], dict)


# --------------------------------------------------------------------------- #
# FIX 2 + FIX 3 — Redis backend (fake client; no real Redis dependency)
# --------------------------------------------------------------------------- #


class _FakeRedis:
    """Minimal Redis stand-in supporting the limiter's Lua + scan paths."""

    def __init__(self):
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def register_script(self, script):
        def run(keys, args):
            k = keys[0]
            self.store[k] = self.store.get(k, 0) + 1
            if self.store[k] == 1:  # atomic EXPIRE-on-first, like the Lua
                self.ttls[k] = int(args[0])
            return self.store[k]

        return run

    def incr(self, k):
        self.store[k] = self.store.get(k, 0) + 1
        return self.store[k]

    def expire(self, k, ttl):
        self.ttls[k] = int(ttl)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return False
        self.store[k] = v
        if ex is not None:
            self.ttls[k] = int(ex)
        return True

    def get(self, k):
        return self.store.get(k)

    def ttl(self, k):
        return self.ttls.get(k, -1)

    def scan_iter(self, match=None, count=None):
        return [k for k in list(self.store) if match is None or fnmatch.fnmatch(k, match)]

    def unlink(self, *keys):
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                self.ttls.pop(k, None)
                n += 1
        return n


def test_redis_rate_limiter_enforces_capacity():
    rl = RedisRateLimiter(client=_FakeRedis())
    results = [rl.allow("k", capacity=3, refill_per_sec=0.05) for _ in range(5)]
    assert results == [True, True, True, False, False]


def test_redis_ttl_always_set_atomically():
    fake = _FakeRedis()
    rl = RedisRateLimiter(client=fake, prefix="metocare:ratelimit:")
    rkey = "metocare:ratelimit:login:1.2.3.4"
    for _ in range(3):
        rl.allow("login:1.2.3.4", capacity=5, refill_per_sec=0.0834)  # window ~60s
        assert fake.ttl(rkey) > 0  # TTL present after EVERY request (no orphan key)


def test_redis_keys_are_namespaced():
    fake = _FakeRedis()
    rl = RedisRateLimiter(client=fake, prefix="metocare:ratelimit:")
    rl.allow("login:x", capacity=5, refill_per_sec=1)
    assert any(k.startswith("metocare:ratelimit:") for k in fake.store)


def test_redis_rejects_unsafe_prefix():
    # Empty or glob-bearing prefix would make reset() scan "*" / over-match.
    for bad in ("", "*", "metocare:*", "metocare:[a]"):
        with pytest.raises(ValueError):
            RedisRateLimiter(client=_FakeRedis(), prefix=bad)


def test_redis_reset_only_deletes_namespace_not_flushdb():
    fake = _FakeRedis()
    fake.set("cache:foo", 1)  # unrelated app data
    fake.set("session:bar", 1)
    rl = RedisRateLimiter(client=fake, prefix="metocare:ratelimit:")
    rl.allow("login:x", capacity=5, refill_per_sec=1)
    rl.allow("register:y", capacity=5, refill_per_sec=1)

    rl.reset()

    assert not any(k.startswith("metocare:ratelimit:") for k in fake.store)  # ours gone
    assert "cache:foo" in fake.store  # unrelated data survives
    assert "session:bar" in fake.store


# --------------------------------------------------------------------------- #
# E — Email blind index
# --------------------------------------------------------------------------- #


def test_blind_index_is_deterministic_and_case_insensitive():
    a = crypto.blind_index("User@Example.com")
    b = crypto.blind_index("  user@example.com ")
    assert a == b  # normalized
    assert a != crypto.blind_index("other@example.com")
    assert len(a) == 64  # sha256 hex
