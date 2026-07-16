"""K1-A1B-F1: Knowledge schema completion — structured references +
drug_side_effects frequency/action_level split.

Two independent changes, both resolving open items from
docs/medication-management/MEDICATION_KNOWLEDGE_TEMPLATE_V1.md and
MEDICATION_PHASE_A_BLOCKING_FINDINGS.md, both approved by PTH 2026-07-16:

1. Structured reference persistence (Finding 1). Replaces the rejected
   "references only in source YAML" proposal. Adds `drug_references`
   (one row per distinct citation) and `knowledge_reference_links` (a
   polymorphic many-to-many join across the 5 knowledge tables, same
   pattern as `knowledge_review_specialties`).

2. `drug_side_effects` frequency/action_level split. The prior `level`
   enum (common/uncommon/rare/serious) conflated frequency with what
   action a patient should take — a side effect can be rare AND urgent.
   Splits into `frequency` + `action_level`, adds a `label` short-text
   field for card-style UI, and simplifies the business key from
   `(ingredient, level, concept_code)` to `(ingredient, concept_code)`.

Both changes run as direct DDL against guaranteed-empty tables (K1
dormancy holds — zero rows ever written to any of the 5 knowledge tables,
per EC-07). upgrade()/downgrade() both assert the row count is 0 before
touching `drug_side_effects`, failing closed rather than silently
discarding data if that assumption is ever wrong.

No clinical content is authored by this migration. No API route, no
frontend, no AI wiring touches any of this — same dormancy discipline as
K1-M01/K1-S2.

Revision ID: k1_a1b_f1_schema_complete
Revises: k1_s2_m01_catalog_migration
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k1_a1b_f1_schema_complete"
down_revision: str | None = "k1_s2_m01_catalog_migration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SIDE_EFFECTS_TABLE = "drug_side_effects"


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]


def _assert_side_effects_empty(context: str) -> None:
    """Fail closed: never run a destructive column swap against real data.
    K1 dormancy (EC-07) guarantees this table is empty today — this check
    makes that assumption an explicit runtime guard, not a silent one,
    matching this codebase's established migration convention (K1-S2's
    count-verification-then-refuse downgrade)."""
    conn = op.get_bind()
    count = conn.execute(sa.text(f"SELECT COUNT(*) FROM {_SIDE_EFFECTS_TABLE}")).scalar()
    if count != 0:
        raise RuntimeError(
            f"{_SIDE_EFFECTS_TABLE} has {count} row(s) — expected 0 (K1 dormancy, EC-07). "
            f"Refusing to run the {context}; this migration assumes no backfill is needed "
            "and will not guess how to map old data into the new columns."
        )


def upgrade() -> None:
    # -------------------------------------------------------------------
    # Structured references (Finding 1)
    # -------------------------------------------------------------------
    op.create_table(
        "drug_references",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("publisher", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("document_identifier", sa.String(255), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=False),
        sa.Column("source_version", sa.String(32), nullable=False),
        sa.Column("accessed_at", sa.Date(), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "publisher",
            "title",
            "publication_date",
            "source_version",
            name="uq_drug_references_natural_key",
        ),
        sa.CheckConstraint(
            "source_type IN "
            "('formulary','clinical_guideline','product_label','peer_reviewed','other')",
            name="ck_drug_references_source_type",
        ),
        sa.CheckConstraint(
            "url IS NOT NULL OR document_identifier IS NOT NULL",
            name="ck_drug_references_locator_present",
        ),
    )

    op.create_table(
        "knowledge_reference_links",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("knowledge_table", sa.String(32), nullable=False),
        sa.Column("knowledge_row_id", sa.String(36), nullable=False),
        sa.Column("drug_reference_id", sa.String(36), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["drug_reference_id"],
            ["drug_references.id"],
            name="fk_krl_reference",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "knowledge_table IN ("
            "'drug_usage','drug_patient_education','drug_side_effects',"
            "'drug_monitoring','drug_contraindications'"
            ")",
            name="ck_krl_knowledge_table",
        ),
        sa.UniqueConstraint(
            "knowledge_table",
            "knowledge_row_id",
            "drug_reference_id",
            name="uq_krl_no_duplicate_link",
        ),
    )
    op.create_index(
        "ix_knowledge_reference_links_row",
        "knowledge_reference_links",
        ["knowledge_table", "knowledge_row_id"],
    )
    op.create_index(
        "ix_knowledge_reference_links_drug_reference_id",
        "knowledge_reference_links",
        ["drug_reference_id"],
    )

    # -------------------------------------------------------------------
    # drug_side_effects: frequency/action_level split
    # -------------------------------------------------------------------
    _assert_side_effects_empty("frequency/action_level column swap")

    # batch_alter_table: SQLite has no native ALTER-of-constraint support
    # (this repo's test_sqlite_upgrade_downgrade_roundtrip runs the full
    # migration chain against SQLite too, not just Postgres) — batch mode
    # is a no-op wrapper on Postgres (still plain ALTER TABLE statements,
    # no table copy) and the only portable way to add/drop columns and
    # CHECK constraints together on SQLite (copy-and-move strategy).
    op.drop_index("uq_drug_side_effects_approved_key", table_name=_SIDE_EFFECTS_TABLE)
    with op.batch_alter_table(_SIDE_EFFECTS_TABLE) as batch_op:
        batch_op.add_column(sa.Column("label", sa.String(80), nullable=False))
        batch_op.add_column(sa.Column("frequency", sa.String(16), nullable=False))
        batch_op.add_column(sa.Column("action_level", sa.String(24), nullable=False))
        batch_op.create_check_constraint(
            "ck_drug_side_effects_frequency",
            "frequency IN ('common','uncommon','rare','unknown')",
        )
        batch_op.create_check_constraint(
            "ck_drug_side_effects_action_level",
            "action_level IN ('self_monitor','contact_clinician','urgent_medical_help')",
        )
        batch_op.drop_column("level")
    op.create_index(
        "uq_drug_side_effects_approved_key",
        _SIDE_EFFECTS_TABLE,
        ["drug_ingredient_id", "concept_code"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
        sqlite_where=sa.text("status = 'approved'"),
    )


def downgrade() -> None:
    """Reverse creation order. The side-effect column revert re-derives a
    single `level` column — not information-preserving (frequency and
    action_level collapse into one field), which is acceptable ONLY
    because the table is guaranteed empty; re-asserted here so a
    downgrade never silently discards real data either."""
    _assert_side_effects_empty("downgrade of the frequency/action_level split")

    op.drop_index("uq_drug_side_effects_approved_key", table_name=_SIDE_EFFECTS_TABLE)
    with op.batch_alter_table(_SIDE_EFFECTS_TABLE) as batch_op:
        batch_op.add_column(sa.Column("level", sa.String(16), nullable=False))
        batch_op.drop_constraint("ck_drug_side_effects_action_level", type_="check")
        batch_op.drop_constraint("ck_drug_side_effects_frequency", type_="check")
        batch_op.drop_column("action_level")
        batch_op.drop_column("frequency")
        batch_op.drop_column("label")
    op.create_index(
        "uq_drug_side_effects_approved_key",
        _SIDE_EFFECTS_TABLE,
        ["drug_ingredient_id", "level", "concept_code"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
        sqlite_where=sa.text("status = 'approved'"),
    )

    op.drop_index(
        "ix_knowledge_reference_links_drug_reference_id",
        table_name="knowledge_reference_links",
    )
    op.drop_index("ix_knowledge_reference_links_row", table_name="knowledge_reference_links")
    op.drop_table("knowledge_reference_links")
    op.drop_table("drug_references")
