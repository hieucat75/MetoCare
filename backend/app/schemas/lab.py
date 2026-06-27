"""Lab schemas."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LabDocumentCreate(BaseModel):
    storage_key: str
    file_type: str | None = None
    lab_name: str | None = None


# --- PR-B: manual structured lab entry (no OCR/file) ---


class LabResultItemIn(BaseModel):
    test_name: str = Field(..., min_length=1, max_length=128)
    value: float | None = None
    unit: str | None = Field(None, max_length=24)
    reference_range: str | None = Field(None, max_length=64)
    original_value: float | None = None
    original_unit: str | None = Field(None, max_length=24)
    original_reference_range: str | None = Field(None, max_length=64)
    original_test_name: str | None = Field(None, max_length=128)


class LabManualEntryCreate(BaseModel):
    lab_name: str | None = Field(None, max_length=255)
    # Required: the real exam date (when the sample was taken), NOT the upload date.
    # A lab report can be months old, so this drives history ordering + trends.
    test_date: dt.date = Field(
        ..., description="Exam date (YYYY-MM-DD); must be ≤ today and within 50 years"
    )
    results: list[LabResultItemIn] = Field(..., min_length=1)
    # Duplicate handling: null = reject if duplicate found (return 409).
    # "new" = save as a new batch alongside any existing one.
    # "overwrite" = soft-delete existing_batch_id first, then save.
    force_mode: Literal["new", "overwrite"] | None = None
    # Required when force_mode="overwrite": the batch_id returned in the 409 response.
    existing_batch_id: str | None = None
    # OCR feedback loop — pass back the id from the upload draft to close the gap analysis.
    ocr_case_id: str | None = None
    review_time_seconds: float | None = None

    @field_validator("test_date")
    @classmethod
    def _validate_test_date(cls, v: dt.date) -> dt.date:
        today = dt.date.today()
        if v > today:
            raise ValueError("Ngày xét nghiệm không được ở tương lai.")
        if v < today.replace(year=today.year - 50):
            raise ValueError("Ngày xét nghiệm quá xa trong quá khứ (>50 năm).")
        return v


# ── Batch schemas ────────────────────────────────────────────────────────────


class LabUploadBatchOut(BaseModel):
    id: str
    patient_id: str
    lab_name: str | None
    test_date: dt.date | None
    result_count: int
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class LabBatchListResponse(BaseModel):
    patient_id: str
    total: int
    items: list[LabUploadBatchOut]


class DuplicateCheckRequest(BaseModel):
    test_date: dt.date
    lab_name: str | None = None
    biomarker_names: list[str] = Field(default_factory=list)


class DuplicateCheckResponse(BaseModel):
    is_duplicate: bool
    existing_batch_id: str | None = None
    existing_test_date: dt.date | None = None
    reason: str | None = None  # "exact_hash" | "same_date_lab" | "overlapping_biomarkers"


class LabResultOut(BaseModel):
    id: str
    patient_id: str
    document_id: str | None
    batch_id: str | None = None
    test_name: str
    canonical_name: str | None = None
    value: float | None
    unit: str | None
    reference_range: str | None
    status: str | None
    test_date: dt.date | None
    verified_by_user: bool
    # OCR originals (may be None for manual entries)
    original_value: float | None = None
    original_unit: str | None = None
    original_reference_range: str | None = None
    original_test_name: str | None = None
    # SI-normalized fields
    normalized_value_si: float | None = None
    normalized_unit_si: str | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class LabResultListResponse(BaseModel):
    patient_id: str
    total: int
    items: list[LabResultOut]


class BatchLabResultListResponse(BaseModel):
    """Response for GET /patients/{patient_id}/lab-batches/{batch_id}/results."""
    batch_id: str
    patient_id: str
    total: int
    items: list[LabResultOut]


class LabDocumentOut(BaseModel):
    id: str
    patient_id: str
    ocr_status: str
    status: str = "uploaded"

    model_config = {"from_attributes": True}


class LabDocumentStatusOut(BaseModel):
    id: str
    status: str
    ocr_status: str
    enqueued: bool = False


class InterpretedBiomarkerOut(BaseModel):
    canonical: str
    value: float
    unit: str
    status: str
    reference_range: str
    needs_verification: bool
    patient_note: str


class InterpretationOut(BaseModel):
    biomarkers: list[InterpretedBiomarkerOut]
    abnormal: list[str]
    critical: list[str]
    needs_verification: bool
    patient_explanation: str
    doctor_summary: str


class LabResultCorrectionIn(BaseModel):
    """Payload for user-correcting a lab result value and/or unit."""
    value: float
    unit: str = ""
