"""c0_m2: create clinic_branches

New table (DATA_MODEL.md §2). Unique (clinic_id, name); index (clinic_id,
status) for the "list my clinic's active branches" query. ON DELETE CASCADE
on clinic_id — a branch has zero meaning once its owning clinic is gone, and
clinics are never hard-deleted in this design (deactivation is a status
flip, not a DELETE).

Revision ID: c0_m2_clinic_branches
Revises: c0_m1_clinic_extend_columns
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0_m2_clinic_branches"
down_revision = "c0_m1_clinic_extend_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic_branches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "clinic_id",
            sa.String(36),
            sa.ForeignKey("clinics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.JSON(), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("working_hours", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("clinic_id", "name", name="uq_clinic_branches_clinic_name"),
    )
    op.create_index(
        "ix_clinic_branches_clinic_id", "clinic_branches", ["clinic_id"]
    )
    op.create_index(
        "ix_clinic_branches_clinic_status", "clinic_branches", ["clinic_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_clinic_branches_clinic_status", table_name="clinic_branches")
    op.drop_index("ix_clinic_branches_clinic_id", table_name="clinic_branches")
    op.drop_table("clinic_branches")
