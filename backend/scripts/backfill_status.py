#!/usr/bin/env python3
"""
Safe idempotent backfill: recompute status for all LabResult records.

Usage:
  python backend/scripts/backfill_status.py           # live run
  python backend/scripts/backfill_status.py --dry-run # preview only
  python backend/scripts/backfill_status.py --batch-id <id>  # single batch

Exit code: 0 on success, 1 on any error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `app` importable when run as a script from the project root or backend dir.
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]  # .../backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import logging  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
_log = logging.getLogger("backfill_status")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill LabResult.status via reclassification.")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes.")
    parser.add_argument("--batch-id", default=None, help="Only process a specific batch UUID.")
    args = parser.parse_args()

    from app.core.database import SessionLocal, create_all
    from app.services.lab import reclassify_lab_results

    # Dev/test: ensure tables exist (production uses Alembic, skips this).
    try:
        create_all()
    except Exception as exc:
        _log.debug("create_all skipped or failed (expected in production): %s", exc)

    db = SessionLocal()
    try:
        _log.info(
            "Starting reclassification [dry_run=%s, batch_id=%s] ...",
            args.dry_run,
            args.batch_id,
        )
        result = reclassify_lab_results(db, batch_id=args.batch_id, dry_run=args.dry_run)
    except Exception as exc:
        _log.error("Reclassification failed: %s", exc, exc_info=True)
        return 1
    finally:
        db.close()

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"\n=== Backfill Status [{mode}] ===")
    print(f"  Updated : {result['updated']}")
    print(f"  Skipped : {result['skipped']}")
    print(f"  Errors  : {len(result['errors'])}")
    if result["errors"]:
        print("\nErrors:")
        for e in result["errors"]:
            print(f"  - {e}")

    if result["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
