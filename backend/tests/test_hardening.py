"""P2-HARDENING-1 tests: refresh cleanup, maintenance job, Redis backend, blind index."""

from __future__ import annotations

import datetime as dt
import os

from app.core import crypto
from app.core.ratelimit import RedisRateLimiter
from app.jobs.maintenance import run_maintenance
from app.models.auth_tokens import RefreshToken
from app.services import auth

# --------------------------------------------------------------------------- #
# B — Refresh-token cleanup
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


def test_cleanup_removes_expired_and_old_revoked(db):
    now = dt.datetime(2026, 6, 14)
    tag = os.urandom(4).hex()
    future = now + dt.timedelta(days=30)
    # expired -> delete
    _add_refresh(db, jti=f"exp-{tag}", expires_at=now - dt.timedelta(days=1))
    # revoked long ago -> delete
    _add_refresh(db, jti=f"oldrev-{tag}", expires_at=future, revoked_at=now - dt.timedelta(days=30))
    # live -> keep
    _add_refresh(db, jti=f"live-{tag}", expires_at=future)
    # recently revoked (within grace) -> keep
    _add_refresh(
        db, jti=f"freshrev-{tag}", expires_at=future, revoked_at=now - dt.timedelta(days=1)
    )
    db.commit()

    deleted = auth.cleanup_expired_refresh_tokens(db, now=now, revoked_grace_days=7)
    assert deleted >= 2

    rows = db.query(RefreshToken).filter(RefreshToken.jti.like(f"%-{tag}")).all()
    remaining = {r.jti for r in rows}
    assert f"live-{tag}" in remaining
    assert f"freshrev-{tag}" in remaining
    assert f"exp-{tag}" not in remaining
    assert f"oldrev-{tag}" not in remaining


def test_cleanup_is_idempotent(db):
    now = dt.datetime(2026, 6, 14)
    auth.cleanup_expired_refresh_tokens(db, now=now)
    second = auth.cleanup_expired_refresh_tokens(db, now=now)
    assert second == 0  # nothing new to delete


# --------------------------------------------------------------------------- #
# C — Maintenance job
# --------------------------------------------------------------------------- #

def test_run_maintenance_returns_summary(db):
    summary = run_maintenance(db, now=dt.datetime(2026, 6, 14))
    assert "audit_retention_purged" in summary
    assert "refresh_tokens_deleted" in summary
    assert isinstance(summary["audit_retention_purged"], dict)


# --------------------------------------------------------------------------- #
# D — Redis rate-limit backend (fake client; no real Redis dependency)
# --------------------------------------------------------------------------- #

class _FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key, ttl):
        self.expires[key] = ttl

    def flushdb(self):
        self.store.clear()
        self.expires.clear()


def test_redis_rate_limiter_enforces_capacity():
    rl = RedisRateLimiter(client=_FakeRedis())
    results = [rl.allow("k", capacity=3, refill_per_sec=0.05) for _ in range(5)]
    assert results == [True, True, True, False, False]


def test_redis_rate_limiter_sets_window_expiry():
    fake = _FakeRedis()
    rl = RedisRateLimiter(client=fake)
    rl.allow("k", capacity=3, refill_per_sec=0.05)  # window = 3/0.05 = 60s
    assert fake.expires["k"] == 60
    rl.reset()
    assert fake.store == {}


# --------------------------------------------------------------------------- #
# E — Email blind index
# --------------------------------------------------------------------------- #

def test_blind_index_is_deterministic_and_case_insensitive():
    a = crypto.blind_index("User@Example.com")
    b = crypto.blind_index("  user@example.com ")
    assert a == b  # normalized
    assert a != crypto.blind_index("other@example.com")
    assert len(a) == 64  # sha256 hex
