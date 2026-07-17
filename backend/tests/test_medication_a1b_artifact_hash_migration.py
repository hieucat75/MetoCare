"""Alembic migration tests: k1_a1b_artifact_hash (adds `artifact_hash` to the
5 knowledge tables for the A1b orchestrator's idempotency design).

Follows tests/test_migrations.py's own subprocess-based convention: each test
runs `alembic upgrade`/`downgrade` against a throwaway SQLite file (always)
or a real Postgres instance (opt-in via MCP_TEST_POSTGRES_URL). Synthetic
fixtures only — never real clinical content.
"""

from __future__ import annotations

import os
import pathlib
import sqlite3
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
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


def _sqlite_columns(path: pathlib.Path, table: str) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


def test_single_migration_head() -> None:
    """Exactly one Alembic head must exist — a second, unmerged head is a
    branching bug (the A1b migration must chain onto the real tip, not
    fork it)."""
    result = _alembic(["heads"], "sqlite:///:memory:")
    assert result.returncode == 0, result.stderr
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, f"expected exactly one Alembic head, got: {heads!r}"


def test_sqlite_upgrade_adds_nullable_artifact_hash_to_all_five_tables(tmp_path) -> None:
    db = tmp_path / "mig.sqlite3"
    url = f"sqlite:///{db}"

    up = _alembic(["upgrade", "head"], url)
    assert up.returncode == 0, up.stderr

    for table in _KNOWLEDGE_TABLES:
        assert "artifact_hash" in _sqlite_columns(db, table), (
            f"artifact_hash missing from {table} after upgrade"
        )


def test_sqlite_upgrade_against_preexisting_row_leaves_hash_null_no_fake_backfill(
    tmp_path,
) -> None:
    """The core invariant this migration must never violate: a row written
    BEFORE this migration ran must have `artifact_hash IS NULL` after
    upgrade — never a fabricated/empty-string/sentinel value."""
    db = tmp_path / "mig.sqlite3"
    url = f"sqlite:///{db}"

    up = _alembic(["upgrade", "k1_a1b_f2_specialty_seed"], url)
    assert up.returncode == 0, up.stderr

    con = sqlite3.connect(db)
    try:
        drug_class_id = str(uuid.uuid4())
        ingredient_id = str(uuid.uuid4())
        row_id = str(uuid.uuid4())
        con.execute(
            "INSERT INTO drug_classes (id, name, required_specialties, created_at, updated_at) "
            "VALUES (?, ?, '[]', datetime('now'), datetime('now'))",
            (drug_class_id, f"pre-existing-class-{uuid.uuid4().hex[:8]}"),
        )
        con.execute(
            "INSERT INTO drug_ingredients (id, name_inn, drug_class_id, created_at, updated_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            (ingredient_id, f"pre-existing-ingredient-{uuid.uuid4().hex[:8]}", drug_class_id),
        )
        con.execute(
            "INSERT INTO drug_side_effects "
            "(id, drug_ingredient_id, concept_code, label, frequency, action_level, "
            "description, version, source, evidence_level, status, authored_by, "
            "status_changed_by, status_changed_at, created_at, updated_at) "
            "VALUES (?, ?, 'pre_existing_effect', 'Label', 'common', 'self_monitor', "
            "'desc', '1.0.0', 'src', 'moderate', 'draft', 'legacy', 'legacy', "
            "datetime('now'), datetime('now'), datetime('now'))",
            (row_id, ingredient_id),
        )
        con.commit()
    finally:
        con.close()

    up2 = _alembic(["upgrade", "k1_a1b_artifact_hash"], url)
    assert up2.returncode == 0, up2.stderr

    con = sqlite3.connect(db)
    try:
        result = con.execute(
            "SELECT artifact_hash FROM drug_side_effects WHERE id = ?", (row_id,)
        ).fetchone()
    finally:
        con.close()
    assert result is not None
    assert result[0] is None, (
        "pre-existing row's artifact_hash must be NULL after upgrade — "
        "never a fabricated backfill value"
    )


def test_sqlite_downgrade_drops_exactly_the_five_columns(tmp_path) -> None:
    db = tmp_path / "mig.sqlite3"
    url = f"sqlite:///{db}"

    up = _alembic(["upgrade", "head"], url)
    assert up.returncode == 0, up.stderr

    down = _alembic(["downgrade", "k1_a1b_f2_specialty_seed"], url)
    assert down.returncode == 0, down.stderr

    for table in _KNOWLEDGE_TABLES:
        assert "artifact_hash" not in _sqlite_columns(db, table), (
            f"artifact_hash still present on {table} after downgrade"
        )


def test_sqlite_full_upgrade_downgrade_reupgrade_roundtrip(tmp_path) -> None:
    db = tmp_path / "mig.sqlite3"
    url = f"sqlite:///{db}"

    assert _alembic(["upgrade", "head"], url).returncode == 0
    assert _alembic(["downgrade", "base"], url).returncode == 0
    reup = _alembic(["upgrade", "head"], url)
    assert reup.returncode == 0, reup.stderr

    for table in _KNOWLEDGE_TABLES:
        assert "artifact_hash" in _sqlite_columns(db, table)


_PG_URL = os.environ.get("MCP_TEST_POSTGRES_URL")


@pytest.mark.skipif(not _PG_URL, reason="No Postgres instance; set MCP_TEST_POSTGRES_URL to run")
def test_postgres_upgrade_downgrade_roundtrip_no_fake_backfill() -> None:
    up = _alembic(["upgrade", "k1_a1b_f2_specialty_seed"], _PG_URL)
    assert up.returncode == 0, up.stderr

    engine = create_engine(_PG_URL, future=True)
    try:
        drug_class_id = str(uuid.uuid4())
        ingredient_id = str(uuid.uuid4())
        row_id = str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO drug_classes (id, name, required_specialties, "
                    "created_at, updated_at) VALUES (:id, :name, '[]'::jsonb, now(), now())"
                ),
                {"id": drug_class_id, "name": f"pre-existing-class-{uuid.uuid4().hex[:8]}"},
            )
            conn.execute(
                text(
                    "INSERT INTO drug_ingredients (id, name_inn, drug_class_id, "
                    "created_at, updated_at) VALUES (:id, :name, :cls, now(), now())"
                ),
                {
                    "id": ingredient_id,
                    "name": f"pre-existing-ingredient-{uuid.uuid4().hex[:8]}",
                    "cls": drug_class_id,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO drug_side_effects "
                    "(id, drug_ingredient_id, concept_code, label, frequency, "
                    "action_level, description, version, source, evidence_level, "
                    "status, authored_by, status_changed_by, status_changed_at, "
                    "created_at, updated_at) "
                    "VALUES (:id, :ing, 'pre_existing_effect', 'Label', 'common', "
                    "'self_monitor', 'desc', '1.0.0', 'src', 'moderate', 'draft', "
                    "'legacy', 'legacy', now(), now(), now())"
                ),
                {"id": row_id, "ing": ingredient_id},
            )

        up2 = _alembic(["upgrade", "k1_a1b_artifact_hash"], _PG_URL)
        assert up2.returncode == 0, up2.stderr

        with engine.begin() as conn:
            for table in _KNOWLEDGE_TABLES:
                cols = {
                    r[0]
                    for r in conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = :t"
                        ),
                        {"t": table},
                    )
                }
                assert "artifact_hash" in cols, f"artifact_hash missing on {table}"

            hash_value = conn.execute(
                text("SELECT artifact_hash FROM drug_side_effects WHERE id = :id"),
                {"id": row_id},
            ).scalar()
            assert hash_value is None, (
                "pre-existing Postgres row's artifact_hash must be NULL after "
                "upgrade — never a fabricated backfill value"
            )

        down = _alembic(["downgrade", "k1_a1b_f2_specialty_seed"], _PG_URL)
        assert down.returncode == 0, down.stderr

        with engine.begin() as conn:
            for table in _KNOWLEDGE_TABLES:
                cols = {
                    r[0]
                    for r in conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = :t"
                        ),
                        {"t": table},
                    )
                }
                assert "artifact_hash" not in cols, f"artifact_hash still present on {table}"
    finally:
        engine.dispose()
        _alembic(["downgrade", "base"], _PG_URL)
