"""Integration tests for K1-A1B-F1: structured references + drug_side_effects
frequency/action_level split.

Runs against a REAL PostgreSQL instance (not SQLite) — CHECK constraints,
partial unique indexes, and FK enforcement differ between dialects, and
migration compatibility gates MUST pass on the target production dialect.
Same convention as test_medication_p0_migrations.py /
test_medication_k1_knowledge_migration.py.

Activation: only runs when POSTGRES_TEST_URL is set (skipped in unit runs).

All rows inserted here are synthetic test fixtures, never real clinical
content — no code path in this file can reach status='approved' outside
this test's own throwaway assertions.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if not POSTGRES_TEST_URL:
        pytest.skip(
            "POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests. "
            "Set POSTGRES_TEST_URL to a throw-away Postgres database to run these tests."
        )


def _make_alembic_config(db_url: str) -> Config:
    os.environ["MCP_DATABASE_URL"] = db_url
    from app.core.config import get_settings

    get_settings.cache_clear()

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")
    cfg = Config(alembic_ini)
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Generator[sa.Engine, None, None]:
    _require_postgres()
    engine = sa.create_engine(POSTGRES_TEST_URL, echo=False, future=True)
    with engine.connect() as _conn:
        dialect_name = _conn.dialect.name
        assert dialect_name == "postgresql", (
            f"Integration tests MUST run against PostgreSQL, got dialect={dialect_name!r}."
        )
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated_schema(pg_engine: sa.Engine) -> Generator[sa.Engine, None, None]:
    db_url = pg_engine.url.render_as_string(hide_password=False)
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, "k1_a1b_f1_schema_complete")
    yield pg_engine
    # Downgrade all the way to the pre-K1 base, not just one step back to
    # k1_s2_m01_catalog_migration. This file sorts alphabetically before
    # test_medication_k1_knowledge_migration.py and
    # test_medication_k1_s2_catalog_migration.py, so when the whole
    # tests/integration/ suite runs together against one shared Postgres
    # instance (CI's actual behavior), leaving the DB mid-chain makes those
    # other files' own `command.upgrade(cfg, THEIR_OWN_TARGET)` calls silent
    # no-ops (their target is already "in the past" relative to current DB
    # state) — they then run against unexpected residual catalog data
    # instead of the pristine state they assume. Matching their own deepest
    # teardown convention (PRE_K1_BASE = "merge_c1m08_p0med") keeps this
    # file's presence invisible to sibling test modules regardless of
    # collection order.
    command.downgrade(cfg, "merge_c1m08_p0med")


@pytest.fixture()
def conn(migrated_schema: sa.Engine) -> Generator[sa.Connection, None, None]:
    with migrated_schema.connect() as connection:
        trans = connection.begin()
        yield connection
        trans.rollback()


def _make_ingredient(conn: sa.Connection) -> str:
    """Synthetic ingredient — never real clinical content."""
    suffix = uuid.uuid4().hex[:8]
    class_id = str(uuid.uuid4())
    ingredient_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO drug_classes (id, name, required_specialties, created_at, updated_at) "
            "VALUES (:id, :name, '[]', now(), now())"
        ),
        {"id": class_id, "name": f"test-class-{suffix}"},
    )
    conn.execute(
        sa.text(
            "INSERT INTO drug_ingredients (id, name_inn, drug_class_id, created_at, updated_at) "
            "VALUES (:id, :name_inn, :class_id, now(), now())"
        ),
        {"id": ingredient_id, "name_inn": f"test-ingredient-{suffix}", "class_id": class_id},
    )
    return ingredient_id


def _insert_side_effect(
    conn: sa.Connection,
    ingredient_id: str,
    *,
    concept_code: str = "test_symptom",
    frequency: str = "common",
    action_level: str = "self_monitor",
    status: str = "draft",
) -> str:
    row_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    conn.execute(
        sa.text(
            """INSERT INTO drug_side_effects
            (id, drug_ingredient_id, concept_code, label, frequency, action_level, description,
             status, status_changed_at, status_changed_by, authored_by, created_at, updated_at)
            VALUES (:id, :ing, :cc, 'synthetic label', :freq, :action, 'synthetic test description',
            :status, :now, 'test', 'test', :now, :now)"""
        ),
        {
            "id": row_id,
            "ing": ingredient_id,
            "cc": concept_code,
            "freq": frequency,
            "action": action_level,
            "status": status,
            "now": now,
        },
    )
    return row_id


class TestDrugReferences:
    def test_table_exists_with_expected_columns(self, conn: sa.Connection) -> None:
        cols = {
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='drug_references'"
                )
            ).fetchall()
        }
        assert {
            "id",
            "publisher",
            "title",
            "source_type",
            "url",
            "document_identifier",
            "publication_date",
            "source_version",
            "accessed_at",
        }.issubset(cols)

    def test_valid_reference_insert(self, conn: sa.Connection) -> None:
        conn.execute(
            sa.text(
                "INSERT INTO drug_references "
                "(id, publisher, title, source_type, url, publication_date, source_version, accessed_at) "
                "VALUES (:id, 'Test Publisher', 'Test Title', 'formulary', 'https://example.invalid/x', "
                "'2024-01-01', '1.0', '2026-01-01')"
            ),
            {"id": str(uuid.uuid4())},
        )

    def test_invalid_source_type_rejected(self, conn: sa.Connection) -> None:
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO drug_references "
                    "(id, publisher, title, source_type, url, publication_date, source_version, accessed_at) "
                    "VALUES (:id, 'p', 't', 'not_a_real_type', 'https://example.invalid/x', "
                    "'2024-01-01', '1.0', '2026-01-01')"
                ),
                {"id": str(uuid.uuid4())},
            )

    def test_missing_url_and_document_identifier_rejected(self, conn: sa.Connection) -> None:
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO drug_references "
                    "(id, publisher, title, source_type, publication_date, source_version, accessed_at) "
                    "VALUES (:id, 'p', 't', 'formulary', '2024-01-01', '1.0', '2026-01-01')"
                ),
                {"id": str(uuid.uuid4())},
            )

    def test_document_identifier_alone_accepted(self, conn: sa.Connection) -> None:
        conn.execute(
            sa.text(
                "INSERT INTO drug_references "
                "(id, publisher, title, source_type, document_identifier, publication_date, source_version, accessed_at) "
                "VALUES (:id, 'p', 't2', 'peer_reviewed', 'ISBN-000', '2024-01-01', '1.0', '2026-01-01')"
            ),
            {"id": str(uuid.uuid4())},
        )

    def test_duplicate_natural_key_rejected(self, conn: sa.Connection) -> None:
        params = {
            "publisher": "Dup Publisher",
            "title": "Dup Title",
            "publication_date": date(2024, 1, 1),
            "source_version": "1.0",
        }
        conn.execute(
            sa.text(
                "INSERT INTO drug_references "
                "(id, publisher, title, source_type, url, publication_date, source_version, accessed_at) "
                "VALUES (:id, :publisher, :title, 'formulary', 'https://example.invalid/a', "
                ":publication_date, :source_version, '2026-01-01')"
            ),
            {"id": str(uuid.uuid4()), **params},
        )
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO drug_references "
                    "(id, publisher, title, source_type, url, publication_date, source_version, accessed_at) "
                    "VALUES (:id, :publisher, :title, 'formulary', 'https://example.invalid/b', "
                    ":publication_date, :source_version, '2026-01-01')"
                ),
                {"id": str(uuid.uuid4()), **params},
            )


class TestKnowledgeReferenceLinks:
    def test_table_exists(self, conn: sa.Connection) -> None:
        result = conn.execute(
            sa.text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name='knowledge_reference_links'"
            )
        ).fetchone()
        assert result is not None

    def test_link_to_side_effect_succeeds(self, conn: sa.Connection) -> None:
        ingredient_id = _make_ingredient(conn)
        side_effect_id = _insert_side_effect(conn, ingredient_id)
        ref_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO drug_references "
                "(id, publisher, title, source_type, url, publication_date, source_version, accessed_at) "
                "VALUES (:id, 'p', 't', 'formulary', 'https://example.invalid/x', '2024-01-01', '1.0', '2026-01-01')"
            ),
            {"id": ref_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO knowledge_reference_links "
                "(id, knowledge_table, knowledge_row_id, drug_reference_id, created_at, updated_at) "
                "VALUES (:id, 'drug_side_effects', :row_id, :ref_id, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "row_id": side_effect_id, "ref_id": ref_id},
        )

    def test_invalid_knowledge_table_rejected(self, conn: sa.Connection) -> None:
        ref_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO drug_references "
                "(id, publisher, title, source_type, url, publication_date, source_version, accessed_at) "
                "VALUES (:id, 'p', 't', 'formulary', 'https://example.invalid/x', '2024-01-01', '1.0', '2026-01-01')"
            ),
            {"id": ref_id},
        )
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO knowledge_reference_links "
                    "(id, knowledge_table, knowledge_row_id, drug_reference_id, created_at, updated_at) "
                    "VALUES (:id, 'drug_interactions', :row_id, :ref_id, now(), now())"
                ),
                {"id": str(uuid.uuid4()), "row_id": str(uuid.uuid4()), "ref_id": ref_id},
            )

    def test_duplicate_link_rejected(self, conn: sa.Connection) -> None:
        ingredient_id = _make_ingredient(conn)
        side_effect_id = _insert_side_effect(conn, ingredient_id)
        ref_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO drug_references "
                "(id, publisher, title, source_type, url, publication_date, source_version, accessed_at) "
                "VALUES (:id, 'p', 't', 'formulary', 'https://example.invalid/x', '2024-01-01', '1.0', '2026-01-01')"
            ),
            {"id": ref_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO knowledge_reference_links "
                "(id, knowledge_table, knowledge_row_id, drug_reference_id, created_at, updated_at) "
                "VALUES (:id, 'drug_side_effects', :row_id, :ref_id, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "row_id": side_effect_id, "ref_id": ref_id},
        )
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO knowledge_reference_links "
                    "(id, knowledge_table, knowledge_row_id, drug_reference_id, created_at, updated_at) "
                    "VALUES (:id, 'drug_side_effects', :row_id, :ref_id, now(), now())"
                ),
                {"id": str(uuid.uuid4()), "row_id": side_effect_id, "ref_id": ref_id},
            )

    def test_deleting_referenced_row_is_restricted(self, conn: sa.Connection) -> None:
        ingredient_id = _make_ingredient(conn)
        side_effect_id = _insert_side_effect(conn, ingredient_id)
        ref_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO drug_references "
                "(id, publisher, title, source_type, url, publication_date, source_version, accessed_at) "
                "VALUES (:id, 'p', 't', 'formulary', 'https://example.invalid/x', '2024-01-01', '1.0', '2026-01-01')"
            ),
            {"id": ref_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO knowledge_reference_links "
                "(id, knowledge_table, knowledge_row_id, drug_reference_id, created_at, updated_at) "
                "VALUES (:id, 'drug_side_effects', :row_id, :ref_id, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "row_id": side_effect_id, "ref_id": ref_id},
        )
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(sa.text("DELETE FROM drug_references WHERE id = :id"), {"id": ref_id})


class TestSideEffectsFrequencyActionLevelSplit:
    def test_level_column_removed(self, conn: sa.Connection) -> None:
        cols = {
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='drug_side_effects'"
                )
            ).fetchall()
        }
        assert "level" not in cols
        assert {"label", "frequency", "action_level", "concept_code"}.issubset(cols)

    def test_valid_frequency_and_action_level_insert(self, conn: sa.Connection) -> None:
        ingredient_id = _make_ingredient(conn)
        _insert_side_effect(conn, ingredient_id, frequency="rare", action_level="urgent_medical_help")

    def test_invalid_frequency_rejected(self, conn: sa.Connection) -> None:
        ingredient_id = _make_ingredient(conn)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_side_effect(conn, ingredient_id, frequency="sometimes")

    def test_invalid_action_level_rejected(self, conn: sa.Connection) -> None:
        ingredient_id = _make_ingredient(conn)
        with pytest.raises(sa.exc.IntegrityError):
            _insert_side_effect(conn, ingredient_id, action_level="call_911")

    def test_rare_and_urgent_can_coexist(self, conn: sa.Connection) -> None:
        """The exact scenario the old single-enum model couldn't express."""
        ingredient_id = _make_ingredient(conn)
        row_id = _insert_side_effect(
            conn, ingredient_id, frequency="rare", action_level="urgent_medical_help"
        )
        row = conn.execute(
            sa.text("SELECT frequency, action_level FROM drug_side_effects WHERE id = :id"),
            {"id": row_id},
        ).fetchone()
        assert row == ("rare", "urgent_medical_help")

    def test_business_key_is_ingredient_and_concept_code_only(self, conn: sa.Connection) -> None:
        """Two APPROVED rows with the same concept_code for the same ingredient
        must be rejected, regardless of differing frequency/action_level —
        proving the business key no longer includes the old `level` column."""
        ingredient_id = _make_ingredient(conn)
        now = datetime.now(UTC)
        conn.execute(
            sa.text(
                """INSERT INTO drug_side_effects
                (id, drug_ingredient_id, concept_code, label, frequency, action_level, description,
                 status, status_changed_at, status_changed_by, authored_by, source, version,
                 evidence_level, reviewed_by, last_reviewed_at, created_at, updated_at)
                VALUES (:id, :ing, 'dup_symptom', 'label', 'common', 'self_monitor', 'desc',
                'approved', :now, 'reviewer', 'author', 'src', 'v1', 'moderate', 'reviewer', :now, :now, :now)"""
            ),
            {"id": str(uuid.uuid4()), "ing": ingredient_id, "now": now},
        )
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    """INSERT INTO drug_side_effects
                    (id, drug_ingredient_id, concept_code, label, frequency, action_level, description,
                     status, status_changed_at, status_changed_by, authored_by, source, version,
                     evidence_level, reviewed_by, last_reviewed_at, created_at, updated_at)
                    VALUES (:id, :ing, 'dup_symptom', 'label2', 'rare', 'urgent_medical_help', 'desc2',
                    'approved', :now, 'reviewer', 'author', 'src', 'v1', 'moderate', 'reviewer', :now, :now, :now)"""
                ),
                {"id": str(uuid.uuid4()), "ing": ingredient_id, "now": now},
            )


class TestRollback:
    def test_downgrade_removes_new_tables_and_restores_level(self, pg_engine: sa.Engine) -> None:
        db_url = pg_engine.url.render_as_string(hide_password=False)
        cfg = _make_alembic_config(db_url)
        command.upgrade(cfg, "k1_a1b_f1_schema_complete")
        command.downgrade(cfg, "k1_s2_m01_catalog_migration")

        with pg_engine.connect() as conn:
            tabs = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name IN ('drug_references','knowledge_reference_links')"
                    )
                ).fetchall()
            }
            assert tabs == set()

            cols = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='drug_side_effects'"
                    )
                ).fetchall()
            }
            assert "level" in cols
            assert not {"label", "frequency", "action_level"} & cols

        # Leave the DB at head for any subsequent test module reusing it.
        command.upgrade(cfg, "head")
