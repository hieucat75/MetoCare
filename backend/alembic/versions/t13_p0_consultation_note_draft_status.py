"""t13_p0: add draft/finalized status to consultation_notes

Enables a real draft -> finalize workflow for the Doctor Portal clinical
notes module WITHOUT introducing any update/delete path on ConsultationNote
(the append-only invariant is unchanged: "a correction is a new note, never
an edit"). Saving a draft or finalizing both create a new row; ``status``
just marks what kind of row it is, and ``finalized_at`` records when a
finalized row was written. Existing rows default to 'finalized' since they
predate the draft concept and were always complete notes.

Revision ID: t13_p0_consultation_note_draft_status
Revises: t12_merge_p0_m1_heads
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t13_p0_consultation_note_draft_status"
down_revision = "t12_merge_p0_m1_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consultation_notes",
        sa.Column("status", sa.String(16), nullable=False, server_default="finalized"),
    )
    op.add_column(
        "consultation_notes",
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE consultation_notes SET finalized_at = created_at WHERE status = 'finalized'"
    )


def downgrade() -> None:
    op.drop_column("consultation_notes", "finalized_at")
    op.drop_column("consultation_notes", "status")
