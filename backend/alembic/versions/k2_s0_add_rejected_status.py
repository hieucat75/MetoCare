"""K2 Slice 0: add `rejected` to the status CHECK on the 5 ADR-13
knowledge tables.

docs/medication-management/
MEDICATION_KNOWLEDGE_SLICE0_ORIGIN_PROVENANCE_FLAGS_IMPLEMENTATION_PLAN.md
§B2.3/§B3. Fourth and last of Slice 0's migrations, PTH-approved ADR-13
amendment.

Closes a real gap: today a `clinical_review` row a reviewer declines has
no modeled destination. Widens the `status` CHECK from 5 to 6 values —
the column itself is unchanged (`VARCHAR(16)`, `'rejected'` fits). No
existing row is ever `rejected` before this migration runs, so the
upgrade is trivially safe for existing data — this is purely a constraint
widening, not a data migration.

`op.batch_alter_table` per table — SQLite has no `ALTER TABLE ... DROP
CONSTRAINT`, so recreating the named CHECK constraint via batch mode is
required (harmless no-op wrapper on Postgres), same idiom
`k2_s1_widen_evidence_level.py` already uses.

Downgrade safety: refuses if any row has `status = 'rejected'` — narrowing
the CHECK back to 5 values would make such a row invalid/unreadable under
the old constraint. If none exist, the 5-value CHECK is recreated.

Revision ID: k2_s0_add_rejected_status
Revises: k2_s0_lifecycle_transitions
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k2_s0_add_rejected_status"
down_revision: str | None = "k2_s0_lifecycle_transitions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KNOWLEDGE_TABLES = (
    "drug_usage",
    "drug_patient_education",
    "drug_side_effects",
    "drug_monitoring",
    "drug_contraindications",
)

# Must match app/models/drug_knowledge_content.py's STATUS_VALUES exactly.
_OLD_STATUS_VALUES = ("draft", "clinical_review", "approved", "deprecated", "retired")
_NEW_STATUS_VALUES = ("draft", "clinical_review", "approved", "rejected", "deprecated", "retired")


def upgrade() -> None:
    new_values = ",".join(f"'{v}'" for v in _NEW_STATUS_VALUES)
    for table in _KNOWLEDGE_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f"ck_{table}_status", type_="check")
            batch_op.create_check_constraint(f"ck_{table}_status", f"status IN ({new_values})")


def downgrade() -> None:
    """Refuses to narrow the CHECK back to 5 values if any row is
    currently `rejected` — such a row would become invalid under the
    narrower constraint, and this migration never deletes or reclassifies
    a rejected row to make room for its own downgrade.

    PR #136 Codex Round 1 finding #8 (fix round 1, 2026-07-28): this
    previously checked ONLY the 5 content tables' current `status` column
    — but `knowledge_lifecycle_transitions` (created earlier in this same
    Slice 0 chain) can independently hold a `from_status='rejected'` or
    `to_status='rejected'` history row even after the content row itself
    was deleted or directly reclassified out of 'rejected' by some other
    means, since that history table is append-only and never rewritten to
    track a content row's later fate. A downgrade that only checked
    current content-row status could narrow the CHECK back to 5 values
    while such retained history still records a 6th value the narrower
    schema can no longer represent — not lost data (history rows are never
    dropped by this downgrade), but a value the post-downgrade schema
    claims is impossible while genuinely still present in retained
    history. Extending this guard to also check
    `knowledge_lifecycle_transitions` closes that gap."""
    bind = op.get_bind()
    offenders: list[str] = []
    for table in _KNOWLEDGE_TABLES:
        count = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE status = 'rejected'")
        ).scalar()
        if count:
            offenders.append(f"{table} ({count} row(s))")

    history_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM knowledge_lifecycle_transitions "
            "WHERE from_status = 'rejected' OR to_status = 'rejected'"
        )
    ).scalar()
    if history_count:
        offenders.append(f"knowledge_lifecycle_transitions ({history_count} row(s) referencing 'rejected')")

    if offenders:
        raise RuntimeError(
            "Refusing to downgrade: the following table(s) reference "
            f"status='rejected', which would become invalid under the narrower "
            f"5-value CHECK constraint: {', '.join(offenders)}. This downgrade is "
            "intentionally irreversible while such rows exist — remediate the "
            "data first before attempting to downgrade past this revision."
        )

    old_values = ",".join(f"'{v}'" for v in _OLD_STATUS_VALUES)
    for table in _KNOWLEDGE_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f"ck_{table}_status", type_="check")
            batch_op.create_check_constraint(f"ck_{table}_status", f"status IN ({old_values})")
