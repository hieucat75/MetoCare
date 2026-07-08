"""c0_m3: create clinic_memberships

New table (DATA_MODEL.md §3), generalizes DoctorClinic to all 7 clinic roles.
DoctorClinic is NOT altered or replaced in this batch. Unique (user_id,
clinic_id) — one membership row per user per clinic (multi-role via the
`roles` JSON array). ON DELETE RESTRICT on user_id/clinic_id (audit-history
integrity — see DATA_MODEL.md §3 deviation rationale); SET NULL on
doctor_profile_id.

Revision ID: c0_m3_clinic_membership
Revises: c0_m2_clinic_branches
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0_m3_clinic_membership"
down_revision = "c0_m2_clinic_branches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "clinic_id",
            sa.String(36),
            sa.ForeignKey("clinics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("branch_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "doctor_profile_id",
            sa.String(36),
            sa.ForeignKey("doctors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="invited"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("joined_at", sa.Date(), nullable=True),
        sa.Column("left_at", sa.Date(), nullable=True),
        sa.Column(
            "invited_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.UniqueConstraint(
            "user_id", "clinic_id", name="uq_clinic_memberships_user_clinic"
        ),
    )
    op.create_index("ix_clinic_memberships_user_id", "clinic_memberships", ["user_id"])
    op.create_index("ix_clinic_memberships_clinic_id", "clinic_memberships", ["clinic_id"])
    op.create_index(
        "ix_clinic_memberships_clinic_status",
        "clinic_memberships",
        ["clinic_id", "status"],
    )
    op.create_index(
        "ix_clinic_memberships_user_status", "clinic_memberships", ["user_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_clinic_memberships_user_status", table_name="clinic_memberships")
    op.drop_index("ix_clinic_memberships_clinic_status", table_name="clinic_memberships")
    op.drop_index("ix_clinic_memberships_clinic_id", table_name="clinic_memberships")
    op.drop_index("ix_clinic_memberships_user_id", table_name="clinic_memberships")
    op.drop_table("clinic_memberships")
