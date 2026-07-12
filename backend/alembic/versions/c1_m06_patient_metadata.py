"""c1_m06: extend clinic_patient_relationships with internal_notes

Additive ALTER on `clinic_patient_relationships` (M06 plan §4): a clinic-only
operational note, distinct from clinical content (which stays on M09's
Encounter/Notes model). Nullable, no index, no FK — same bare-value
discipline as `AuditLog.details` (c1_m05_audit_details).

Revision ID: c1_m06_patient_metadata
Revises: c1_m05_audit_details
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1_m06_patient_metadata"
down_revision = "c1_m05_audit_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clinic_patient_relationships", sa.Column("internal_notes", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("clinic_patient_relationships", "internal_notes")
