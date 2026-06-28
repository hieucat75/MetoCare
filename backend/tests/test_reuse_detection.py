"""Refresh-token reuse detection (token-family revocation)."""

from __future__ import annotations

import os

from app.models.governance import AuditLog


def _register(client):
    email = f"reuse-{os.urandom(4).hex()}@example.com"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 201
    return r.json()


def test_reuse_of_rotated_token_revokes_whole_family(client, db):
    tok = _register(client)
    t0 = tok["refresh_token"]

    # Rotate once: t0 -> t1 (t0 now revoked).
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": t0})
    assert r1.status_code == 200
    t1 = r1.json()["refresh_token"]

    # Reuse the OLD (rotated) token -> reuse detected -> 401.
    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": t0})
    assert reuse.status_code == 401
    assert "reuse" in reuse.json()["detail"].lower()

    # The whole family is now dead: even the legitimate newest token is revoked.
    after = client.post("/api/v1/auth/refresh", json={"refresh_token": t1})
    assert after.status_code == 401


def test_reuse_writes_high_severity_audit(client, db):
    tok = _register(client)
    t0 = tok["refresh_token"]
    client.post("/api/v1/auth/refresh", json={"refresh_token": t0})  # rotate
    client.post("/api/v1/auth/refresh", json={"refresh_token": t0})  # reuse -> detection

    row = (
        db.query(AuditLog)
        .filter(AuditLog.action == "refresh_token_reuse_detected")
        .order_by(AuditLog.timestamp.desc())
        .first()
    )
    assert row is not None
    assert row.severity == "high"
    assert row.outcome == "deny"
