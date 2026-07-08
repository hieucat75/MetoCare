"""c0_m6: create clinic_patient_relationships

New table (DATA_MODEL.md §6) — the missing patient<->clinic link.
`patient_profiles` is NOT altered (no clinic_id column added there; a patient
keeps one longitudinal profile across every clinic they've visited). Unique
(clinic_id, patient_code) per Agent C; ADDITIONALLY unique (clinic_id,
patient_id) to prevent a double-submit race forking one patient into two
rows at the same clinic (DATA_MODEL.md §6 deviation). ON DELETE RESTRICT on
both FKs — a patient's profile/clinic link must never silently disappear.

Revision ID: c0_m6_clinic_patient_rel
Revises: c0_m5_clinic_service
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0_m6_clinic_patient_rel"
down_revision = "c0_m5_clinic_service"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinic_patient_relationships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patient_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "clinic_id",
            sa.String(36),
            sa.ForeignKey("clinics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("patient_code", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
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
            "clinic_id", "patient_code", name="uq_clinic_patient_rel_clinic_code"
        ),
        sa.UniqueConstraint(
            "clinic_id", "patient_id", name="uq_clinic_patient_rel_clinic_patient"
        ),
    )
    op.create_index(
        "ix_clinic_patient_rel_patient_id",
        "clinic_patient_relationships",
        ["patient_id"],
    )
    op.create_index(
        "ix_clinic_patient_rel_clinic_id",
        "clinic_patient_relationships",
        ["clinic_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_clinic_patient_rel_clinic_id", table_name="clinic_patient_relationships"
    )
    op.drop_index(
        "ix_clinic_patient_rel_patient_id", table_name="clinic_patient_relationships"
    )
    op.drop_table("clinic_patient_relationships")
