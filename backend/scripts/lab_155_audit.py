"""PHI-free audit for #155 (Azure DI table extraction range-as-value defect).

Companion to lab_analyte_audit.py (#153/#154). That script already counts
rbc/hematocrit dimensional mismatches; this one covers what #155 added:
hemoglobin's new unit guard, and a heuristic detector for historical rows
whose stored value equals a bound parsed from their own printed reference
range — the shape #155's `_is_range_like` guard now refuses at extraction
time, so any pre-fix row matching it is a candidate for the exact defect,
not proof of it (a value can coincide with its range's edge legitimately).

Emits COUNTS ONLY. No patient_id, no test_name, no values, no dates. Every
query is a `SELECT count(*)`; nothing here can print a person. Read-only:
this script does not UPDATE or DELETE a single row — remediation, if any,
is separate, explicit, human-approved follow-up work, not something this
audit performs.

Run in-environment (the production database is firewalled from developer
machines, and that firewall is not something this script asks anyone to
change):

    az containerapp job create ... --args "python" "-m" "scripts.lab_155_audit"
"""

from __future__ import annotations

import os
import sys

import sqlalchemy as sa

HEMOGLOBIN_ALLOWED_UNITS = ("g/dl", "g/l")
_NORM = "lower(replace(replace({col}, ' ', ''), '×', 'x'))"

# Postgres regex: the first number at the start of the stored range string
# ("130–170" or "130-170" -> "130"), and the number after the dash for the
# high bound. NULL-safe — a range that doesn't match this shape yields NULL
# and the comparison is simply not counted (never a false positive).
_LOW_BOUND = r"(substring({col} from '^([0-9]+\.?[0-9]*)'))::numeric"
_HIGH_BOUND = r"(substring({col} from '[-–—]\s*([0-9]+\.?[0-9]*)$'))::numeric"


def _count(conn, sql: str, **params) -> int:
    return int(conn.execute(sa.text(sql), params).scalar() or 0)


def main() -> int:
    url = os.getenv("MCP_DATABASE_URL")
    if not url:
        print("MCP_DATABASE_URL is not set", file=sys.stderr)
        return 2
    engine = sa.create_engine(url)

    lab_unit = _NORM.format(col="unit")
    live = "deleted_at IS NULL"

    with engine.connect() as conn:
        rows: list[tuple[str, int]] = []

        rows.append(
            (
                "lab_results: canonical=hemoglobin with a unit outside {g/dL, g/L}"
                " (now reads NEEDS_REVIEW per #155 item 2 — verify this is expected"
                " before treating volume as a regression)",
                _count(
                    conn,
                    f"SELECT count(*) FROM lab_results WHERE {live} "
                    f"AND lower(canonical_name)='hemoglobin' AND unit IS NOT NULL "
                    f"AND NOT ({lab_unit} = ANY(:u))",
                    u=list(HEMOGLOBIN_ALLOWED_UNITS),
                ),
            )
        )
        rows.append(
            (
                "lab_results: canonical=hemoglobin, unit=g/L (pre-#155, stored"
                " unconverted — now correctly converts to g/dL on read)",
                _count(
                    conn,
                    f"SELECT count(*) FROM lab_results WHERE {live} "
                    f"AND lower(canonical_name)='hemoglobin' AND {lab_unit}='g/l'",
                ),
            )
        )
        rows.append(
            (
                "lab_results: canonical=hemoglobin with NULL unit"
                " (already NEEDS_REVIEW pre- and post-#155 — no behaviour change)",
                _count(
                    conn,
                    f"SELECT count(*) FROM lab_results WHERE {live} "
                    "AND lower(canonical_name)='hemoglobin' AND unit IS NULL",
                ),
            )
        )

        # Heuristic only — see module docstring. Candidate, not confirmed.
        low = _LOW_BOUND.format(col="original_reference_range")
        high = _HIGH_BOUND.format(col="original_reference_range")
        for analyte in ("hemoglobin", "wbc", "platelet", "hematocrit"):
            rows.append(
                (
                    f"lab_results: canonical={analyte}, value equals a bound parsed"
                    " from its own original_reference_range (#155 range-as-value"
                    " shape — CANDIDATE, not confirmed; do not auto-remediate)",
                    _count(
                        conn,
                        f"SELECT count(*) FROM lab_results WHERE {live} "
                        "AND lower(canonical_name)=:analyte "
                        "AND value IS NOT NULL AND original_reference_range IS NOT NULL "
                        f"AND (value = {low} OR value = {high})",
                        analyte=analyte,
                    ),
                )
            )

        print("=== #155 RANGE-AS-VALUE + HEMOGLOBIN UNIT AUDIT (counts only, no PHI) ===")
        for label, n in rows:
            print(f"  {n:>6}  {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
