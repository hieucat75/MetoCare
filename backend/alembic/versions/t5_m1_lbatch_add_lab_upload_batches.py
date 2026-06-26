"""Add lab_upload_batches table + batch_id FK on lab_results + deleted_at on health_metrics.

Revision ID: t5_m1_lbatch
Revises:     t4_m11_orlb
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "t5_m1_lbatch"
down_revision: str | None = "t4_m11_orlb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. New table: lab_upload_batches ────────────────────────────────────
    op.create_table(
        "lab_upload_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patient_profiles.id"),
            nullable=False,
        ),
        sa.Column(
            "source_document_id",
            sa.String(36),
            sa.ForeignKey("lab_documents.id"),
            nullable=True,
        ),
        sa.Column("lab_name", sa.String(255), nullable=True),
        sa.Column("test_date", sa.Date(), nullable=True),
        # SHA-256 hex of the raw file bytes — exact duplicate detection.
        sa.Column("file_hash", sa.String(64), nullable=True),
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
        # Soft-delete columns (mirrors SoftDeleteMixin on LabResult).
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "deleted_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("delete_reason", sa.String(512), nullable=True),
    )
    op.create_index(
        "ix_lab_upload_batches_patient_id",
        "lab_upload_batches",
        ["patient_id"],
    )
    op.create_index(
        "ix_lab_upload_batches_test_date",
        "lab_upload_batches",
        ["patient_id", "test_date"],
    )

    # ── 2. Add batch_id FK to lab_results ───────────────────────────────────
    with op.batch_alter_table("lab_results", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("batch_id", sa.String(36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_lab_results_batch_id",
            "lab_upload_batches",
            ["batch_id"],
            ["id"],
        )
        batch_op.create_index("ix_lab_results_batch_id", ["batch_id"])

    # ── 3. Add deleted_at to health_metrics (was missing SoftDeleteMixin) ──
    with op.batch_alter_table("health_metrics", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("deleted_by", sa.String(36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_health_metrics_deleted_by",
            "users",
            ["deleted_by"],
            ["id"],
        )
        batch_op.create_index("ix_health_metrics_deleted_at", ["deleted_at"])


def downgrade() -> None:
    with op.batch_alter_table("health_metrics", schema=None) as batch_op:
        batch_op.drop_index("ix_health_metrics_deleted_at")
        batch_op.drop_constraint("fk_health_metrics_deleted_by", type_="foreignkey")
        batch_op.drop_column("deleted_by")
        batch_op.drop_column("deleted_at")

    with op.batch_alter_table("lab_results", schema=None) as batch_op:
        batch_op.drop_index("ix_lab_results_batch_id")
        batch_op.drop_constraint("fk_lab_results_batch_id", type_="foreignkey")
        batch_op.drop_column("batch_id")

    op.drop_index("ix_lab_upload_batches_test_date", table_name="lab_upload_batches")
    op.drop_index("ix_lab_upload_batches_patient_id", table_name="lab_upload_batches")
    op.drop_table("lab_upload_batches")
