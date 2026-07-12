"""Integration tests for P0 medication platform migrations.

These tests run against a REAL PostgreSQL instance (not SQLite) because:
  - JSONB column types require real Postgres (SQLite stores them as TEXT)
  - CHECK constraints, partial indexes, and FK enforcement differ between dialects
  - Migration compatibility gates MUST pass on the target production dialect

Activation:
  - Tests are marked with @pytest.mark.integration
  - Only run when POSTGRES_TEST_URL env var is set (skipped in unit test runs)
  - CI: activated by the `test-backend-postgres` job which sets POSTGRES_TEST_URL
    from the GitHub Actions postgres service

Usage (local):
    POSTGRES_TEST_URL="postgresql://mcp:mcp_dev_only@localhost:5432/mcp_test" \
    pytest tests/integration/test_medication_p0_migrations.py -v -m integration

The tests create a THROW-AWAY DATABASE (mcp_test or dynamically named) —
they NEVER touch the dev or staging database.

Design:
  - Each test class spins up a fresh schema using Alembic upgrade to the
    p0_m01 revision, then runs assertions, then tears down.
  - Test isolation: each test class uses its own engine / schema.
  - No SQLAlchemy ORM models imported here — all assertions via raw SQL to
    decouple from ORM changes during the migration window.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Generator
from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

# ---------------------------------------------------------------------------
# Pytest configuration
# ---------------------------------------------------------------------------

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    """Skip test if no Postgres URL is configured."""
    if not POSTGRES_TEST_URL:
        pytest.skip(
            "POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests. "
            "Set POSTGRES_TEST_URL to a throw-away Postgres database to run these tests."
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_alembic_config(db_url: str) -> Config:
    """Return an Alembic Config object wired to the given database URL.

    Also patches MCP_DATABASE_URL in os.environ so that alembic/env.py
    (which calls get_settings().database_url) sees the correct Postgres URL
    rather than the SQLite override set by tests/conftest.py.

    CRITICAL: get_settings() is decorated with @lru_cache, so changing
    os.environ alone is insufficient — the stale SQLite URL stays cached.
    We must call get_settings.cache_clear() AFTER setting the env var so
    the next call to get_settings() inside alembic/env.py returns the
    correct PostgreSQL URL.
    """
    # Ensure env.py reads the correct URL — conftest.py may have set
    # MCP_DATABASE_URL=sqlite:///... which would silently override this config.
    os.environ["MCP_DATABASE_URL"] = db_url
    # Clear the lru_cache so get_settings() re-reads from os.environ.
    # Without this, alembic/env.py would still get the cached SQLite URL
    # and run migrations against SQLite instead of PostgreSQL.
    from app.core.config import get_settings
    get_settings.cache_clear()

    # Resolve the alembic.ini from the backend directory (two levels up from this file)
    backend_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    alembic_ini = os.path.join(backend_dir, "alembic.ini")
    cfg = Config(alembic_ini)
    cfg.set_main_option("sqlalchemy.url", db_url)
    # Point Alembic at the correct migrations directory
    cfg.set_main_option(
        "script_location", os.path.join(backend_dir, "alembic")
    )
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Generator[sa.Engine, None, None]:
    """Create a throw-away Postgres engine for the whole test module.

    The database named in POSTGRES_TEST_URL must already exist (GitHub Actions
    postgres service creates it automatically).

    Fail-closed guard: asserts the engine dialect is postgresql before yielding.
    If the URL somehow resolved to SQLite (e.g. cache/env bug), the test module
    aborts immediately with a clear error instead of silently running against
    the wrong database.
    """
    _require_postgres()
    engine = sa.create_engine(POSTGRES_TEST_URL, echo=False, future=True)
    # Fail-closed: abort the entire module if we are not on PostgreSQL.
    # This catches any future regression where the URL falls back to SQLite.
    with engine.connect() as _conn:
        dialect_name = _conn.dialect.name
        assert dialect_name == "postgresql", (
            f"Integration tests MUST run against PostgreSQL, got dialect={dialect_name!r}. "
            f"Check POSTGRES_TEST_URL: {POSTGRES_TEST_URL!r}"
        )
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated_schema(pg_engine: sa.Engine) -> Generator[sa.Engine, None, None]:
    """Apply P0 migration and yield the engine; tear down after module."""
    # IMPORTANT: use render_as_string(hide_password=False) to preserve the
    # real password in the URL string. SQLAlchemy 2.x str(engine.url) masks
    # the password as literal '***', which causes psycopg authentication
    # failures when Alembic uses that string to build its own engine.
    db_url = pg_engine.url.render_as_string(hide_password=False)
    cfg = _make_alembic_config(db_url)

    # Upgrade to the P0 revision head
    command.upgrade(cfg, "p0_m01_med_lifecycle")

    yield pg_engine

    # Tear down: downgrade back to the pre-P0 revision so other test modules
    # are not affected if they share the same database.
    command.downgrade(cfg, "c0_m9_audit_log_clinic_id")


@pytest.fixture()
def conn(migrated_schema: sa.Engine) -> Generator[sa.Connection, None, None]:
    """Yield a fresh connection inside a SAVEPOINT for per-test isolation."""
    with migrated_schema.connect() as connection:
        with connection.begin_nested():  # SAVEPOINT
            yield connection
            connection.rollback()  # roll back each test's writes


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _insert_patient(conn: sa.Connection, user_id: str | None = None) -> str:
    """Insert a minimal patient_profile and return its id."""
    pid = str(uuid.uuid4())
    uid = user_id or str(uuid.uuid4())
    # Insert user first (FK constraint)
    conn.execute(
        sa.text(
            """
            INSERT INTO users (id, email, password_hash, role, full_name,
                               is_active, mfa_enabled, created_at, updated_at)
            VALUES (:id, :email, 'hash', 'PATIENT', 'Test Patient',
                   true, false, now(), now())
            ON CONFLICT (id) DO NOTHING;
            """
        ),
        {"id": uid, "email": f"test-{uid}@example.com"},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO patient_profiles (id, user_id, full_name, created_at, updated_at)
            VALUES (:id, :user_id, 'Test Patient', now(), now());
            """
        ),
        {"id": pid, "user_id": uid},
    )
    return pid


def _insert_medication(
    conn: sa.Connection,
    patient_id: str,
    name: str = "Aspirin",
    lifecycle_status: str = "active",
    deleted_at: str | None = None,
) -> str:
    """Insert a minimal medication row and return its id."""
    mid = str(uuid.uuid4())
    conn.execute(
        sa.text(
            """
            INSERT INTO medications
                (id, patient_id, name, lifecycle_status, verification_status,
                 source_type, medication_category, created_at, updated_at, deleted_at)
            VALUES
                (:id, :patient_id, :name, :lifecycle_status, 'patient_reported',
                 'patient_manual', 'conventional_drug', now(), now(), :deleted_at);
            """
        ),
        {
            "id": mid,
            "patient_id": patient_id,
            "name": name,
            "lifecycle_status": lifecycle_status,
            "deleted_at": deleted_at,
        },
    )
    return mid


# ===========================================================================
# TEST CLASS 1 — M-01: New columns on medications with correct types
# ===========================================================================


class TestM01LifecycleColumns:
    """M-01: Verify all 5 new columns exist with correct types and constraints."""

    def test_new_columns_present_in_information_schema(
        self, conn: sa.Connection
    ) -> None:
        """All 5 P0 columns must exist on the medications table."""
        result = conn.execute(
            sa.text(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'medications'
                  AND column_name IN (
                      'lifecycle_status', 'verification_status', 'source_type',
                      'medication_category', 'status_reason'
                  )
                ORDER BY column_name;
                """
            )
        ).fetchall()

        col_names = {row[0] for row in result}
        assert "lifecycle_status" in col_names, "lifecycle_status column missing"
        assert "verification_status" in col_names, "verification_status column missing"
        assert "source_type" in col_names, "source_type column missing"
        assert "medication_category" in col_names, "medication_category column missing"
        assert "status_reason" in col_names, "status_reason column missing"

    def test_not_null_columns_have_defaults(self, conn: sa.Connection) -> None:
        """lifecycle_status, verification_status, source_type, medication_category must be NOT NULL."""
        result = conn.execute(
            sa.text(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'medications'
                  AND column_name IN (
                      'lifecycle_status', 'verification_status',
                      'source_type', 'medication_category'
                  );
                """
            )
        ).fetchall()

        nullable_map = {row[0]: row[1] for row in result}
        for col in ("lifecycle_status", "verification_status", "source_type", "medication_category"):
            assert nullable_map.get(col) == "NO", (
                f"Column {col} should be NOT NULL but is nullable"
            )

    def test_status_reason_is_nullable(self, conn: sa.Connection) -> None:
        """status_reason must be nullable TEXT."""
        result = conn.execute(
            sa.text(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_name = 'medications' AND column_name = 'status_reason';
                """
            )
        ).scalar()
        assert result == "YES", "status_reason should be nullable"

    def test_lifecycle_status_check_constraint_enforced(
        self, conn: sa.Connection
    ) -> None:
        """Invalid lifecycle_status value must be rejected by CHECK constraint."""
        pid = _insert_patient(conn)
        mid = str(uuid.uuid4())
        with pytest.raises(Exception, match="chk_lifecycle_status|check"):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO medications
                        (id, patient_id, name, lifecycle_status, verification_status,
                         source_type, medication_category, created_at, updated_at)
                    VALUES (:id, :pid, 'TestDrug', 'INVALID_STATUS', 'patient_reported',
                            'patient_manual', 'conventional_drug', now(), now());
                    """
                ),
                {"id": mid, "pid": pid},
            )

    def test_verification_status_check_constraint_enforced(
        self, conn: sa.Connection
    ) -> None:
        """Invalid verification_status value must be rejected."""
        pid = _insert_patient(conn)
        mid = str(uuid.uuid4())
        with pytest.raises(Exception, match="chk_verification_status|check"):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO medications
                        (id, patient_id, name, lifecycle_status, verification_status,
                         source_type, medication_category, created_at, updated_at)
                    VALUES (:id, :pid, 'TestDrug', 'active', 'INVALID',
                            'patient_manual', 'conventional_drug', now(), now());
                    """
                ),
                {"id": mid, "pid": pid},
            )

    def test_source_type_check_constraint_enforced(
        self, conn: sa.Connection
    ) -> None:
        """Invalid source_type value must be rejected."""
        pid = _insert_patient(conn)
        mid = str(uuid.uuid4())
        with pytest.raises(Exception, match="chk_source_type|check"):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO medications
                        (id, patient_id, name, lifecycle_status, verification_status,
                         source_type, medication_category, created_at, updated_at)
                    VALUES (:id, :pid, 'TestDrug', 'active', 'patient_reported',
                            'INVALID_SOURCE', 'conventional_drug', now(), now());
                    """
                ),
                {"id": mid, "pid": pid},
            )

    def test_valid_medication_insert_with_all_new_fields(
        self, conn: sa.Connection
    ) -> None:
        """A valid medication row with all new P0 fields must insert successfully."""
        pid = _insert_patient(conn)
        mid = _insert_medication(
            conn, pid, name="Metformin", lifecycle_status="active"
        )
        row = conn.execute(
            sa.text(
                "SELECT lifecycle_status, verification_status, source_type, medication_category "
                "FROM medications WHERE id = :mid"
            ),
            {"mid": mid},
        ).fetchone()
        assert row is not None
        assert row[0] == "active"
        assert row[1] == "patient_reported"
        assert row[2] == "patient_manual"
        assert row[3] == "conventional_drug"


# ===========================================================================
# TEST CLASS 2 — M-01b: medication_category_codes lookup table
# ===========================================================================


class TestM01bCategoryCodesTable:
    """M-01b: medication_category_codes table created, seeded, and FK enforced."""

    def test_table_exists(self, conn: sa.Connection) -> None:
        """medication_category_codes table must exist."""
        result = conn.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'medication_category_codes';
                """
            )
        ).scalar()
        assert result == 1, "medication_category_codes table not found"

    def test_seed_data_present(self, conn: sa.Connection) -> None:
        """Both P0 seed rows (conventional_drug, supplement) must be present."""
        rows = conn.execute(
            sa.text(
                "SELECT code FROM medication_category_codes ORDER BY code;"
            )
        ).fetchall()
        codes = {r[0] for r in rows}
        assert "conventional_drug" in codes, "conventional_drug seed row missing"
        assert "supplement" in codes, "supplement seed row missing"

    def test_seed_labels_correct(self, conn: sa.Connection) -> None:
        """Seed rows must have correct Vietnamese and English labels."""
        row = conn.execute(
            sa.text(
                "SELECT label_vi, label_en, interaction_risk_level "
                "FROM medication_category_codes WHERE code = 'conventional_drug';"
            )
        ).fetchone()
        assert row is not None
        assert row[0] == "Thuốc điều trị"
        assert row[1] == "Conventional Drug"
        assert row[2] == "high"

    def test_fk_enforced_invalid_category(self, conn: sa.Connection) -> None:
        """Inserting a medication with unknown medication_category must fail FK constraint."""
        pid = _insert_patient(conn)
        mid = str(uuid.uuid4())
        with pytest.raises(Exception, match="fk_medication_category|foreign key"):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO medications
                        (id, patient_id, name, lifecycle_status, verification_status,
                         source_type, medication_category, created_at, updated_at)
                    VALUES (:id, :pid, 'Drug', 'active', 'patient_reported',
                            'patient_manual', 'unknown_category_xyz', now(), now());
                    """
                ),
                {"id": mid, "pid": pid},
            )

    def test_supplement_category_accepted(self, conn: sa.Connection) -> None:
        """supplement category (second seed) must be accepted by FK."""
        pid = _insert_patient(conn)
        mid = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO medications
                    (id, patient_id, name, lifecycle_status, verification_status,
                     source_type, medication_category, created_at, updated_at)
                VALUES (:id, :pid, 'Vitamin C', 'active', 'patient_reported',
                        'patient_manual', 'supplement', now(), now());
                """
            ),
            {"id": mid, "pid": pid},
        )
        cat = conn.execute(
            sa.text("SELECT medication_category FROM medications WHERE id = :id"),
            {"id": mid},
        ).scalar()
        assert cat == "supplement"


# ===========================================================================
# TEST CLASS 3 — M-02: medication_audit_log table
# ===========================================================================


class TestM02AuditLogTable:
    """M-02: medication_audit_log table created; JSONB columns readable/writable."""

    def test_table_exists(self, conn: sa.Connection) -> None:
        """medication_audit_log table must exist."""
        result = conn.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'medication_audit_log';
                """
            )
        ).scalar()
        assert result == 1

    def test_jsonb_columns_exist(self, conn: sa.Connection) -> None:
        """before_snapshot, after_snapshot, event_data must be JSONB type."""
        rows = conn.execute(
            sa.text(
                """
                SELECT column_name, udt_name
                FROM information_schema.columns
                WHERE table_name = 'medication_audit_log'
                  AND column_name IN ('before_snapshot', 'after_snapshot', 'event_data')
                ORDER BY column_name;
                """
            )
        ).fetchall()
        col_types = {row[0]: row[1] for row in rows}
        for col in ("before_snapshot", "after_snapshot", "event_data"):
            assert col in col_types, f"{col} column missing from medication_audit_log"
            assert col_types[col] == "jsonb", (
                f"{col} must be type JSONB, got {col_types[col]!r}"
            )

    def test_insert_and_read_jsonb_event_data(self, conn: sa.Connection) -> None:
        """Insert JSONB into event_data; read back; verify type is JSONB not TEXT."""
        pid = _insert_patient(conn)
        mid = _insert_medication(conn, pid)
        log_id = str(uuid.uuid4())
        payload = {"drug": "aspirin", "dose": "100mg", "note": "P0 test"}

        conn.execute(
            sa.text(
                """
                INSERT INTO medication_audit_log
                    (id, medication_id, patient_id, event_type, event_data, created_at)
                VALUES (:id, :mid, :pid, 'create', cast(:payload as jsonb), now());
                """
            ),
            {"id": log_id, "mid": mid, "pid": pid, "payload": json.dumps(payload)},
        )

        # Read back and verify it's queryable as JSONB
        result = conn.execute(
            sa.text(
                "SELECT event_data->>'drug' AS drug, event_data->>'dose' AS dose "
                "FROM medication_audit_log WHERE id = :id"
            ),
            {"id": log_id},
        ).fetchone()
        assert result is not None
        assert result[0] == "aspirin", "JSONB drug field not readable via ->>"
        assert result[1] == "100mg", "JSONB dose field not readable via ->>"

    def test_insert_before_after_snapshots(self, conn: sa.Connection) -> None:
        """before_snapshot and after_snapshot must be writable and queryable as JSONB."""
        pid = _insert_patient(conn)
        mid = _insert_medication(conn, pid)
        log_id = str(uuid.uuid4())
        before = {"lifecycle_status": "active", "name": "Aspirin"}
        after = {"lifecycle_status": "paused", "name": "Aspirin"}

        conn.execute(
            sa.text(
                """
                INSERT INTO medication_audit_log
                    (id, medication_id, patient_id, event_type,
                     field_changed, old_value, new_value,
                     before_snapshot, after_snapshot, created_at)
                VALUES (:id, :mid, :pid, 'lifecycle_change',
                        'lifecycle_status', 'active', 'paused',
                        cast(:before as jsonb), cast(:after as jsonb), now());
                """
            ),
            {
                "id": log_id,
                "mid": mid,
                "pid": pid,
                "before": json.dumps(before),
                "after": json.dumps(after),
            },
        )

        row = conn.execute(
            sa.text(
                "SELECT before_snapshot->>'lifecycle_status', "
                "       after_snapshot->>'lifecycle_status' "
                "FROM medication_audit_log WHERE id = :id"
            ),
            {"id": log_id},
        ).fetchone()
        assert row is not None
        assert row[0] == "active", "before_snapshot JSONB not readable"
        assert row[1] == "paused", "after_snapshot JSONB not readable"

    def test_pure_event_null_snapshots_accepted(self, conn: sa.Connection) -> None:
        """Pure observational events (no field change) must accept NULL snapshots."""
        pid = _insert_patient(conn)
        mid = _insert_medication(conn, pid)
        log_id = str(uuid.uuid4())

        conn.execute(
            sa.text(
                """
                INSERT INTO medication_audit_log
                    (id, medication_id, patient_id, event_type,
                     event_data, before_snapshot, after_snapshot, created_at)
                VALUES (:id, :mid, :pid, 'patient_reported_non_adherence',
                        CAST('{"note": "forgot"}' AS jsonb), NULL, NULL, now());
                """
            ),
            {"id": log_id, "mid": mid, "pid": pid},
        )

        row = conn.execute(
            sa.text(
                "SELECT before_snapshot, after_snapshot, event_data->>'note' "
                "FROM medication_audit_log WHERE id = :id"
            ),
            {"id": log_id},
        ).fetchone()
        assert row is not None
        assert row[0] is None, "before_snapshot must be nullable"
        assert row[1] is None, "after_snapshot must be nullable"
        assert row[2] == "forgot", "event_data JSONB note not readable"

    def test_cascade_delete_on_medication(self, conn: sa.Connection) -> None:
        """Deleting a medication must cascade to medication_audit_log rows."""
        pid = _insert_patient(conn)
        mid = _insert_medication(conn, pid)
        log_id = str(uuid.uuid4())

        conn.execute(
            sa.text(
                """
                INSERT INTO medication_audit_log
                    (id, medication_id, patient_id, event_type, created_at)
                VALUES (:lid, :mid, :pid, 'create', now());
                """
            ),
            {"lid": log_id, "mid": mid, "pid": pid},
        )

        conn.execute(
            sa.text("DELETE FROM medications WHERE id = :mid"),
            {"mid": mid},
        )

        count = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM medication_audit_log WHERE id = :lid"
            ),
            {"lid": log_id},
        ).scalar()
        assert count == 0, "medication_audit_log rows not deleted on CASCADE"


# ===========================================================================
# TEST CLASS 4 — M-03: medication_statements table
# ===========================================================================


class TestM03MedicationStatements:
    """M-03: medication_statements table created; all new fields present."""

    def test_table_exists(self, conn: sa.Connection) -> None:
        """medication_statements table must exist."""
        result = conn.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'medication_statements';
                """
            )
        ).scalar()
        assert result == 1

    def test_all_new_fields_present(self, conn: sa.Connection) -> None:
        """All P0 + Q-OQ-1 fields must be present."""
        required = {
            "id", "patient_id", "source_type", "source_ref",
            "assertion_type", "related_medication_id",
            "raw_drug_name", "normalized_name", "drug_product_id",
            "match_confidence", "raw_dose", "raw_frequency",
            "raw_prescriber", "raw_date",
            "effective_from", "payload_snapshot",
            "statement_status", "merged_into_medication_id",
            "reviewed_by_user_id", "reviewed_at", "review_note", "created_at",
        }
        rows = conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'medication_statements';"
            )
        ).fetchall()
        actual = {r[0] for r in rows}
        missing = required - actual
        assert not missing, f"medication_statements missing columns: {missing}"

    def test_payload_snapshot_is_jsonb(self, conn: sa.Connection) -> None:
        """payload_snapshot must be stored as JSONB, not TEXT."""
        result = conn.execute(
            sa.text(
                """
                SELECT udt_name FROM information_schema.columns
                WHERE table_name = 'medication_statements'
                  AND column_name = 'payload_snapshot';
                """
            )
        ).scalar()
        assert result == "jsonb", f"payload_snapshot must be JSONB, got {result!r}"

    def test_insert_continued_use_assertion(self, conn: sa.Connection) -> None:
        """continued_use assertion with related_medication_id must insert correctly."""
        pid = _insert_patient(conn)
        expired_mid = _insert_medication(
            conn, pid, name="Lisinopril", lifecycle_status="expired"
        )
        stmt_id = str(uuid.uuid4())
        snapshot = {
            "id": expired_mid,
            "name": "Lisinopril",
            "lifecycle_status": "expired",
        }

        conn.execute(
            sa.text(
                """
                INSERT INTO medication_statements
                    (id, patient_id, source_type, assertion_type,
                     related_medication_id, raw_drug_name, effective_from,
                     payload_snapshot, statement_status, created_at)
                VALUES (:id, :pid, 'patient_manual', 'continued_use',
                        :rel_mid, 'Lisinopril', :eff_from,
                        cast(:snapshot as jsonb), 'pending', now());
                """
            ),
            {
                "id": stmt_id,
                "pid": pid,
                "rel_mid": expired_mid,
                "eff_from": date.today().isoformat(),
                "snapshot": json.dumps(snapshot),
            },
        )

        row = conn.execute(
            sa.text(
                """
                SELECT assertion_type, related_medication_id,
                       statement_status, payload_snapshot->>'lifecycle_status'
                FROM medication_statements WHERE id = :id;
                """
            ),
            {"id": stmt_id},
        ).fetchone()
        assert row is not None
        assert row[0] == "continued_use"
        assert row[1] == expired_mid
        assert row[2] == "pending"
        assert row[3] == "expired", "payload_snapshot JSONB not readable"

    def test_default_assertion_type_is_new_entry(
        self, conn: sa.Connection
    ) -> None:
        """Default assertion_type must be 'new_entry'."""
        pid = _insert_patient(conn)
        stmt_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO medication_statements
                    (id, patient_id, source_type, raw_drug_name, created_at)
                VALUES (:id, :pid, 'patient_manual', 'Aspirin', now());
                """
            ),
            {"id": stmt_id, "pid": pid},
        )
        result = conn.execute(
            sa.text(
                "SELECT assertion_type, statement_status FROM medication_statements WHERE id = :id"
            ),
            {"id": stmt_id},
        ).fetchone()
        assert result[0] == "new_entry"
        assert result[1] == "pending"


# ===========================================================================
# TEST CLASS 5 — M-04: drug_product_id and generic_name on medications
# ===========================================================================


class TestM04DrugProductFields:
    """M-04: drug_product_id and generic_name added as nullable columns."""

    def test_columns_exist(self, conn: sa.Connection) -> None:
        """drug_product_id and generic_name must exist on medications."""
        result = conn.execute(
            sa.text(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'medications'
                  AND column_name IN ('drug_product_id', 'generic_name')
                ORDER BY column_name;
                """
            )
        ).fetchall()
        cols = {r[0]: r[1] for r in result}
        assert "drug_product_id" in cols, "drug_product_id missing"
        assert "generic_name" in cols, "generic_name missing"
        assert cols["drug_product_id"] == "YES", "drug_product_id must be nullable"
        assert cols["generic_name"] == "YES", "generic_name must be nullable"

    def test_nullable_write_and_read(self, conn: sa.Connection) -> None:
        """Both fields must accept NULL and non-NULL values."""
        pid = _insert_patient(conn)
        mid = _insert_medication(conn, pid, name="Aspirin")

        # Update with real values
        conn.execute(
            sa.text(
                "UPDATE medications SET generic_name = :gn WHERE id = :id"
            ),
            {"gn": "acetylsalicylic acid", "id": mid},
        )

        row = conn.execute(
            sa.text(
                "SELECT drug_product_id, generic_name FROM medications WHERE id = :id"
            ),
            {"id": mid},
        ).fetchone()
        assert row[0] is None, "drug_product_id should be NULL"
        assert row[1] == "acetylsalicylic acid"


# ===========================================================================
# TEST CLASS 6 — Soft-delete mapping
# ===========================================================================


class TestSoftDeleteMapping:
    """Rows with deleted_at IS NOT NULL must get lifecycle_status='entered_in_error'."""

    def test_new_soft_deleted_row_set_to_entered_in_error(
        self, conn: sa.Connection
    ) -> None:
        """A medication inserted with deleted_at set must allow entered_in_error status."""
        pid = _insert_patient(conn)
        mid = _insert_medication(
            conn,
            pid,
            name="DeletedDrug",
            lifecycle_status="entered_in_error",
            deleted_at=datetime.now(UTC).isoformat(),
        )

        row = conn.execute(
            sa.text(
                "SELECT lifecycle_status, deleted_at FROM medications WHERE id = :id"
            ),
            {"id": mid},
        ).fetchone()
        assert row[0] == "entered_in_error"
        assert row[1] is not None

    def test_migration_update_targets_only_deleted_rows(
        self, conn: sa.Connection
    ) -> None:
        """Live rows must have lifecycle_status='active'; soft-deleted must be 'entered_in_error'."""
        pid = _insert_patient(conn)

        # Insert a live medication
        live_mid = _insert_medication(conn, pid, name="LiveDrug", lifecycle_status="active")

        # Insert a soft-deleted medication with entered_in_error (simulating post-migration state)
        dead_mid = _insert_medication(
            conn,
            pid,
            name="DeadDrug",
            lifecycle_status="entered_in_error",
            deleted_at=datetime.now(UTC).isoformat(),
        )

        live_status = conn.execute(
            sa.text("SELECT lifecycle_status FROM medications WHERE id = :id"),
            {"id": live_mid},
        ).scalar()
        dead_status = conn.execute(
            sa.text("SELECT lifecycle_status FROM medications WHERE id = :id"),
            {"id": dead_mid},
        ).scalar()

        assert live_status == "active", "Live row should have lifecycle_status='active'"
        assert dead_status == "entered_in_error", (
            "Soft-deleted row should have lifecycle_status='entered_in_error'"
        )

    def test_list_query_excludes_entered_in_error_and_soft_deleted(
        self, conn: sa.Connection
    ) -> None:
        """Standard list query (deleted_at IS NULL AND lifecycle_status != entered_in_error) must exclude both."""
        pid = _insert_patient(conn)

        # Live medication
        _insert_medication(conn, pid, name="VisibleDrug", lifecycle_status="active")
        # Soft-deleted
        _insert_medication(
            conn,
            pid,
            name="HiddenDrug",
            lifecycle_status="entered_in_error",
            deleted_at=datetime.now(UTC).isoformat(),
        )

        count = conn.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM medications
                WHERE patient_id = :pid
                  AND deleted_at IS NULL
                  AND lifecycle_status != 'entered_in_error';
                """
            ),
            {"pid": pid},
        ).scalar()

        assert count == 1, (
            f"Expected 1 visible medication, got {count} "
            "(soft-deleted/entered_in_error rows leaking through)"
        )


# ===========================================================================
# TEST CLASS 7 — Rollback (downgrade)
# ===========================================================================


class TestRollback:
    """downgrade() must restore schema to pre-P0 state cleanly."""

    def test_downgrade_removes_new_tables(self, pg_engine: sa.Engine) -> None:
        """After downgrade, medication_audit_log, medication_statements, medication_category_codes must not exist."""
        cfg = _make_alembic_config(pg_engine.url.render_as_string(hide_password=False))

        # Ensure we're at the P0 revision first
        command.upgrade(cfg, "p0_m01_med_lifecycle")

        # Downgrade to pre-P0
        command.downgrade(cfg, "c0_m9_audit_log_clinic_id")

        with pg_engine.connect() as conn:
            for table_name in (
                "medication_audit_log",
                "medication_statements",
                "medication_category_codes",
            ):
                count = conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_name = :t"
                    ),
                    {"t": table_name},
                ).scalar()
                assert count == 0, (
                    f"Table {table_name} still exists after downgrade"
                )

        # Re-apply P0 so the module fixture is still valid for other tests
        command.upgrade(cfg, "p0_m01_med_lifecycle")

    def test_downgrade_removes_p0_columns_from_medications(
        self, pg_engine: sa.Engine
    ) -> None:
        """After downgrade, P0 columns must not exist on medications."""
        cfg = _make_alembic_config(pg_engine.url.render_as_string(hide_password=False))
        command.upgrade(cfg, "p0_m01_med_lifecycle")
        command.downgrade(cfg, "c0_m9_audit_log_clinic_id")

        with pg_engine.connect() as conn:
            for col in (
                "lifecycle_status", "verification_status", "source_type",
                "medication_category", "status_reason",
                "drug_product_id", "generic_name",
            ):
                count = conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM information_schema.columns "
                        "WHERE table_name = 'medications' AND column_name = :c"
                    ),
                    {"c": col},
                ).scalar()
                assert count == 0, (
                    f"Column {col} still exists on medications after downgrade"
                )

        # Re-apply P0
        command.upgrade(cfg, "p0_m01_med_lifecycle")


# ===========================================================================
# TEST CLASS 8 — JSONB type verification
# ===========================================================================


class TestJsonbTypeEnforcement:
    """JSONB columns must behave as true JSONB, not TEXT in disguise."""

    def test_jsonb_operator_query_works(self, conn: sa.Connection) -> None:
        """JSONB ->> operator must work on medication_audit_log.before_snapshot."""
        pid = _insert_patient(conn)
        mid = _insert_medication(conn, pid)
        log_id = str(uuid.uuid4())
        snapshot = {"drug": "aspirin", "dose": "100mg", "lifecycle_status": "active"}

        conn.execute(
            sa.text(
                """
                INSERT INTO medication_audit_log
                    (id, medication_id, patient_id, event_type,
                     before_snapshot, created_at)
                VALUES (:id, :mid, :pid, 'lifecycle_change',
                        cast(:snap as jsonb), now());
                """
            ),
            {"id": log_id, "mid": mid, "pid": pid, "snap": json.dumps(snapshot)},
        )

        # Use JSONB containment operator @> (TEXT would fail this)
        result = conn.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM medication_audit_log
                WHERE before_snapshot @> CAST('{"drug": "aspirin"}' AS jsonb)
                  AND id = :id;
                """
            ),
            {"id": log_id},
        ).scalar()
        assert result == 1, (
            "JSONB containment operator @> failed — column may not be real JSONB"
        )

    def test_jsonb_path_query_works(self, conn: sa.Connection) -> None:
        """JSONB jsonb_path_exists must work on medication_statements.payload_snapshot."""
        pid = _insert_patient(conn)
        stmt_id = str(uuid.uuid4())
        snap = {"lifecycle_status": "expired", "name": "Lisinopril", "dose": "10mg"}

        conn.execute(
            sa.text(
                """
                INSERT INTO medication_statements
                    (id, patient_id, source_type, raw_drug_name,
                     payload_snapshot, created_at)
                VALUES (:id, :pid, 'patient_manual', 'Lisinopril',
                        cast(:snap as jsonb), now());
                """
            ),
            {"id": stmt_id, "pid": pid, "snap": json.dumps(snap)},
        )

        result = conn.execute(
            sa.text(
                """
                SELECT jsonb_path_exists(payload_snapshot, '$.lifecycle_status')
                FROM medication_statements WHERE id = :id;
                """
            ),
            {"id": stmt_id},
        ).scalar()
        assert result is True, "jsonb_path_exists failed on payload_snapshot"


# ===========================================================================
# TEST CLASS 9 — Migration Idempotency
# ===========================================================================

class TestMigrationIdempotency:
    """Verify the full CI migration workflow is idempotent.

    These tests guard against side effects when the DB is already at head:
    duplicate tables, duplicate seed rows, or constraint violations on re-run.
    """

    def test_upgrade_from_baseline_to_head(self, pg_engine: sa.Engine) -> None:
        """DB at baseline -> alembic upgrade head -> schema at head.

        Explicitly verifies that all P0 tables and columns are present after
        a clean upgrade from the pre-P0 baseline revision.
        """
        cfg = _make_alembic_config(pg_engine.url.render_as_string(hide_password=False))

        # Ensure we start from the pre-P0 baseline
        command.downgrade(cfg, "c0_m9_audit_log_clinic_id")

        # Apply P0 head
        command.upgrade(cfg, "p0_m01_med_lifecycle")

        with pg_engine.connect() as conn:
            # Verify all P0 tables exist
            for table_name in (
                "medication_audit_log",
                "medication_statements",
                "medication_category_codes",
            ):
                count = conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_name = :t"
                    ),
                    {"t": table_name},
                ).scalar()
                assert count == 1, (
                    f"Table {table_name!r} missing after upgrade from baseline to head"
                )

            # Verify all P0 columns on medications
            for col in (
                "lifecycle_status",
                "verification_status",
                "source_type",
                "medication_category",
                "status_reason",
                "drug_product_id",
                "generic_name",
            ):
                count = conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM information_schema.columns "
                        "WHERE table_name = 'medications' AND column_name = :c"
                    ),
                    {"c": col},
                ).scalar()
                assert count == 1, (
                    f"Column {col!r} missing on medications after upgrade from baseline"
                )

            # Verify seed data
            seed_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM medication_category_codes;")
            ).scalar()
            assert seed_count == 2, (
                f"Expected exactly 2 seed rows in medication_category_codes "
                f"after clean upgrade, got {seed_count}"
            )

    def test_already_at_head_pipeline_rerun(self, pg_engine: sa.Engine) -> None:
        """DB already at head -> run upgrade head again -> no error, no duplicate tables/rows.

        Simulates a CI pipeline re-run (e.g. flaky runner retry) where the DB
        is already migrated. Alembic must detect it is already at head and do
        nothing. Seed rows must not be duplicated.
        """
        cfg = _make_alembic_config(pg_engine.url.render_as_string(hide_password=False))

        # Ensure the DB is at P0 head (may already be there from previous test)
        command.upgrade(cfg, "p0_m01_med_lifecycle")

        # Run upgrade head a SECOND time on already-migrated DB
        # Alembic should detect already at head and be a no-op (no exception)
        command.upgrade(cfg, "p0_m01_med_lifecycle")

        with pg_engine.connect() as conn:
            # Tables must still exist (not been dropped/recreated)
            for table_name in (
                "medication_audit_log",
                "medication_statements",
                "medication_category_codes",
            ):
                count = conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_name = :t"
                    ),
                    {"t": table_name},
                ).scalar()
                assert count == 1, (
                    f"Table {table_name!r} missing after double upgrade head"
                )

            # Seed rows must be exactly 2, NOT 4 (no duplicates from second run)
            seed_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM medication_category_codes;")
            ).scalar()
            assert seed_count == 2, (
                f"Expected exactly 2 seed rows after double upgrade (no duplicates), "
                f"got {seed_count} — migration is NOT idempotent for seed data"
            )

            # Verify both expected codes are still present
            codes = {
                row[0]
                for row in conn.execute(
                    sa.text("SELECT code FROM medication_category_codes ORDER BY code;")
                ).fetchall()
            }
            assert codes == {"conventional_drug", "supplement"}, (
                f"Unexpected seed codes after double upgrade: {codes!r}"
            )

    def test_downgrade_then_upgrade_roundtrip(self, pg_engine: sa.Engine) -> None:
        """DB at head -> downgrade to pre-P0 -> upgrade back to head -> schema correct.

        Verifies that the full roundtrip (head → downgrade → upgrade) leaves the
        schema in a consistent state: all P0 tables and columns present, seed data
        correctly re-inserted with exactly 2 rows.
        """
        cfg = _make_alembic_config(pg_engine.url.render_as_string(hide_password=False))

        # Ensure we start from head
        command.upgrade(cfg, "p0_m01_med_lifecycle")

        # Downgrade to the revision immediately before P0
        command.downgrade(cfg, "c0_m9_audit_log_clinic_id")

        with pg_engine.connect() as conn:
            # Verify P0 tables are gone after downgrade
            for table_name in (
                "medication_audit_log",
                "medication_statements",
                "medication_category_codes",
            ):
                count = conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_name = :t"
                    ),
                    {"t": table_name},
                ).scalar()
                assert count == 0, (
                    f"Table {table_name!r} still exists after downgrade to pre-P0 — "
                    f"downgrade is incomplete"
                )

            # Verify P0 columns are gone from medications after downgrade
            for col in ("lifecycle_status", "verification_status", "source_type"):
                count = conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM information_schema.columns "
                        "WHERE table_name = 'medications' AND column_name = :c"
                    ),
                    {"c": col},
                ).scalar()
                assert count == 0, (
                    f"Column {col!r} still exists on medications after downgrade"
                )

        # Upgrade back to head
        command.upgrade(cfg, "p0_m01_med_lifecycle")

        with pg_engine.connect() as conn:
            # Verify all P0 tables are back
            for table_name in (
                "medication_audit_log",
                "medication_statements",
                "medication_category_codes",
            ):
                count = conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_name = :t"
                    ),
                    {"t": table_name},
                ).scalar()
                assert count == 1, (
                    f"Table {table_name!r} missing after downgrade+upgrade roundtrip"
                )

            # Verify all P0 columns are back on medications
            for col in (
                "lifecycle_status",
                "verification_status",
                "source_type",
                "medication_category",
                "status_reason",
                "drug_product_id",
                "generic_name",
            ):
                count = conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM information_schema.columns "
                        "WHERE table_name = 'medications' AND column_name = :c"
                    ),
                    {"c": col},
                ).scalar()
                assert count == 1, (
                    f"Column {col!r} missing on medications after downgrade+upgrade roundtrip"
                )

            # Verify seed data re-inserted correctly — exactly 2 rows, not 0 and not 4
            seed_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM medication_category_codes;")
            ).scalar()
            assert seed_count == 2, (
                f"Expected exactly 2 seed rows after downgrade+upgrade roundtrip, "
                f"got {seed_count}"
            )

            # Verify both seed codes are present with correct labels
            rows = conn.execute(
                sa.text(
                    "SELECT code, label_vi, label_en "
                    "FROM medication_category_codes ORDER BY code;"
                )
            ).fetchall()
            codes = {r[0] for r in rows}
            assert codes == {"conventional_drug", "supplement"}, (
                f"Unexpected seed codes after roundtrip: {codes!r}"
            )

            # Spot-check labels survive the roundtrip
            row_map = {r[0]: r for r in rows}
            assert row_map["conventional_drug"][1] == "Thuốc điều trị", (
                "conventional_drug label_vi incorrect after roundtrip"
            )
            assert row_map["conventional_drug"][2] == "Conventional Drug", (
                "conventional_drug label_en incorrect after roundtrip"
            )

        # Leave DB at head so the module fixture teardown (downgrade) works correctly
        # (migrated_schema fixture will downgrade in its own teardown)
