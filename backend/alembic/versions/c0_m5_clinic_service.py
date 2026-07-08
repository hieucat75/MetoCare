"""c0_m5: create clinic_services

New table (DATA_MODEL.md §5) — the clinic service/pricing catalog. Index
(clinic_id, status) for the catalog-listing query. ON DELETE CASCADE on
clinic_id (a service has no meaning without its clinic).

Revision ID: c0_m5_clinic_service
Revises: c0_m4_clinic_invitation
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0_m5_clinic_service"
down_revision = "c0_m4_clinic_invitation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic_services",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "clinic_id",
            sa.String(36),
            sa.ForeignKey("clinics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("branch_ids", sa.JSON(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("package_visit_count", sa.Integer(), nullable=True),
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
    )
    op.create_index("ix_clinic_services_clinic_id", "clinic_services", ["clinic_id"])
    op.create_index(
        "ix_clinic_services_clinic_status", "clinic_services", ["clinic_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_clinic_services_clinic_status", table_name="clinic_services")
    op.drop_index("ix_clinic_services_clinic_id", table_name="clinic_services")
    op.drop_table("clinic_services")
