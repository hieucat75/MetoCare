"""Add ocr_cases table for OCR feedback loop and accuracy tracking.

Revision ID: t5_m2_ocase
Revises:     t5_m1_lbatch
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "t5_m2_ocase"
down_revision: str | None = "t5_m1_lbatch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ocr_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), nullable=False),
        sa.Column("lab_batch_id", sa.String(36), nullable=True),
        sa.Column("hospital_detected", sa.String(64), nullable=True),
        sa.Column("hospital_confidence", sa.Float, nullable=True),
        sa.Column("source_file_hash", sa.String(64), nullable=True),
        sa.Column("source_file_path_or_blob_ref", sa.String(512), nullable=True),
        sa.Column("azure_model", sa.String(64), nullable=True),
        sa.Column("parser_version", sa.String(32), nullable=True),
        sa.Column("ocr_engine_version", sa.String(64), nullable=True),
        sa.Column("raw_azure_json", sa.Text, nullable=True),
        sa.Column("extracted_rows_json", sa.Text, nullable=True),
        sa.Column("corrected_rows_json", sa.Text, nullable=True),
        sa.Column("gap_report_json", sa.Text, nullable=True),
        sa.Column("accuracy_score", sa.Float, nullable=True),
        sa.Column("row_accuracy", sa.Float, nullable=True),
        sa.Column("biomarker_accuracy", sa.Float, nullable=True),
        sa.Column("value_accuracy", sa.Float, nullable=True),
        sa.Column("unit_accuracy", sa.Float, nullable=True),
        sa.Column("editing_rate", sa.Float, nullable=True),
        sa.Column("rows_total", sa.Integer, nullable=True),
        sa.Column("rows_correct", sa.Integer, nullable=True),
        sa.Column("rows_missing", sa.Integer, nullable=True),
        sa.Column("rows_added", sa.Integer, nullable=True),
        sa.Column("rows_deleted", sa.Integer, nullable=True),
        sa.Column("rows_value_corrected", sa.Integer, nullable=True),
        sa.Column("rows_unit_corrected", sa.Integer, nullable=True),
        sa.Column("rows_biomarker_corrected", sa.Integer, nullable=True),
        sa.Column("user_review_time_seconds", sa.Float, nullable=True),
        sa.Column("export_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("exported_dataset_path", sa.String(512), nullable=True),
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
    op.create_index("ix_ocr_cases_patient_id", "ocr_cases", ["patient_id"])
    op.create_index("ix_ocr_cases_lab_batch_id", "ocr_cases", ["lab_batch_id"])
    op.create_index("ix_ocr_cases_hospital_detected", "ocr_cases", ["hospital_detected"])


def downgrade() -> None:
    op.drop_index("ix_ocr_cases_hospital_detected", table_name="ocr_cases")
    op.drop_index("ix_ocr_cases_lab_batch_id", table_name="ocr_cases")
    op.drop_index("ix_ocr_cases_patient_id", table_name="ocr_cases")
    op.drop_table("ocr_cases")
