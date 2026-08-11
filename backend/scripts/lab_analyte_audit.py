"""PHI-free audit of analyte/unit dimensional mismatches.

Production displayed one stored CBC row as `rbc 0.50 L/L` = "Nguy hiểm" on the
labs screen and "Rất thấp" on the metrics screen. The row was a hematocrit
fraction filed as a red cell count. Before any row is mutated we need to know how
many records carry that shape — and we need to know it without reading a single
patient identifier.

Emits COUNTS ONLY. No patient_id, no test_name, no values, no dates. Every query
is a `SELECT count(*)`; nothing here can print a person.

Run in-environment (the production database is firewalled from developer
machines, and that firewall is not something this script asks anyone to change):

    az containerapp job create ... --args "python" "-m" "scripts.lab_analyte_audit"
"""

from __future__ import annotations

import os
import sys

import sqlalchemy as sa

# Unit spellings, lowercased and space-stripped, grouped by the dimension they
# measure. Kept literal rather than imported so the audit reflects what is
# STORED, not what today's registry would accept.
FRACTION_UNITS = ("l/l", "%", "ratio")
COUNT_UNITS = ("10^12/l", "10*12/l", "10¹²/l", "t/l", "tera/l", "10^6/ul", "m/ul")

_NORM = "lower(replace(replace({col}, ' ', ''), '×', 'x'))"


def _count(conn, sql: str, **params) -> int:
    return int(conn.execute(sa.text(sql), params).scalar() or 0)


def main() -> int:
    url = os.getenv("MCP_DATABASE_URL")
    if not url:
        print("MCP_DATABASE_URL is not set", file=sys.stderr)
        return 2
    engine = sa.create_engine(url)

    lab_unit = _NORM.format(col="unit")
    hm_unit = _NORM.format(col="unit")
    live = "deleted_at IS NULL"

    with engine.connect() as conn:
        rows: list[tuple[str, int]] = []

        rows.append(
            (
                "lab_results: canonical=rbc with a VOLUME-FRACTION unit",
                _count(
                    conn,
                    f"SELECT count(*) FROM lab_results WHERE {live} "
                    f"AND lower(canonical_name)='rbc' AND {lab_unit} = ANY(:u)",
                    u=list(FRACTION_UNITS),
                ),
            )
        )
        rows.append(
            (
                "lab_results: canonical=hematocrit with a COUNT unit",
                _count(
                    conn,
                    f"SELECT count(*) FROM lab_results WHERE {live} "
                    f"AND lower(canonical_name)='hematocrit' AND {lab_unit} = ANY(:u)",
                    u=list(COUNT_UNITS),
                ),
            )
        )
        rows.append(
            (
                "lab_results: rbc value < 1.0 (an HCT fraction, not a cell count)",
                _count(
                    conn,
                    f"SELECT count(*) FROM lab_results WHERE {live} "
                    "AND lower(canonical_name)='rbc' AND value IS NOT NULL AND value < 1.0",
                ),
            )
        )
        rows.append(
            (
                "lab_results: rbc + fraction unit CARRYING a confident severity",
                _count(
                    conn,
                    f"SELECT count(*) FROM lab_results WHERE {live} "
                    f"AND lower(canonical_name)='rbc' AND {lab_unit} = ANY(:u) "
                    "AND lower(coalesce(status,'')) IN ('critical','low','high')",
                    u=list(FRACTION_UNITS),
                ),
            )
        )
        rows.append(
            (
                "lab_results: stored unit differs in dimension from original_unit",
                _count(
                    conn,
                    f"SELECT count(*) FROM lab_results WHERE {live} "
                    "AND lower(canonical_name) IN ('rbc','hematocrit') "
                    "AND original_unit IS NOT NULL AND unit IS NOT NULL "
                    f"AND {lab_unit} <> {_NORM.format(col='original_unit')}",
                ),
            )
        )
        rows.append(
            (
                "health_metrics: metric_type=rbc with a VOLUME-FRACTION unit",
                _count(
                    conn,
                    f"SELECT count(*) FROM health_metrics WHERE {live} "
                    f"AND lower(metric_type)='rbc' AND {hm_unit} = ANY(:u)",
                    u=list(FRACTION_UNITS),
                ),
            )
        )
        rows.append(
            (
                "health_metrics: metric_type=hematocrit with a COUNT unit",
                _count(
                    conn,
                    f"SELECT count(*) FROM health_metrics WHERE {live} "
                    f"AND lower(metric_type)='hematocrit' AND {hm_unit} = ANY(:u)",
                    u=list(COUNT_UNITS),
                ),
            )
        )
        rows.append(
            (
                "health_metrics: rbc value < 1.0",
                _count(
                    conn,
                    f"SELECT count(*) FROM health_metrics WHERE {live} "
                    "AND lower(metric_type)='rbc' AND value IS NOT NULL AND value < 1.0",
                ),
            )
        )

        rows.append(
            (
                "lab_results: canonical=hematocrit with a FRACTION unit (needs conversion)",
                _count(
                    conn,
                    f"SELECT count(*) FROM lab_results WHERE {live} "
                    f"AND lower(canonical_name)='hematocrit' AND {lab_unit} = ANY(:u)",
                    u=["l/l", "ratio", "v/v"],
                ),
            )
        )
        rows.append(
            (
                "lab_results: hematocrit value < 1.0 (an unconverted fraction)",
                _count(
                    conn,
                    f"SELECT count(*) FROM lab_results WHERE {live} "
                    "AND lower(canonical_name)='hematocrit' AND value IS NOT NULL AND value < 1.0",
                ),
            )
        )

        # Deterministically remediable subset: rbc + L/L + a plausible HCT
        # fraction. These are the ONLY rows a conversion may touch without
        # guessing which half of the analyte/unit pair was wrong.
        remediable = _count(
            conn,
            f"SELECT count(*) FROM lab_results WHERE {live} "
            f"AND lower(canonical_name)='rbc' AND {lab_unit}='l/l' "
            "AND value IS NOT NULL AND value > 0.15 AND value < 0.75",
        )

        print("=== ANALYTE/UNIT DIMENSIONAL AUDIT (counts only, no PHI) ===")
        for label, n in rows:
            print(f"  {n:>6}  {label}")
        print()
        print(f"  {remediable:>6}  DETERMINISTICALLY REMEDIABLE (rbc + L/L + 0.15<v<0.75)")
        print()
        total_unsafe = rows[0][1] + rows[1][1] + rows[5][1] + rows[6][1]
        print(f"  {total_unsafe:>6}  TOTAL rows a read-path guard must neutralise")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
