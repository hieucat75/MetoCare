#!/usr/bin/env python3
"""
Data integrity cleanup — identify and optionally correct bad persisted data.

Usage:
  python backend/scripts/data_integrity_cleanup.py --dry-run   # report only (default)
  python backend/scripts/data_integrity_cleanup.py --apply     # apply safe corrections

Safety rules (enforced):
  - NEVER delete records
  - NEVER change original_value or original_unit
  - NEVER auto-correct canonical_name / metric_type (too destructive)
  - ONLY safe corrections: re-normalize normalized_value_si / normalized_unit_si
    when unit is clearly wrong, plus set data_quality_flag + data_quality_note
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
_log = logging.getLogger("data_integrity_cleanup")

# ---------------------------------------------------------------------------
# Suspicious patterns to scan for
# ---------------------------------------------------------------------------

# Each pattern:
#   name:        identifier
#   description: human readable
#   sql_filter:  (canonical_name, extra_where_clause)  — for LabResult query
#   checker:     callable(row) -> (is_suspicious: bool, reason: str, safe_correction: dict | None)
#                  safe_correction: {"normalized_value_si": float, "normalized_unit_si": str}
#                  or None if no auto-correction is safe

# We implement checks in Python after a broadish SQL fetch to keep things readable
# and avoid dialect-specific SQL.

PATTERNS: list[dict] = [
    {
        "name": "creatinine_unit_mismatch",
        "description": (
            "Creatinine value stored with a normalized unit of mg/dL but the value "
            "is > 28 mg/dL — physiologically implausible. Likely the original value "
            "was in µmol/L and stored without conversion."
        ),
        "canonical_name": "creatinine",
        # Only rows where normalized_unit_si looks like mg/dL and value > 28
        "safe_correction": True,
        "correction_description": "Re-normalize: treat normalized_value_si as µmol/L → mg/dL (multiply by si_factor=0.011312)",
    },
    {
        "name": "health_metric_creatinine_high",
        "description": (
            "HealthMetric with metric_type='creatinine' and value > 28 mg/dL "
            "— likely wrong unit or metric_type."
        ),
        "canonical_name": "creatinine",
        "model": "health_metric",
        "safe_correction": False,  # do NOT auto-correct metric_type
        "correction_description": "Flag as suspicious only; manual review required",
    },
    {
        "name": "glucose_as_creatinine",
        "description": (
            "HealthMetric with metric_type='creatinine' but value > 100 mg/dL "
            "— glucose-range value stored as creatinine — probable metric_type mismatch."
        ),
        "canonical_name": "creatinine",
        "model": "health_metric",
        "value_min": 100.0,
        "safe_correction": False,
        "correction_description": "Flag suspicious=True; do NOT auto-correct metric_type",
    },
]


def _norm_unit(u: str) -> str:
    return (u or "").replace("µ", "u").replace("μ", "u").replace("mc", "u").strip().lower()


def run_cleanup(dry_run: bool = True) -> dict:
    from app.core.database import SessionLocal, create_all
    from app.models.clinical import HealthMetric, LabResult

    try:
        create_all()
    except Exception as exc:
        _log.debug("create_all skipped (expected in production): %s", exc)

    db = SessionLocal()
    summary = {
        "dry_run": dry_run,
        "patterns": [],
        "total_suspicious": 0,
        "total_auto_corrected": 0,
        "total_flagged": 0,
        "errors": [],
    }

    try:
        # ----------------------------------------------------------------
        # Pattern 1 — creatinine unit mismatch in LabResult
        # ----------------------------------------------------------------
        from sqlalchemy import select

        stmt = select(LabResult).where(
            LabResult.canonical_name == "creatinine",
            LabResult.deleted_at.is_(None),
        )
        lab_rows = db.execute(stmt).scalars().all()

        suspicious_lab: list[LabResult] = []
        for row in lab_rows:
            if row.normalized_value_si is None:
                continue
            unit = row.normalized_unit_si or ""
            val = row.normalized_value_si
            # Suspicious: normalized_unit_si looks like mg/dL but value > 28
            if _norm_unit(unit) == "mg/dl" and val > 28.0:
                suspicious_lab.append(row)

        pattern_result = {
            "name": "creatinine_unit_mismatch",
            "description": PATTERNS[0]["description"],
            "found": len(suspicious_lab),
            "ids": [str(r.id) for r in suspicious_lab],
            "corrected": 0,
            "flagged": 0,
            "examples": [],
        }

        for row in suspicious_lab[:5]:  # show up to 5 examples
            orig_val = row.normalized_value_si
            # Re-normalize: if stored value is actually µmol/L, convert to mg/dL
            # creatinine si_factor = 0.011312  (µmol/L → mg/dL)
            corrected_val = round(orig_val * 0.011312, 4)
            pattern_result["examples"].append(
                {
                    "id": str(row.id),
                    "canonical_name": row.canonical_name,
                    "normalized_value_si": orig_val,
                    "normalized_unit_si": row.normalized_unit_si,
                    "suggested_correction": f"{corrected_val} mg/dL",
                }
            )

        if not dry_run:
            for row in suspicious_lab:
                try:
                    orig_val = row.normalized_value_si
                    corrected_val = round(orig_val * 0.011312, 4)
                    # Safe correction only — fix normalized fields, never original
                    row.normalized_value_si = corrected_val
                    row.normalized_unit_si = "mg/dL"
                    row.data_quality_flag = "flag"
                    row.data_quality_note = (
                        f"data_integrity_cleanup: renormalized creatinine "
                        f"{orig_val} (was stored as mg/dL but implausible) → "
                        f"{corrected_val} mg/dL (treated as µmol/L)"
                    )
                    pattern_result["corrected"] += 1
                except Exception as exc:
                    msg = f"Error correcting LabResult {row.id}: {exc}"
                    _log.error(msg)
                    summary["errors"].append(msg)
        else:
            # Dry-run: just flag
            for row in suspicious_lab:
                row.data_quality_flag = "flag"
                row.data_quality_note = (
                    "data_integrity_cleanup (dry-run): creatinine normalized value "
                    f"{row.normalized_value_si} {row.normalized_unit_si} is implausible "
                    "— would re-normalize in --apply mode"
                )
            pattern_result["flagged"] = len(suspicious_lab)

        summary["patterns"].append(pattern_result)
        summary["total_suspicious"] += len(suspicious_lab)
        summary["total_auto_corrected"] += pattern_result["corrected"]
        summary["total_flagged"] += pattern_result["flagged"]

        # ----------------------------------------------------------------
        # Pattern 2 — HealthMetric creatinine high
        # ----------------------------------------------------------------
        hm_stmt = select(HealthMetric).where(
            HealthMetric.metric_type == "creatinine",
            HealthMetric.deleted_at.is_(None),
        )
        hm_rows = db.execute(hm_stmt).scalars().all()

        suspicious_hm: list[HealthMetric] = []
        for row in hm_rows:
            if row.value is None:
                continue
            unit = row.unit or ""
            if _norm_unit(unit) == "mg/dl" and row.value > 28.0:
                suspicious_hm.append(row)

        pattern2 = {
            "name": "health_metric_creatinine_high",
            "description": PATTERNS[1]["description"],
            "found": len(suspicious_hm),
            "ids": [str(r.id) for r in suspicious_hm],
            "corrected": 0,
            "flagged": 0,
            "examples": [],
        }

        for row in suspicious_hm[:5]:
            pattern2["examples"].append(
                {
                    "id": str(row.id),
                    "metric_type": row.metric_type,
                    "value": row.value,
                    "unit": row.unit,
                    "note": "Implausible creatinine — manual review required",
                }
            )

        # Always flag only — never auto-correct HealthMetric metric_type
        if not dry_run:
            for row in suspicious_hm:
                try:
                    row.data_quality_flag = "flag"
                    row.data_quality_note = (
                        f"data_integrity_cleanup: creatinine value {row.value} {row.unit} "
                        "exceeds physiological maximum (28 mg/dL) — manual review required"
                    )
                    pattern2["flagged"] += 1
                except Exception as exc:
                    msg = f"Error flagging HealthMetric {row.id}: {exc}"
                    _log.error(msg)
                    summary["errors"].append(msg)
        else:
            pattern2["flagged"] = len(suspicious_hm)

        summary["patterns"].append(pattern2)
        summary["total_suspicious"] += len(suspicious_hm)
        summary["total_flagged"] += pattern2["flagged"]

        # ----------------------------------------------------------------
        # Pattern 3 — glucose-range value stored as creatinine metric_type
        # ----------------------------------------------------------------
        suspicious_hm3: list[HealthMetric] = []
        for row in hm_rows:
            if row.value is None:
                continue
            unit = row.unit or ""
            if _norm_unit(unit) == "mg/dl" and row.value > 100.0:
                suspicious_hm3.append(row)

        pattern3 = {
            "name": "glucose_as_creatinine",
            "description": PATTERNS[2]["description"],
            "found": len(suspicious_hm3),
            "ids": [str(r.id) for r in suspicious_hm3],
            "corrected": 0,
            "flagged": 0,
            "examples": [],
        }

        for row in suspicious_hm3[:5]:
            pattern3["examples"].append(
                {
                    "id": str(row.id),
                    "metric_type": row.metric_type,
                    "value": row.value,
                    "unit": row.unit,
                    "note": "Glucose-range value stored as creatinine — probable metric_type mismatch",
                }
            )

        # Flag only — no auto-correction
        if not dry_run:
            for row in suspicious_hm3:
                try:
                    if row.data_quality_flag != "flag":  # don't overwrite already flagged
                        row.data_quality_flag = "flag"
                        row.data_quality_note = (
                            f"data_integrity_cleanup: creatinine metric_type has glucose-range "
                            f"value {row.value} {row.unit} — probable metric_type mismatch"
                        )
                    pattern3["flagged"] += 1
                except Exception as exc:
                    msg = f"Error flagging HealthMetric {row.id} (pattern3): {exc}"
                    _log.error(msg)
                    summary["errors"].append(msg)
        else:
            pattern3["flagged"] = len(suspicious_hm3)

        summary["patterns"].append(pattern3)
        summary["total_suspicious"] += len(suspicious_hm3)
        summary["total_flagged"] += pattern3["flagged"]

        # ----------------------------------------------------------------
        # Commit
        # ----------------------------------------------------------------
        if not dry_run:
            try:
                db.commit()
                _log.info("Changes committed.")
            except Exception as exc:
                db.rollback()
                msg = f"DB commit failed: {exc}"
                _log.error(msg)
                summary["errors"].append(msg)
                summary["total_auto_corrected"] = 0
                summary["total_flagged"] = 0

    finally:
        db.close()

    return summary


def print_report(summary: dict) -> None:
    mode = "DRY-RUN" if summary["dry_run"] else "APPLY"
    print(f"\n{'=' * 60}")
    print(f"  Data Integrity Cleanup Report [{mode}]")
    print(f"{'=' * 60}\n")

    for p in summary["patterns"]:
        print(f"Pattern: {p['name']}")
        print(f"  Description: {p['description']}")
        print(f"  Found: {p['found']} records")
        if p["ids"]:
            print(f"  IDs (first 20): {p['ids'][:20]}")
        if p.get("examples"):
            print("  Examples:")
            for ex in p["examples"]:
                print(f"    {ex}")
        if not summary["dry_run"]:
            print(f"  Auto-corrected: {p['corrected']}")
            print(f"  Flagged:        {p['flagged']}")
        print()

    print(f"{'=' * 60}")
    print(f"SUMMARY [{mode}]:")
    print(f"  Total suspicious records: {summary['total_suspicious']}")
    if not summary["dry_run"]:
        print(f"  Auto-corrected (re-normalized): {summary['total_auto_corrected']}")
        print(f"  Flagged for manual review:      {summary['total_flagged']}")
        print("  Records deleted: 0 (NEVER DELETE)")
    print(f"  Errors: {len(summary['errors'])}")
    if summary["errors"]:
        print("  Error details:")
        for e in summary["errors"]:
            print(f"    - {e}")
    print(f"{'=' * 60}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Data integrity cleanup — identify and optionally correct bad persisted data."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview only, no DB writes (default).",
    )
    parser.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Apply safe corrections.",
    )
    args = parser.parse_args()

    if not args.dry_run:
        _log.warning("APPLY mode: safe corrections will be written to DB.")

    summary = run_cleanup(dry_run=args.dry_run)
    print_report(summary)

    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
