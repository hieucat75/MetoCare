#!/usr/bin/env python3
"""Idempotent seed script for the drug reference catalog.

Usage (from the repo root):
  python backend/scripts/seed_drug_catalog.py            # live run
  python backend/scripts/seed_drug_catalog.py --dry-run  # count only

Safe to re-run: skips drugs whose generic_name already exists.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parent.parent
sys.path.insert(0, str(_BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.services.drug_catalog import seed_catalog  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the drug reference catalog.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show how many rows would be inserted without writing to the DB.",
    )
    args = parser.parse_args()

    if args.dry_run:
        from app.services.drug_catalog import _SEED

        with SessionLocal() as db:
            from app.models.drug_catalog import DrugEntry

            existing = {
                r.generic_name.lower() for r in db.query(DrugEntry.generic_name).all()
            }
        new_count = sum(1 for s in _SEED if s["generic_name"].lower() not in existing)
        print(f"[dry-run] Would insert {new_count} / {len(_SEED)} entries.")
        return

    with SessionLocal() as db:
        inserted = seed_catalog(db)

    print(f"Seeded {inserted} new drug entries.")


if __name__ == "__main__":
    main()
