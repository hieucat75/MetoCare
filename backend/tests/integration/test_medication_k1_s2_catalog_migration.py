"""Integration tests for K1-S2: drug_catalog → relational core migration.

Run against a REAL PostgreSQL instance — see
test_medication_k1_knowledge_migration.py for why. Self-contained, following
this package's one-file-per-migration convention.

Usage (local):
    POSTGRES_TEST_URL="postgresql://mcp:mcp_dev_only@127.0.0.1:5544/mcp_test" \
    pytest tests/integration/test_medication_k1_s2_catalog_migration.py -v -m integration
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")
K1_S2_HEAD = "k1_s2_m01_catalog_migration"
K1_S1_BASE = "k1_m01_knowledge_schema"

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if not POSTGRES_TEST_URL:
        pytest.skip("POSTGRES_TEST_URL not set — skipping PostgreSQL integration tests.")


def _make_alembic_config(db_url: str) -> Config:
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
    """Upgrade to the K1-S2 head; downgrade to the K1-S1 base after the module."""
    db_url = pg_engine.url.render_as_string(hide_password=False)
    cfg = _make_alembic_config(db_url)
    command.upgrade(cfg, K1_S2_HEAD)
    yield pg_engine
    command.downgrade(cfg, K1_S1_BASE)


class TestZeroLoss:
    def test_41_of_41_migrated(self, migrated_schema: sa.Engine) -> None:
        with migrated_schema.connect() as conn:
            catalog_count = conn.execute(sa.text("SELECT COUNT(*) FROM drug_catalog")).scalar_one()
            product_count = conn.execute(sa.text("SELECT COUNT(*) FROM drug_products")).scalar_one()
            ingredient_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM drug_ingredients")
            ).scalar_one()
        assert catalog_count == 41
        assert product_count == 41
        assert ingredient_count == 41

    def test_source_catalog_untouched(self, migrated_schema: sa.Engine) -> None:
        """drug_catalog is read-only to this migration — row count and a spot
        check of a specific row's content must be unchanged."""
        with migrated_schema.connect() as conn:
            count = conn.execute(sa.text("SELECT COUNT(*) FROM drug_catalog")).scalar_one()
            metformin = conn.execute(
                sa.text(
                    "SELECT generic_name, drug_class FROM drug_catalog WHERE generic_name = 'metformin'"
                )
            ).one()
        assert count == 41
        assert metformin.generic_name == "metformin"
        assert metformin.drug_class == "biguanide"

    def test_every_product_has_display_name_matching_a_catalog_generic_name(
        self, migrated_schema: sa.Engine
    ) -> None:
        with migrated_schema.connect() as conn:
            unmatched = conn.execute(
                sa.text(
                    """
                    SELECT p.display_name FROM drug_products p
                    LEFT JOIN drug_catalog c ON c.generic_name = p.display_name
                    WHERE c.id IS NULL
                    """
                )
            ).fetchall()
        assert unmatched == []


class TestProductIngredientLinkage:
    def test_metformin_links_to_correct_ingredient_and_class(
        self, migrated_schema: sa.Engine
    ) -> None:
        with migrated_schema.connect() as conn:
            row = conn.execute(
                sa.text(
                    """
                    SELECT p.display_name, i.name_inn, c.name AS class_name
                    FROM drug_products p
                    JOIN drug_product_ingredients pi ON pi.drug_product_id = p.id
                    JOIN drug_ingredients i ON i.id = pi.drug_ingredient_id
                    JOIN drug_classes c ON c.id = i.drug_class_id
                    WHERE p.display_name = 'metformin'
                    """
                )
            ).one()
        assert row.name_inn == "metformin hydrochloride"
        assert row.class_name == "biguanide"

    def test_every_product_has_exactly_one_ingredient_link(
        self, migrated_schema: sa.Engine
    ) -> None:
        """Confirms the 1-ingredient-per-product assumption held for all 41 —
        this migration does not silently handle multi-ingredient rows."""
        with migrated_schema.connect() as conn:
            rows = conn.execute(
                sa.text(
                    """
                    SELECT p.display_name, COUNT(*) AS n
                    FROM drug_products p
                    JOIN drug_product_ingredients pi ON pi.drug_product_id = p.id
                    GROUP BY p.display_name
                    HAVING COUNT(*) != 1
                    """
                )
            ).fetchall()
        assert rows == []

    def test_shared_class_has_multiple_ingredients(self, migrated_schema: sa.Engine) -> None:
        """25 classes for 41 ingredients means some classes are shared
        (e.g. ARBs: losartan/valsartan/telmisartan/candesartan)."""
        with migrated_schema.connect() as conn:
            arb_ingredients = conn.execute(
                sa.text(
                    """
                    SELECT COUNT(*) FROM drug_ingredients i
                    JOIN drug_classes c ON c.id = i.drug_class_id
                    WHERE c.name = 'arb'
                    """
                )
            ).scalar_one()
        assert arb_ingredients == 4


class TestNameHandling:
    def test_name_appearing_in_multiple_lists_gets_one_row_per_type(
        self, migrated_schema: sa.Engine
    ) -> None:
        """Source lists 'Metformin' (verbatim casing) in both brand_names and
        vietnamese_common_names for the metformin product — must produce 2
        distinct rows (different name_type), not collapsed or duplicated
        within a type. Names are stored verbatim (not lowercased) — this
        query intentionally matches the source's exact casing."""
        with migrated_schema.connect() as conn:
            rows = conn.execute(
                sa.text(
                    """
                    SELECT pn.name_type, COUNT(*) AS n
                    FROM drug_product_names pn
                    JOIN drug_products p ON p.id = pn.drug_product_id
                    WHERE p.display_name = 'metformin' AND pn.name = 'Metformin'
                    GROUP BY pn.name_type
                    """
                )
            ).fetchall()
        by_type = {r.name_type: r.n for r in rows}
        assert by_type == {"brand": 1, "vietnamese_common": 1}

    def test_no_duplicate_name_rows_within_same_type(self, migrated_schema: sa.Engine) -> None:
        with migrated_schema.connect() as conn:
            dupes = conn.execute(
                sa.text(
                    """
                    SELECT drug_product_id, name, name_type, COUNT(*) AS n
                    FROM drug_product_names
                    GROUP BY drug_product_id, name, name_type
                    HAVING COUNT(*) > 1
                    """
                )
            ).fetchall()
        assert dupes == []

    def test_total_product_names_count(self, migrated_schema: sa.Engine) -> None:
        with migrated_schema.connect() as conn:
            count = conn.execute(sa.text("SELECT COUNT(*) FROM drug_product_names")).scalar_one()
        assert count == 255


class TestBusinessKeyConstraints:
    def test_duplicate_display_name_rejected(self, migrated_schema: sa.Engine) -> None:
        with migrated_schema.connect() as conn:
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(
                    sa.text(
                        "INSERT INTO drug_products "
                        "(id, display_name, prescription_required, country, is_active, "
                        "source_version, created_at, updated_at) "
                        "VALUES (gen_random_uuid()::text, 'metformin', true, 'VN', true, "
                        "'1.0.0', now(), now())"
                    )
                )
            conn.rollback()

    def test_duplicate_product_name_type_rejected(self, migrated_schema: sa.Engine) -> None:
        with migrated_schema.connect() as conn:
            product_id = conn.execute(
                sa.text("SELECT id FROM drug_products WHERE display_name = 'metformin'")
            ).scalar_one()
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(
                    sa.text(
                        "INSERT INTO drug_product_names "
                        "(id, drug_product_id, name, name_type, language, created_at, updated_at) "
                        "VALUES (gen_random_uuid()::text, :pid, 'Glucophage', 'brand', 'vi', now(), now())"
                    ),
                    {"pid": product_id},
                )
            conn.rollback()


class TestIdempotency:
    def test_rerunning_migration_logic_inserts_nothing_new(self, pg_engine: sa.Engine) -> None:
        """Calls the migration's core upsert function directly a second time
        against the already-migrated database — proves idempotency at the
        data level, not just via Alembic's once-per-revision tracking."""
        import importlib.util

        from sqlalchemy.orm import Session

        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        mig_path = os.path.join(
            backend_dir, "alembic", "versions", "k1_s2_m01_catalog_migration.py"
        )
        spec = importlib.util.spec_from_file_location("k1_s2_mig", mig_path)
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)

        with pg_engine.connect() as conn:
            before = {
                t: conn.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
                for t in (
                    "drug_classes",
                    "drug_ingredients",
                    "drug_products",
                    "drug_product_ingredients",
                    "drug_product_names",
                )
            }

        session = Session(bind=pg_engine)
        stats = mig.migrate_catalog_rows(session)
        session.close()

        assert stats["classes"] == 0
        assert stats["ingredients"] == 0
        assert stats["products"] == 0
        assert stats["product_names"] == 0

        with pg_engine.connect() as conn:
            after = {
                t: conn.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
                for t in before
            }
        assert before == after


class TestRollback:
    def test_downgrade_removes_all_migrated_rows_but_keeps_catalog(
        self, pg_engine: sa.Engine
    ) -> None:
        db_url = pg_engine.url.render_as_string(hide_password=False)
        cfg = _make_alembic_config(db_url)
        command.upgrade(cfg, K1_S2_HEAD)
        command.downgrade(cfg, K1_S1_BASE)

        with pg_engine.connect() as conn:
            counts = {
                t: conn.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
                for t in (
                    "drug_classes",
                    "drug_ingredients",
                    "drug_products",
                    "drug_product_ingredients",
                    "drug_product_names",
                )
            }
            catalog_count = conn.execute(sa.text("SELECT COUNT(*) FROM drug_catalog")).scalar_one()

        assert all(v == 0 for v in counts.values()), counts
        assert catalog_count == 41

        command.upgrade(cfg, K1_S2_HEAD)

    def test_upgrade_downgrade_upgrade_idempotent(self, pg_engine: sa.Engine) -> None:
        db_url = pg_engine.url.render_as_string(hide_password=False)
        cfg = _make_alembic_config(db_url)
        command.upgrade(cfg, K1_S2_HEAD)
        command.downgrade(cfg, K1_S1_BASE)
        command.upgrade(cfg, K1_S2_HEAD)

        with pg_engine.connect() as conn:
            counts = {
                t: conn.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
                for t in ("drug_classes", "drug_ingredients", "drug_products", "drug_product_names")
            }
        assert counts == {
            "drug_classes": 25,
            "drug_ingredients": 41,
            "drug_products": 41,
            "drug_product_names": 255,
        }
