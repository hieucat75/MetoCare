"""Lab schemas."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


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


class LabManualEntryCreate(BaseModel):
    lab_name: str | None = Field(None, max_length=255)
    test_date: dt.date | None = None
    results: list[LabResultItemIn] = Field(..., min_length=1)


class LabResultOut(BaseModel):
    id: str
    patient_id: str
    document_id: str | None
    test_name: str
    value: float | None
    unit: str | None
    reference_range: str | None
    status: str | None
    test_date: dt.date | None
    verified_by_user: bool
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class LabResultListResponse(BaseModel):
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
