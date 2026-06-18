"""T21: add doctor_availability and booking_appointments tables

Revision ID: t21_add_booking
Revises: t19_add_triage_log
Create Date: 2026-06-18 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t21_add_booking"
down_revision: str | None = "t19_add_triage_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. doctor_availability                                              #
    # ------------------------------------------------------------------ #
    op.create_table(
        "doctor_availability",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "doctor_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slot_start", sa.DateTime(timezone=False), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=False), nullable=False),
        sa.Column("is_booked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    # ------------------------------------------------------------------ #
    # 2. booking_appointments                                             #
    # ------------------------------------------------------------------ #
    op.create_table(
        "booking_appointments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patient_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "doctor_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "availability_id",
            sa.String(36),
            sa.ForeignKey("doctor_availability.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )



def downgrade() -> None:
    op.drop_table("booking_appointments")
    op.drop_table("doctor_availability")
