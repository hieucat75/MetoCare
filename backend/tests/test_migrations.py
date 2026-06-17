"""Alembic migration tests.

- SQLite (always): upgrade head -> downgrade base is clean and reversible. The
  TimescaleDB migration is a no-op on SQLite, so it must pass here too.
- PostgreSQL/TimescaleDB (opt-in via MCP_TEST_POSTGRES_URL): upgrade builds a
  real hypertable; ingest + trend query works. Skipped when no instance is set
  (Docker/TimescaleDB not available in every environment).
"""

from __future__ import annotations

import os
import pathlib
import sqlite3
import subprocess
import sys

import pytest

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_TABLES = (
    "users",
    "patient_profiles",
    "health_metrics",
    "consents",
    "audit_logs",
    "lab_results",
)


def _alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["MCP_DATABASE_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _sqlite_tables(path: pathlib.Path) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


T4_TABLES = (
    "ai_sessions",
    "ai_clinical_recommendations",
    "encounters",
    "care_plans",
    "booking_health_snapshots",
    "doctor_clinic",
)


def test_sqlite_upgrade_downgrade_roundtrip(tmp_path):
    db = tmp_path / "mig.sqlite3"
    url = f"sqlite:///{db}"

    up = _alembic(["upgrade", "head"], url)
    assert up.returncode == 0, up.stderr

    tables = _sqlite_tables(db)
    for t in CORE_TABLES:
        assert t in tables, f"missing table after upgrade: {t}"
    # T4 tables must also be present after upgrade
    for t in T4_TABLES:
        assert t in tables, f"T4 table missing after upgrade: {t}"
    assert "alembic_version" in tables

    down = _alembic(["downgrade", "base"], url)
    assert down.returncode == 0, down.stderr

    remaining = _sqlite_tables(db)
    # only alembic's bookkeeping table may remain
    assert remaining <= {"alembic_version"}, f"tables left after downgrade: {remaining}"


def test_migration_chain_order():
    """C5 fix: verify the migration chain has encounters BEFORE the encounter FK migration.

    Reads the migration files to confirm:
    - t4_m4_add_encs (creates encounters) comes before t4_m4b_enc_fk (adds encounter FK)
    - t4_m4b_enc_fk has down_revision = t4_m4_add_encs
    - t4_m0_role runs before t4_m1_ren_conv
    """
    versions_dir = BACKEND_ROOT / "alembic" / "versions"

    def _read_field(filename: str, field: str) -> str:
        content = (versions_dir / filename).read_text()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith(f"{field}:"):
                # revision: str = 't4_m4b_enc_fk'
                val = stripped.split("=", 1)[-1].strip().strip("'\"")
                return val
        raise AssertionError(f"{field} not found in {filename}")

    # C5: t4_m4b_enc_fk must depend on t4_m4_add_encs
    fk_down = _read_field("t4_m4b_enc_fk_add_encounter_fk_to_ai_sessions.py", "down_revision")
    assert fk_down == "t4_m4_add_encs", (
        f"C5 VIOLATED: t4_m4b_enc_fk down_revision should be 't4_m4_add_encs', got '{fk_down}'"
    )

    # C5: t4_m5 must depend on t4_m4b (not t4_m4 directly)
    m5_down = _read_field("t4_m5_add_cpln_add_care_plan_table.py", "down_revision")
    assert m5_down == "t4_m4b_enc_fk", (
        f"C5 VIOLATED: t4_m5 down_revision should be 't4_m4b_enc_fk', got '{m5_down}'"
    )

    # C6: t4_m0_role must run before t4_m1_ren_conv
    m1_file = "t4_m1_ren_conv_rename_ai_conversations_to_ai_sessions.py"
    m1_down = _read_field(m1_file, "down_revision")
    assert m1_down == "t4_m0_role", (
        f"C6 VIOLATED: t4_m1 down_revision should be 't4_m0_role', got '{m1_down}'"
    )


_PG_URL = os.environ.get("MCP_TEST_POSTGRES_URL")


@pytest.mark.skipif(not _PG_URL, reason="No TimescaleDB; set MCP_TEST_POSTGRES_URL to run")
def test_postgres_hypertable_ingest_and_trend():
    import datetime as dt

    from sqlalchemy import create_engine, text

    up = _alembic(["upgrade", "head"], _PG_URL)
    assert up.returncode == 0, up.stderr

    engine = create_engine(_PG_URL, future=True)
    try:
        with engine.begin() as conn:
            # health_metrics must now be a hypertable.
            is_ht = conn.execute(
                text(
                    "SELECT count(*) FROM timescaledb_information.hypertables "
                    "WHERE hypertable_name = 'health_metrics'"
                )
            ).scalar()
            assert is_ht == 1

            # ingest a few synthetic (non-PHI) points and query a trend window.
            base = dt.datetime(2026, 1, 1)
            for i in range(5):
                conn.execute(
                    text(
                        "INSERT INTO health_metrics "
                        "(id, patient_id, metric_type, value, measured_at, created_at, updated_at) "
                        "VALUES (:id, 'p1', 'fasting_glucose', :v, :ts, now(), now())"
                    ),
                    {"id": f"m{i}", "v": 90 + i, "ts": base + dt.timedelta(days=i)},
                )
            avg_val = conn.execute(
                text(
                    "SELECT avg(value) FROM health_metrics "
                    "WHERE patient_id='p1' AND metric_type='fasting_glucose'"
                )
            ).scalar()
            assert 90 <= float(avg_val) <= 95
    finally:
        engine.dispose()
        _alembic(["downgrade", "base"], _PG_URL)
