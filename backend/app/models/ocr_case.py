"""OCRCase model — captures every OCR pipeline session for accuracy tracking.

One OCRCase is created per ``POST /lab-uploads`` call (the draft).
It is updated once when the user confirms the save via ``POST /patients/{id}/lab-results``.
The gap between extracted draft rows and user-corrected rows drives per-hospital
accuracy metrics and (if policy allows) dataset export.

Privacy rules:
- raw_azure_json may be stored (allowed per privacy policy for runtime DB).
- extracted/corrected rows are structured JSON — no raw OCR free-text.
- source_file_hash is SHA-256 hex — cannot reconstruct the image.
- source_file_path is a blob reference, never actual bytes.
- This record is patient-owned; patients may only read their own cases.
"""

from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKey


class OCRCase(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "ocr_cases"

    # ── Ownership ──────────────────────────────────────────────────────────────
    patient_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    # Set when user confirms save (links OCR draft → LabUploadBatch).
    lab_batch_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    # ── Detection ─────────────────────────────────────────────────────────────
    hospital_detected: Mapped[str | None] = mapped_column(String(64))
    hospital_confidence: Mapped[float | None] = mapped_column(Float)

    # ── Source ────────────────────────────────────────────────────────────────
    source_file_hash: Mapped[str | None] = mapped_column(String(64))
    source_file_path_or_blob_ref: Mapped[str | None] = mapped_column(String(512))

    # ── Provider metadata ─────────────────────────────────────────────────────
    azure_model: Mapped[str | None] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(32))
    ocr_engine_version: Mapped[str | None] = mapped_column(String(64))

    # ── JSON payloads ─────────────────────────────────────────────────────────
    raw_azure_json: Mapped[str | None] = mapped_column(Text)
    extracted_rows_json: Mapped[str | None] = mapped_column(Text)
    corrected_rows_json: Mapped[str | None] = mapped_column(Text)
    gap_report_json: Mapped[str | None] = mapped_column(Text)

    # ── Accuracy metrics (denormalized for fast reporting) ────────────────────
    accuracy_score: Mapped[float | None] = mapped_column(Float)
    row_accuracy: Mapped[float | None] = mapped_column(Float)
    biomarker_accuracy: Mapped[float | None] = mapped_column(Float)
    value_accuracy: Mapped[float | None] = mapped_column(Float)
    unit_accuracy: Mapped[float | None] = mapped_column(Float)
    editing_rate: Mapped[float | None] = mapped_column(Float)

    rows_total: Mapped[int | None] = mapped_column(Integer)
    rows_correct: Mapped[int | None] = mapped_column(Integer)
    rows_missing: Mapped[int | None] = mapped_column(Integer)
    rows_added: Mapped[int | None] = mapped_column(Integer)
    rows_deleted: Mapped[int | None] = mapped_column(Integer)
    rows_value_corrected: Mapped[int | None] = mapped_column(Integer)
    rows_unit_corrected: Mapped[int | None] = mapped_column(Integer)
    rows_biomarker_corrected: Mapped[int | None] = mapped_column(Integer)

    # ── UX signal ─────────────────────────────────────────────────────────────
    user_review_time_seconds: Mapped[float | None] = mapped_column(Float)

    # ── Dataset export ────────────────────────────────────────────────────────
    export_status: Mapped[str] = mapped_column(String(16), default="pending")
    exported_dataset_path: Mapped[str | None] = mapped_column(String(512))
