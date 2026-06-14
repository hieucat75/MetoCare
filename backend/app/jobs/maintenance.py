"""Operational maintenance job (cron-friendly, idempotent).

Runs the periodic data-lifecycle tasks:
- audit-log retention purge (per-category TTL)
- expired/revoked refresh-token cleanup

Safe to run repeatedly. Invoke from cron / a scheduler:

    python -m app.jobs.maintenance

It opens its own DB session and prints a JSON summary. No external calls.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.services import audit_retention, auth


def run_maintenance(db: Session, *, now: dt.datetime | None = None) -> dict:
    """Run all maintenance tasks; return a summary of what was purged."""
    audit_purged = audit_retention.purge_expired(db, now=now)
    refresh_deleted = auth.cleanup_expired_refresh_tokens(db, now=now)
    return {
        "audit_retention_purged": audit_purged,
        "refresh_tokens_deleted": refresh_deleted,
    }


def main() -> None:  # pragma: no cover - CLI entrypoint
    import json

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        summary = run_maintenance(db)
    finally:
        db.close()
    print(json.dumps({"maintenance": summary}, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    main()
