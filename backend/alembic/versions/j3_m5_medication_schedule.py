"""Journey 3 M5: medication scheduling tables (§1.8).

Adds medication_schedules + dose_occurrences (the reminder/adherence substrate).
Purely additive; portable SQLite/PostgreSQL (JSONB on PG). dose_occurrences has a
unique idempotency_key so the concurrency-safe scheduler never double-materializes
a dose.

Revision ID: j3_m5_medication_schedule
Revises: mdi_s0_medical_documents
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "j3_m5_medication_schedule"
down_revision: str | None = "mdi_s0_medical_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "medication_schedules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("medication_id", sa.String(length=36), sa.ForeignKey("medications.id"), nullable=False),
        sa.Column("patient_id", sa.String(length=36), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("patient_timezone", sa.String(length=64), server_default="Asia/Ho_Chi_Minh", nullable=False),
        sa.Column("schedule_type", sa.String(length=24), nullable=False),
        sa.Column("local_dose_times", _json(), nullable=True),
        sa.Column("recurrence", _json(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("source", sa.String(length=24), server_default="manual", nullable=False),
        sa.Column("verification_status", sa.String(length=24), nullable=True),
        sa.Column("dedupe_key", sa.String(length=128), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("superseded_by", sa.String(length=36), sa.ForeignKey("medication_schedules.id"), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_medication_schedules_medication_id", "medication_schedules", ["medication_id"])
    op.create_index("ix_medication_schedules_patient_id", "medication_schedules", ["patient_id"])
    op.create_index("ix_medication_schedules_status", "medication_schedules", ["status"])
    op.create_index("ix_medication_schedules_dedupe_key", "medication_schedules", ["dedupe_key"])

    op.create_table(
        "dose_occurrences",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("schedule_id", sa.String(length=36), sa.ForeignKey("medication_schedules.id"), nullable=False),
        sa.Column("patient_id", sa.String(length=36), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("scheduled_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_render", sa.String(length=32), nullable=True),
        sa.Column("state", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("source_schedule_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skip_reason", sa.String(length=255), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("idempotency_key", name="uq_dose_idempotency_key"),
    )
    op.create_index("ix_dose_occurrences_schedule_id", "dose_occurrences", ["schedule_id"])
    op.create_index("ix_dose_occurrences_patient_id", "dose_occurrences", ["patient_id"])
    op.create_index("ix_dose_occurrences_scheduled_utc", "dose_occurrences", ["scheduled_utc"])
    op.create_index("ix_dose_occurrences_state", "dose_occurrences", ["state"])


def downgrade() -> None:
    op.drop_index("ix_dose_occurrences_state", table_name="dose_occurrences")
    op.drop_index("ix_dose_occurrences_scheduled_utc", table_name="dose_occurrences")
    op.drop_index("ix_dose_occurrences_patient_id", table_name="dose_occurrences")
    op.drop_index("ix_dose_occurrences_schedule_id", table_name="dose_occurrences")
    op.drop_table("dose_occurrences")
    op.drop_index("ix_medication_schedules_dedupe_key", table_name="medication_schedules")
    op.drop_index("ix_medication_schedules_status", table_name="medication_schedules")
    op.drop_index("ix_medication_schedules_patient_id", table_name="medication_schedules")
    op.drop_index("ix_medication_schedules_medication_id", table_name="medication_schedules")
    op.drop_table("medication_schedules")
