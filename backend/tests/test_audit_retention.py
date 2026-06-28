"""Audit retention purge tests."""

from __future__ import annotations

import datetime as dt
import os

from app.models.governance import AuditLog
from app.services import audit_retention


def test_category_mapping():
    assert audit_retention.category_for("login") == "auth"
    assert audit_retention.category_for("register") == "auth"
    assert audit_retention.category_for("admin_read") == "admin"
    assert audit_retention.category_for("read") == "data_access"
    assert audit_retention.category_for("interpret") == "data_access"


def test_purge_expired_by_category(db):
    now = dt.datetime(2026, 6, 12)
    aid = "ret-" + os.urandom(4).hex()

    def add(action, age_days):
        db.add(
            AuditLog(
                actor_type="user",
                actor_id=aid,
                action=action,
                resource_type="x",
                timestamp=now - dt.timedelta(days=age_days),
            )
        )

    add("read", 800)  # data_access, TTL 730 -> purge
    add("read", 10)  # data_access, recent -> keep
    add("login", 400)  # auth, TTL 365 -> purge
    add("login", 30)  # auth, recent -> keep
    add("admin_read", 2000)  # admin, TTL 1095 -> purge
    db.commit()

    result = audit_retention.purge_expired(db, now=now)
    assert result["data_access"] >= 1
    assert result["auth"] >= 1
    assert result["admin"] >= 1

    rows = db.query(AuditLog).filter(AuditLog.actor_id == aid).all()
    kept = sorted(r.action for r in rows)
    assert kept == ["login", "read"]  # only the two recent rows survive
