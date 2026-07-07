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


def _sqlite_fk_list(path: pathlib.Path, table: str) -> list[tuple]:
    con = sqlite3.connect(path)
    try:
        return list(con.execute(f"PRAGMA foreign_key_list({table})"))
    finally:
        con.close()


def _sqlite_index_names(path: pathlib.Path, table: str) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute(f"PRAGMA index_list({table})")}
    finally:
        con.close()


def _sqlite_columns(path: pathlib.Path, table: str) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


def test_t12_reviewed_by_user_id_fk_and_index_roundtrip(tmp_path):
    """t12_m1: reviewed_by_user_id must be a nullable FK to users.id with
    ON DELETE SET NULL, plus an index — and both must cleanly disappear on
    downgrade (finding 4)."""
    db = tmp_path / "t12_fk.sqlite3"
    url = f"sqlite:///{db}"

    up = _alembic(["upgrade", "head"], url)
    assert up.returncode == 0, up.stderr

    cols = _sqlite_columns(db, "meto_conversations")
    assert "reviewed_at" in cols
    assert "reviewed_by_user_id" in cols

    fks = _sqlite_fk_list(db, "meto_conversations")
    reviewer_fk = next((fk for fk in fks if fk[3] == "reviewed_by_user_id"), None)
    assert reviewer_fk is not None, "no FK found on reviewed_by_user_id"
    # PRAGMA foreign_key_list columns: (id, seq, table, from, to, on_update, on_delete, match)
    assert reviewer_fk[2] == "users"
    assert reviewer_fk[4] == "id"
    assert reviewer_fk[6] == "SET NULL"

    index_names = _sqlite_index_names(db, "meto_conversations")
    assert "ix_meto_conversations_reviewed_by_user_id" in index_names

    down = _alembic(["downgrade", "t11_m1_health_metric_original"], url)
    assert down.returncode == 0, down.stderr

    cols_after = _sqlite_columns(db, "meto_conversations")
    assert "reviewed_at" not in cols_after
    assert "reviewed_by_user_id" not in cols_after
    assert "ix_meto_conversations_reviewed_by_user_id" not in _sqlite_index_names(
        db, "meto_conversations"
    )


def test_all_revision_ids_fit_alembic_version_column():
    """Every migration's ``revision`` must fit Alembic's default
    ``alembic_version.version_num VARCHAR(32)`` column.

    SQLite never enforces VARCHAR length limits, so an oversized revision id
    passes every local/CI test silently and only fails on real Postgres —
    which is exactly what happened with a too-long id in production
    (StringDataRightTruncation on the version-stamp UPDATE, staging deploy
    2026-07-07). This test makes that failure mode visible on SQLite too.
    """
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    max_len = 32
    offenders: list[tuple[str, str, int]] = []

    for path in sorted(versions_dir.glob("*.py")):
        content = path.read_text()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("revision") and "=" in stripped and "down_revision" not in stripped:
                value = stripped.split("=", 1)[-1].strip().strip("'\"")
                if len(value) > max_len:
                    offenders.append((path.name, value, len(value)))
                break

    assert not offenders, (
        f"Revision id(s) exceed alembic_version.version_num VARCHAR({max_len}): "
        f"{offenders}"
    )


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

    # C5-bis: M3 must NOT contain 'encounters' FK in create_table (FK must be in M4b)
    m3_file = "t4_m3_add_recs_add_ai_clinical_recommendations.py"
    m3_content = (versions_dir / m3_file).read_text()
    assert "ForeignKeyConstraint" not in m3_content or "encounters.id" not in m3_content, (
        "C5-bis VIOLATED: M3 still contains FK -> encounters.id; "
        "this must be moved to M4b (after encounters table created)"
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
