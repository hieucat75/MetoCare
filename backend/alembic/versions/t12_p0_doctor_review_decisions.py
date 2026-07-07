"""t12_p0: add doctor_review_decisions (encrypted review notes)

Persists the doctor-portal review comment + internal_note (both potentially PHI)
in an ENCRYPTED store, keeping ``audit_logs`` PHI-free per its contract. The
encrypted columns map to ``sa.Text`` (ciphertext is base64 text).

Revision ID: t12_p0_doctor_review_decisions
Revises: t11_m1_health_metric_original
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t12_p0_doctor_review_decisions"
down_revision = "t11_m1_health_metric_original"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "doctor_review_decisions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("doctor_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("internal_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_doctor_review_decisions_item_id", "doctor_review_decisions", ["item_id"]
    )
    op.create_index(
        "ix_doctor_review_decisions_patient_id", "doctor_review_decisions", ["patient_id"]
    )
    op.create_index(
        "ix_doctor_review_decisions_doctor_id", "doctor_review_decisions", ["doctor_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_doctor_review_decisions_doctor_id", table_name="doctor_review_decisions"
    )
    op.drop_index(
        "ix_doctor_review_decisions_patient_id", table_name="doctor_review_decisions"
    )
    op.drop_index(
        "ix_doctor_review_decisions_item_id", table_name="doctor_review_decisions"
    )
    op.drop_table("doctor_review_decisions")
