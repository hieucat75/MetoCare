"""Integration tests for the K1 Medication Knowledge Repository migration.

Run against a REAL PostgreSQL instance (not SQLite) because CHECK constraints
and partial unique indexes must be verified against the target production
dialect. Self-contained — does not import helpers from
test_medication_p0_migrations.py (matches this test package's existing
one-file-per-migration convention).

Usage (local):
    POSTGRES_TEST_URL="postgresql://mcp:mcp_dev_only@127.0.0.1:5544/mcp_test" \
    pytest tests/integration/test_medication_k1_knowledge_migration.py -v -m integration

Scope: EC-01 (ADR-13 schema) + EC-02 (ADR-01 schema) only. No clinical
content, no API, no frontend, no AI wiring — see
docs/medication-management/MEDICATION_K1_EXIT_CRITERIA.md.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")
K1_HEAD = "k1_m01_knowledge_schema"
PRE_K1_BASE = "merge_c1m08_p0med"

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if not POSTGRES_TEST_URL:
        pytest.skip(
            "POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests."
        )


def _make_alembic_config(db_url: str) -> Config:
    """Alembic Config wired to db_url, with the get_settings() lru_cache clear
    and MCP_DATABASE_URL patch required so alembic/env.py picks it up (see
    test_medication_p0_migrations.py's fixed helper — same fix applied here
    directly since get_settings() is process-global and cached)."""
    os.environ["MCP_DATABASE_URL"] = db_url
    from app.core.config import get_settings

    get_settings.cache_clear()

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Generator[sa.Engine, None, None]:
    _require_postgres()
    engine = sa.create_engine(POSTGRES_TEST_URL, echo=False, future=True)
    with engine.connect() as conn:
        assert conn.dialect.name == "postgresql", (
            f"Integration tests MUST run against PostgreSQL, got {conn.dialect.name!r}"
        )
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated_schema(pg_engine: sa.Engine) -> Generator[sa.Engine, None, None]:
    """Upgrade to the K1 head; downgrade to pre-K1 base after the module."""
    db_url = pg_engine.url.render_as_string(hide_password=False)
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, K1_HEAD)
    yield pg_engine
    command.downgrade(cfg, PRE_K1_BASE)


NEW_TABLES = (
    "drug_classes",
    "drug_ingredients",
    "drug_products",
    "drug_product_ingredients",
    "drug_product_names",
    "clinical_specialties",
    "knowledge_review_specialties",
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
    "drug_interactions",
)

KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
    "drug_interactions",
)


def _seed_class_and_ingredient(conn: sa.Connection) -> str:
    """Insert one drug_classes + one drug_ingredients row; return ingredient id."""
    class_id = str(uuid.uuid4())
    ingredient_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    conn.execute(
        sa.text(
            """
            INSERT INTO drug_classes (id, name, required_specialties, created_at, updated_at)
            VALUES (:id, :name, cast(:specialties as json), :now, :now)
            """
        ),
        {"id": class_id, "name": f"class-{class_id[:8]}", "specialties": "[]", "now": now},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO drug_ingredients
                (id, name_inn, drug_class_id, created_at, updated_at)
            VALUES (:id, :name, :class_id, :now, :now)
            """
        ),
        {
            "id": ingredient_id,
            "name": f"ingredient-{ingredient_id[:8]}",
            "class_id": class_id,
            "now": now,
        },
    )
    conn.commit()
    return ingredient_id


class TestSchemaExists:
    def test_all_thirteen_tables_created(self, migrated_schema: sa.Engine) -> None:
        inspector = sa.inspect(migrated_schema)
        existing = set(inspector.get_table_names())
        missing = [t for t in NEW_TABLES if t not in existing]
        assert not missing, f"Missing K1 tables: {missing}"

    def test_drug_catalog_untouched(self, migrated_schema: sa.Engine) -> None:
        """EC-03/EC-04 (catalog migration) is a separate PR — drug_catalog
        keeps its 41 seed rows unmodified by this schema-only migration."""
        with migrated_schema.connect() as conn:
            count = conn.execute(sa.text("SELECT COUNT(*) FROM drug_catalog")).scalar_one()
        assert count == 41


class TestStatusCheckConstraint:
    @pytest.mark.parametrize("table", KNOWLEDGE_TABLES)
    def test_invalid_status_rejected(self, migrated_schema: sa.Engine, table: str) -> None:
        with migrated_schema.connect() as conn:
            ingredient_id = None
            if table != "drug_interactions":
                ingredient_id = _seed_class_and_ingredient(conn)
            with pytest.raises(sa.exc.IntegrityError):
                _insert_minimal_row(conn, table, ingredient_id, status="bogus")
            conn.rollback()


class TestApprovedInvariantsCheck:
    @pytest.mark.parametrize("table", KNOWLEDGE_TABLES)
    def test_approved_without_provenance_rejected(
        self, migrated_schema: sa.Engine, table: str
    ) -> None:
        with migrated_schema.connect() as conn:
            ingredient_id = None
            if table != "drug_interactions":
                ingredient_id = _seed_class_and_ingredient(conn)
            with pytest.raises(sa.exc.IntegrityError):
                _insert_minimal_row(conn, table, ingredient_id, status="approved")
            conn.rollback()

    @pytest.mark.parametrize("table", KNOWLEDGE_TABLES)
    def test_approved_with_full_provenance_accepted(
        self, migrated_schema: sa.Engine, table: str
    ) -> None:
        with migrated_schema.connect() as conn:
            ingredient_id = None
            if table != "drug_interactions":
                ingredient_id = _seed_class_and_ingredient(conn)
            _insert_minimal_row(
                conn,
                table,
                ingredient_id,
                status="approved",
                with_provenance=True,
            )
            conn.commit()


class TestBusinessKeyUniqueness:
    def test_two_draft_rows_same_business_key_allowed(
        self, migrated_schema: sa.Engine
    ) -> None:
        """Drafts are not constrained — only 'approved' is (ADR-13)."""
        with migrated_schema.connect() as conn:
            ingredient_id = _seed_class_and_ingredient(conn)
            _insert_minimal_row(conn, "drug_usage", ingredient_id, status="draft")
            _insert_minimal_row(conn, "drug_usage", ingredient_id, status="draft")
            conn.commit()

    def test_two_approved_rows_same_business_key_rejected(
        self, migrated_schema: sa.Engine
    ) -> None:
        with migrated_schema.connect() as conn:
            ingredient_id = _seed_class_and_ingredient(conn)
            _insert_minimal_row(
                conn, "drug_usage", ingredient_id, status="approved", with_provenance=True
            )
            conn.commit()
            with pytest.raises(sa.exc.IntegrityError):
                _insert_minimal_row(
                    conn, "drug_usage", ingredient_id, status="approved", with_provenance=True
                )
            conn.rollback()

    def test_deprecated_and_approved_same_key_allowed(
        self, migrated_schema: sa.Engine
    ) -> None:
        """approved -> deprecated transition (service layer, future PR) must
        be able to coexist with a new approved row at the same business key —
        the partial index only constrains status='approved' rows."""
        with migrated_schema.connect() as conn:
            ingredient_id = _seed_class_and_ingredient(conn)
            _insert_minimal_row(
                conn, "drug_usage", ingredient_id, status="deprecated", with_provenance=True
            )
            _insert_minimal_row(
                conn, "drug_usage", ingredient_id, status="approved", with_provenance=True
            )
            conn.commit()


class TestForeignKeyEnforcement:
    def test_unknown_drug_ingredient_id_rejected(self, migrated_schema: sa.Engine) -> None:
        with migrated_schema.connect() as conn:
            with pytest.raises(sa.exc.IntegrityError):
                _insert_minimal_row(conn, "drug_usage", str(uuid.uuid4()), status="draft")
            conn.rollback()

    def test_drug_class_self_referential_fk(self, migrated_schema: sa.Engine) -> None:
        with migrated_schema.connect() as conn:
            parent_id = str(uuid.uuid4())
            child_id = str(uuid.uuid4())
            now = datetime.now(UTC)
            conn.execute(
                sa.text(
                    """
                    INSERT INTO drug_classes (id, name, required_specialties, created_at, updated_at)
                    VALUES (:id, :name, cast('[]' as json), :now, :now)
                    """
                ),
                {"id": parent_id, "name": f"parent-{parent_id[:8]}", "now": now},
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO drug_classes
                        (id, name, parent_class_id, required_specialties, created_at, updated_at)
                    VALUES (:id, :name, :parent_id, cast('[]' as json), :now, :now)
                    """
                ),
                {
                    "id": child_id,
                    "name": f"child-{child_id[:8]}",
                    "parent_id": parent_id,
                    "now": now,
                },
            )
            conn.commit()


class TestRollback:
    def test_downgrade_removes_all_new_tables(self, pg_engine: sa.Engine) -> None:
        db_url = pg_engine.url.render_as_string(hide_password=False)
        cfg = _make_alembic_config(db_url)
        command.upgrade(cfg, K1_HEAD)
        command.downgrade(cfg, PRE_K1_BASE)

        inspector = sa.inspect(pg_engine)
        existing = set(inspector.get_table_names())
        leftover = [t for t in NEW_TABLES if t in existing]
        assert not leftover, f"Tables survived downgrade: {leftover}"

        # Restore head so subsequent test classes in this module still see K1.
        command.upgrade(cfg, K1_HEAD)

    def test_upgrade_downgrade_upgrade_idempotent(self, pg_engine: sa.Engine) -> None:
        db_url = pg_engine.url.render_as_string(hide_password=False)
        cfg = _make_alembic_config(db_url)
        command.upgrade(cfg, K1_HEAD)
        command.downgrade(cfg, PRE_K1_BASE)
        command.upgrade(cfg, K1_HEAD)

        inspector = sa.inspect(pg_engine)
        existing = set(inspector.get_table_names())
        missing = [t for t in NEW_TABLES if t not in existing]
        assert not missing, f"Missing K1 tables after rehearsal cycle: {missing}"


def _insert_minimal_row(
    conn: sa.Connection,
    table: str,
    drug_ingredient_id: str | None,
    status: str,
    with_provenance: bool = False,
) -> None:
    """Insert a minimal row into any of the 6 knowledge tables for testing."""
    row_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    provenance = (
        {
            "source": "test-source",
            "version": "1.0.0",
            "evidence_level": "expert_opinion",
            "reviewed_by": "test-reviewer",
            "last_reviewed_at": now,
        }
        if with_provenance
        else {
            "source": None,
            "version": None,
            "evidence_level": None,
            "reviewed_by": None,
            "last_reviewed_at": None,
        }
    )

    table_specific = {
        "drug_usage": (
            "INSERT INTO drug_usage "
            "(id, drug_ingredient_id, locale, audience, content, source, version, "
            "evidence_level, reviewed_by, last_reviewed_at, status, status_changed_at, "
            "status_changed_by, authored_by, created_at, updated_at) "
            "VALUES (:id, :ing, 'vi', 'patient', 'content', :source, :version, "
            ":evidence_level, :reviewed_by, :last_reviewed_at, :status, :now, "
            "'tester', 'tester', :now, :now)"
        ),
        "drug_patient_education": (
            "INSERT INTO drug_patient_education "
            "(id, drug_ingredient_id, theme, locale, audience, content, source, version, "
            "evidence_level, reviewed_by, last_reviewed_at, status, status_changed_at, "
            "status_changed_by, authored_by, created_at, updated_at) "
            "VALUES (:id, :ing, 'general', 'vi', 'patient', 'content', :source, :version, "
            ":evidence_level, :reviewed_by, :last_reviewed_at, :status, :now, "
            "'tester', 'tester', :now, :now)"
        ),
        "drug_side_effects": (
            "INSERT INTO drug_side_effects "
            "(id, drug_ingredient_id, level, concept_code, description, source, version, "
            "evidence_level, reviewed_by, last_reviewed_at, status, status_changed_at, "
            "status_changed_by, authored_by, created_at, updated_at) "
            "VALUES (:id, :ing, 'common', 'nausea', 'desc', :source, :version, "
            ":evidence_level, :reviewed_by, :last_reviewed_at, :status, :now, "
            "'tester', 'tester', :now, :now)"
        ),
        "drug_monitoring": (
            "INSERT INTO drug_monitoring "
            "(id, drug_ingredient_id, parameter, patient_context, guidance, source, version, "
            "evidence_level, reviewed_by, last_reviewed_at, status, status_changed_at, "
            "status_changed_by, authored_by, created_at, updated_at) "
            "VALUES (:id, :ing, 'eGFR', 'baseline', 'guidance', :source, :version, "
            ":evidence_level, :reviewed_by, :last_reviewed_at, :status, :now, "
            "'tester', 'tester', :now, :now)"
        ),
        "drug_contraindications": (
            "INSERT INTO drug_contraindications "
            "(id, drug_ingredient_id, condition_type, condition_key, condition_detail, source, "
            "version, evidence_level, reviewed_by, last_reviewed_at, status, status_changed_at, "
            "status_changed_by, authored_by, created_at, updated_at) "
            "VALUES (:id, :ing, 'renal', 'egfr_lt_30', 'detail', :source, :version, "
            ":evidence_level, :reviewed_by, :last_reviewed_at, :status, :now, "
            "'tester', 'tester', :now, :now)"
        ),
        "drug_interactions": (
            "INSERT INTO drug_interactions "
            "(id, subject_a_type, subject_a_id, subject_b_type, subject_b_id, canonical_pair_key, "
            "source, version, evidence_level, reviewed_by, last_reviewed_at, status, "
            "status_changed_at, status_changed_by, authored_by, created_at, updated_at) "
            "VALUES (:id, 'ingredient', :ing_a, 'ingredient', :ing_b, :pair_key, "
            ":source, :version, :evidence_level, :reviewed_by, :last_reviewed_at, :status, :now, "
            "'tester', 'tester', :now, :now)"
        ),
    }

    params = {
        "id": row_id,
        "ing": drug_ingredient_id,
        "status": status,
        "now": now,
        **provenance,
    }
    if table == "drug_interactions":
        params["ing_a"] = str(uuid.uuid4())
        params["ing_b"] = str(uuid.uuid4())
        params["pair_key"] = row_id  # unique per test call unless testing collision

    conn.execute(sa.text(table_specific[table]), params)
