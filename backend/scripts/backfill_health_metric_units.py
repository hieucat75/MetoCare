#!/usr/bin/env python3
"""
P0 Backfill: sync HealthMetric.value/unit/status from linked LabResult.

Old HealthMetric rows promoted before the _promote_row unit-normalization fix
may have:
  - value = raw OCR value (e.g. 87.7 µmol/L creatinine stored as 87.7 without unit)
  - unit = "" or None (dropped during old promotion)
  - status = wrong (classified against wrong canonical unit)

This script finds all HealthMetric rows with source='lab_result' and syncs:
  - value → LabResult.normalized_value_si
  - unit  → LabResult.normalized_unit_si
  - status → re-classified using canonical value

Safe/idempotent: rows already correct are skipped. Dry-run mode by default.

Usage:
  cd /Users/pth/Developer/Metocare
  python backend/scripts/backfill_health_metric_units.py --dry-run   # preview
  python backend/scripts/backfill_health_metric_units.py             # live run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]  # .../backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import logging  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
_log = logging.getLogger("backfill_hm_units")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync HealthMetric value/unit/status from LabResult (P0 unit fix)."
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False, help="Preview only, no DB writes."
    )
    parser.add_argument("--limit", type=int, default=0, help="Max rows to process (0 = all).")
    args = parser.parse_args()

    from app.core.database import SessionLocal, create_all
    from app.domain.lab_interpreter import classify_value
    from app.domain.lab_normalization import normalize_value_to_si
    from app.models.clinical import HealthMetric, LabResult
    from sqlalchemy import select

    try:
        create_all()
    except Exception as exc:
        _log.debug("create_all skipped (expected in production): %s", exc)

    db = SessionLocal()
    updated = skipped = errors = 0

    try:
        # Find all lab-sourced HealthMetric rows.
        stmt = select(HealthMetric).where(
            HealthMetric.source == "lab_result",
            HealthMetric.deleted_at.is_(None),
            HealthMetric.source_ref.is_not(None),
        )
        if args.limit > 0:
            stmt = stmt.limit(args.limit)

        rows = list(db.execute(stmt).scalars())
        _log.info("Found %d lab-sourced HealthMetric rows to audit.", len(rows))

        for hm in rows:
            try:
                # Load the source LabResult.
                lr = db.get(LabResult, hm.source_ref)
                if lr is None:
                    _log.warning(
                        "HealthMetric %s has source_ref %s but LabResult not found",
                        hm.id,
                        hm.source_ref,
                    )
                    skipped += 1
                    continue

                # Get canonical value/unit from LabResult.
                norm_value = lr.normalized_value_si
                norm_unit = lr.normalized_unit_si

                # If LabResult itself lacks normalized fields, compute now.
                if norm_value is None and lr.canonical_name and lr.value is not None:
                    norm_value, norm_unit = normalize_value_to_si(
                        float(lr.original_value or lr.value),
                        lr.original_unit or lr.unit or "",
                        lr.canonical_name,
                    )

                if norm_value is None:
                    _log.warning(
                        "HealthMetric %s: could not resolve canonical value for lab %s",
                        hm.id,
                        hm.source_ref,
                    )
                    skipped += 1
                    continue

                # Compute canonical status.
                status_enum = classify_value(hm.metric_type, norm_value)
                new_status = status_enum.value if status_enum else hm.status

                # Check if already correct.
                already_correct = (
                    abs((hm.value or 0) - norm_value) < 0.0001
                    and (hm.unit or "") == (norm_unit or "")
                    and hm.status == new_status
                )
                if already_correct:
                    skipped += 1
                    continue

                _log.info(
                    "%s HealthMetric %s (%s): value %s→%.4f, unit %r→%r, status %r→%r",
                    "[DRY]" if args.dry_run else "[FIX]",
                    hm.id,
                    hm.metric_type,
                    hm.value,
                    norm_value,
                    hm.unit,
                    norm_unit,
                    hm.status,
                    new_status,
                )

                if not args.dry_run:
                    hm.value = norm_value
                    hm.unit = norm_unit
                    hm.status = new_status

                updated += 1

            except Exception as exc:  # noqa: BLE001
                _log.error("Error processing HealthMetric %s: %s", hm.id, exc)
                errors += 1

        if not args.dry_run and updated > 0:
            db.commit()
            _log.info("Committed %d updates.", updated)

        _log.info(
            "Done. updated=%d skipped=%d errors=%d dry_run=%s",
            updated,
            skipped,
            errors,
            args.dry_run,
        )

    finally:
        db.close()

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
