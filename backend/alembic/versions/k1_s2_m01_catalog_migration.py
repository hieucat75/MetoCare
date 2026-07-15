"""K1-S2-M01: migrate the 41-entry drug_catalog into the ADR-01 relational core.

Data-only migration. `drug_catalog` (DrugEntry) is READ ONLY — never modified,
never deleted, in upgrade or downgrade. This migration only populates
drug_classes / drug_ingredients / drug_products / drug_product_ingredients /
drug_product_names, all created empty by K1-M01 and never written to since.

No clinical content (ADR-13's six knowledge tables — untouched), no API, no
frontend, no AI, no drug_interactions, no Medication.drug_product_id backfill.
See docs/medication-management/MEDICATION_K1_S2_CATALOG_MIGRATION_REPORT.md
for the per-entry classification (all 41 migrated cleanly; universal
nullable gaps documented, not guessed around).

Idempotency: two DB-level UNIQUE constraints (drug_products.display_name,
drug_product_names(drug_product_id, name, name_type)) are added here as the
business keys the data loop relies on, so a duplicate-insert bug would be
caught by the database, not just trusted from the ORM's own existence
checks. Re-running upgrade() a second time inserts zero new rows (verified
by integration test).

Revision ID: k1_s2_m01_catalog_migration
Revises: k1_m01_knowledge_schema
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision: str = "k1_s2_m01_catalog_migration"
down_revision: str | None = "k1_m01_knowledge_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXPECTED_SOURCE_ROW_COUNT = 41


def _add_business_key_constraints() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("drug_products", schema=None) as batch_op:
            batch_op.create_unique_constraint(
                "uq_drug_products_display_name", ["display_name"]
            )
        with op.batch_alter_table("drug_product_names", schema=None) as batch_op:
            batch_op.create_unique_constraint(
                "uq_drug_product_names_product_name_type",
                ["drug_product_id", "name", "name_type"],
            )
    else:
        op.create_unique_constraint(
            "uq_drug_products_display_name", "drug_products", ["display_name"]
        )
        op.create_unique_constraint(
            "uq_drug_product_names_product_name_type",
            "drug_product_names",
            ["drug_product_id", "name", "name_type"],
        )


def _drop_business_key_constraints() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("drug_product_names", schema=None) as batch_op:
            batch_op.drop_constraint(
                "uq_drug_product_names_product_name_type", type_="unique"
            )
        with op.batch_alter_table("drug_products", schema=None) as batch_op:
            batch_op.drop_constraint("uq_drug_products_display_name", type_="unique")
    else:
        op.drop_constraint(
            "uq_drug_product_names_product_name_type",
            "drug_product_names",
            type_="unique",
        )
        op.drop_constraint(
            "uq_drug_products_display_name", "drug_products", type_="unique"
        )


def migrate_catalog_rows(session: Session) -> dict[str, int]:
    """Core upsert loop — importable directly so tests can call it twice
    against the same session/connection to prove idempotency at the data
    level, independent of Alembic's own once-per-revision version tracking.
    """
    from app.models.drug_catalog import DrugEntry
    from app.models.drug_knowledge_core import (
        DrugClass,
        DrugIngredient,
        DrugProduct,
        DrugProductIngredient,
        DrugProductName,
    )

    catalog_rows = session.query(DrugEntry).order_by(DrugEntry.generic_name).all()
    if len(catalog_rows) != EXPECTED_SOURCE_ROW_COUNT:
        raise RuntimeError(
            f"K1-S2 zero-loss check failed: expected {EXPECTED_SOURCE_ROW_COUNT} "
            f"drug_catalog rows, found {len(catalog_rows)}. Not migrating — "
            "investigate before re-running (catalog seed drifted since this "
            "migration was authored)."
        )

    class_cache: dict[str, DrugClass] = {}
    stats = {"classes": 0, "ingredients": 0, "products": 0, "product_names": 0}

    for row in catalog_rows:
        # 1. drug_classes — one row per distinct source drug_class string.
        # No ATC code/level exists anywhere in the source data (confirmed by
        # inspection of all 41 entries) — left NULL, not guessed.
        cls = class_cache.get(row.drug_class)
        if cls is None:
            cls = session.query(DrugClass).filter_by(name=row.drug_class).one_or_none()
            if cls is None:
                cls = DrugClass(name=row.drug_class, required_specialties=[])
                session.add(cls)
                session.flush()
                stats["classes"] += 1
            class_cache[row.drug_class] = cls

        # 2. drug_ingredients — every one of the 41 entries has exactly one
        # active_ingredient (verified during design; no combination products
        # in this catalog). name_inn is the source value verbatim (often the
        # salt form actually prescribed, e.g. "metformin hydrochloride") —
        # not decomposed into a purer INN base name, which would require
        # clinical judgment this migration does not have grounds to guess.
        # name_vietnamese / cas_number: no dedicated ingredient-level source
        # field exists (vietnamese_common_names is a PRODUCT/brand list, not
        # an ingredient name) — left NULL rather than mis-mapped.
        ing_name = row.active_ingredients[0].strip()
        ingredient = session.query(DrugIngredient).filter_by(name_inn=ing_name).one_or_none()
        if ingredient is None:
            ingredient = DrugIngredient(name_inn=ing_name, drug_class_id=cls.id)
            session.add(ingredient)
            session.flush()
            stats["ingredients"] += 1

        # 3. drug_products
        product = (
            session.query(DrugProduct).filter_by(display_name=row.generic_name).one_or_none()
        )
        if product is None:
            product = DrugProduct(
                display_name=row.generic_name,
                prescription_required=row.prescription_required,
                country=row.country_context,
                is_active=row.is_active,
                source_version=row.source_version,
            )
            session.add(product)
            session.flush()
            stats["products"] += 1

        # 4. drug_product_ingredients — role="active_ingredient" states what
        # the source's own field name already asserts (active_ingredients),
        # not an inference about pharmacology this migration can't judge.
        link = (
            session.query(DrugProductIngredient)
            .filter_by(drug_product_id=product.id, drug_ingredient_id=ingredient.id)
            .one_or_none()
        )
        if link is None:
            session.add(
                DrugProductIngredient(
                    drug_product_id=product.id,
                    drug_ingredient_id=ingredient.id,
                    is_primary=True,
                    role="active_ingredient",
                )
            )

        # 5. drug_product_names — brand/vietnamese_common/alias lists often
        # overlap (e.g. a brand name repeated in the VN list) by design in
        # the source data; each (name, name_type) pair is its own row, not
        # collapsed. language="vi" reflects market context (all 41 entries
        # are country_context="VN"), not a claim about the name string's
        # actual language.
        for names, name_type in (
            (row.brand_names, "brand"),
            (row.vietnamese_common_names, "vietnamese_common"),
            (row.aliases, "alias"),
        ):
            for name in names:
                exists = (
                    session.query(DrugProductName)
                    .filter_by(drug_product_id=product.id, name=name, name_type=name_type)
                    .one_or_none()
                )
                if exists is None:
                    session.add(
                        DrugProductName(
                            drug_product_id=product.id,
                            name=name,
                            name_type=name_type,
                            language="vi",
                        )
                    )
                    stats["product_names"] += 1

    session.commit()
    stats["source_rows_seen"] = len(catalog_rows)
    return stats


def upgrade() -> None:
    _add_business_key_constraints()
    bind = op.get_bind()
    session = Session(bind=bind)
    stats = migrate_catalog_rows(session)
    print(f"[k1_s2_m01] migrated {stats['source_rows_seen']}/{EXPECTED_SOURCE_ROW_COUNT} catalog rows: {stats}")


def downgrade() -> None:
    """Remove only the rows this migration created. drug_catalog is never touched.

    Safe to unconditionally clear all 5 relational-core tables: K1-M01
    shipped them empty and nothing else has written to them since — this is
    the only migration/service that has ever populated them.
    """
    from app.models.drug_knowledge_core import (
        DrugClass,
        DrugIngredient,
        DrugProduct,
        DrugProductIngredient,
        DrugProductName,
    )

    bind = op.get_bind()
    session = Session(bind=bind)
    session.query(DrugProductName).delete()
    session.query(DrugProductIngredient).delete()
    session.query(DrugProduct).delete()
    session.query(DrugIngredient).delete()
    session.query(DrugClass).delete()
    session.commit()

    _drop_business_key_constraints()
