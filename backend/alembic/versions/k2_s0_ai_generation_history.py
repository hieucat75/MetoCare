"""K2 Slice 0: create `knowledge_ai_generations` (append-only AI generation
history).

docs/medication-management/
MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md
§B2.4/§B3. Second of Slice 0's four migrations.

Mirrors `app/models/drug_knowledge_ai_generation.py`'s `KnowledgeAIGeneration`
model exactly. Polymorphic association (no physical FK to any of the 5
knowledge tables) — same shape as `knowledge_reference_links`/
`knowledge_review_specialties`.

No clinical content is authored by this migration — the table is created
empty and stays empty through Slice 0 (no AI provider calls, no synthesis
code exists yet to write into it).

Downgrade safety: refuses if the table is non-empty (any row in it is, by
definition, a real generation record, never a backfilled default) — raises
a named `RuntimeError`. If empty, drops the table.

Revision ID: k2_s0_ai_generation_history
Revises: k2_s0_knowledge_origin
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# PR #136 Codex Round 2 finding (fix round 2, 2026-07-28): plain
# PostgreSQL `json` has no equality operator, so k2_s0_integrity_guards'
# append-only trigger comparing these two columns with `IS DISTINCT FROM`
# raised `operator does not exist: json = json` on every UPDATE —
# including the one legitimate review_status promotion, breaking approval
# of every ai_synthesized row on Postgres. `jsonb` supports equality/IS
# DISTINCT FROM directly; SQLite's own JSON type is unaffected either way.
_JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

revision: str = "k2_s0_ai_generation_history"
down_revision: str | None = "k2_s0_knowledge_origin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)
_GENERATION_STATUS_VALUES = ("succeeded", "failed")
_REVIEW_STATUS_VALUES = ("pending", "promoted", "rejected", "superseded")
# Must match app/models/drug_knowledge_content.py's ORIGIN_VALUES exactly.
_ORIGIN_VALUES = ("source_extracted", "rule_derived", "ai_synthesized", "human_authored")


def upgrade() -> None:
    knowledge_table_values = ",".join(f"'{t}'" for t in _KNOWLEDGE_TABLES)
    generation_status_values = ",".join(f"'{v}'" for v in _GENERATION_STATUS_VALUES)
    review_status_values = ",".join(f"'{v}'" for v in _REVIEW_STATUS_VALUES)
    origin_values = ",".join(f"'{v}'" for v in _ORIGIN_VALUES)

    op.create_table(
        "knowledge_ai_generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("knowledge_table", sa.String(32), nullable=False),
        sa.Column("target_row_id", sa.String(36), nullable=True),
        sa.Column("model_provider", sa.String(32), nullable=False),
        sa.Column("model_identifier", sa.String(64), nullable=False),
        sa.Column("model_version_snapshot", sa.String(128), nullable=True),
        sa.Column("prompt_template_id", sa.String(64), nullable=False),
        sa.Column("prompt_template_version", sa.String(32), nullable=False),
        sa.Column("normalization_pipeline_version", sa.String(32), nullable=True),
        sa.Column("input_source_ids", _JSON_TYPE, nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("generation_params", _JSON_TYPE, nullable=True),
        sa.Column("generation_status", sa.String(16), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(24), nullable=False, server_default=sa.text("'ai_synthesized'")),
        sa.Column("review_status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("superseded_by_generation_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            f"knowledge_table IN ({knowledge_table_values})",
            name="ck_knowledge_ai_generations_table",
        ),
        sa.CheckConstraint(
            f"generation_status IN ({generation_status_values})",
            name="ck_knowledge_ai_generations_status",
        ),
        sa.CheckConstraint(
            f"review_status IN ({review_status_values})",
            name="ck_knowledge_ai_generations_review_status",
        ),
        sa.CheckConstraint(
            f"origin IN ({origin_values})",
            name="ck_knowledge_ai_generations_origin",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_generation_id"],
            ["knowledge_ai_generations.id"],
            ondelete="RESTRICT",
            name="fk_knowledge_ai_generations_superseded_by",
        ),
    )
    op.create_index(
        "ix_knowledge_ai_generations_row",
        "knowledge_ai_generations",
        ["knowledge_table", "target_row_id"],
    )
    op.create_index(
        "ix_knowledge_ai_generations_review_status",
        "knowledge_ai_generations",
        ["review_status"],
    )


def downgrade() -> None:
    """Refuses to drop the table if it holds any row — every row in an
    append-only generation-history table is real evidence, never a
    reconstructable default."""
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT COUNT(*) FROM knowledge_ai_generations")).scalar()
    if count:
        raise RuntimeError(
            f"Refusing to downgrade: knowledge_ai_generations has {count} row(s). "
            "This table is append-only generation-history evidence — dropping it "
            "would destroy provenance that cannot be reconstructed. Remediate "
            "(export/archive the data first) before downgrading past this revision."
        )
    op.drop_index("ix_knowledge_ai_generations_review_status", table_name="knowledge_ai_generations")
    op.drop_index("ix_knowledge_ai_generations_row", table_name="knowledge_ai_generations")
    op.drop_table("knowledge_ai_generations")
