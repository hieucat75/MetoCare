"""K2 Slice 0: add `origin` to the 5 ADR-13 knowledge tables.

docs/medication-management/
MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md
§B2.2/§B3. First of Slice 0's four migrations.

Every row has exactly one origin — a first-class fact about the row
itself, following the exact "add one column to all 5 tables in one
revision" shape `k1_a1b_artifact_hash.py` already used for `artifact_hash`.

Legacy-row interpretation: every pre-Slice-0 row becomes `human_authored`
— NOT `source_extracted`. Verified directly against the live codebase
(plan §0.2/§B2.2): every row ever written through this codebase's only
real write path (`create_draft`, fed exclusively by the A1b importer,
which hard-types `ai_generated: Literal[False]` at
`medication_knowledge_import/schema.py:171`) is human-authored — no
ingestion pipeline (Slice 2) has ever run. Backfilling to `source_extracted`
would itself misclassify legacy content, which this plan is required to
avoid.

Backfill strategy: server-default backfill at `ADD COLUMN` time — every
pre-Slice-0 row becomes `human_authored` atomically as part of the ADD
COLUMN statement itself, no separate UPDATE needed.

No clinical content is authored by this migration. No API route,
frontend, or AI wiring is touched.

Downgrade safety: refuses if any row has `origin <> 'human_authored'` on
any of the 5 tables (real classification has already happened) — raises a
named `RuntimeError` listing offending tables/counts, same idiom as
`k2_s1_widen_evidence_level.py`. If every row is still at the default, the
column and its CHECK constraint are dropped on all 5 tables.

Revision ID: k2_s0_knowledge_origin
Revises: k2_s1_widen_evidence_level
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k2_s0_knowledge_origin"
down_revision: str | None = "k2_s1_widen_evidence_level"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)

# Must match app/models/drug_knowledge_content.py's ORIGIN_VALUES exactly.
_ORIGIN_VALUES = ("source_extracted", "rule_derived", "ai_synthesized", "human_authored")
_ORIGIN_DEFAULT = "human_authored"


def upgrade() -> None:
    """`op.batch_alter_table` per table — required for SQLite to add a
    NOT NULL column with a CHECK constraint in one step (harmless no-op
    wrapper on Postgres, same idiom as `k2_s1_widen_evidence_level.py`).
    The server default backfills every existing row atomically as part of
    the ADD COLUMN itself."""
    values = ",".join(f"'{v}'" for v in _ORIGIN_VALUES)
    for table in _KNOWLEDGE_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "origin",
                    sa.String(24),
                    nullable=False,
                    server_default=sa.text(f"'{_ORIGIN_DEFAULT}'"),
                )
            )
            batch_op.create_check_constraint(f"ck_{table}_origin", f"origin IN ({values})")


def downgrade() -> None:
    """Refuses to drop `origin` if any row has been reclassified away from
    the default — dropping the column would silently discard real
    provenance classification, not just an unused default value."""
    bind = op.get_bind()
    offenders: list[str] = []
    for table in _KNOWLEDGE_TABLES:
        count = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE origin <> :default"),
            {"default": _ORIGIN_DEFAULT},
        ).scalar()
        if count:
            offenders.append(f"{table} ({count} row(s))")

    if offenders:
        raise RuntimeError(
            "Refusing to downgrade: the following table(s) have origin values "
            f"other than the default {_ORIGIN_DEFAULT!r}, which would be silently "
            f"discarded by dropping the column: {', '.join(offenders)}. Remediate "
            "the data first (confirm this classification is no longer needed) "
            "before attempting to downgrade past this revision."
        )

    for table in _KNOWLEDGE_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f"ck_{table}_origin", type_="check")
            batch_op.drop_column("origin")
