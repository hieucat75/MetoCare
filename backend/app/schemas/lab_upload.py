"""Schemas for the lab-upload draft endpoint (OCR Lab Upload track)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LabUploadDraftItemOut(BaseModel):
    test_name: str          # canonical key — feeds straight into the confirm-save form
    canonical: str
    value: float
    unit: str
    reference_range: str | None = None
    status: str             # normal | low | high | critical | unknown
    confidence: float
    needs_verification: bool
    confidence_reasons: list[str] = Field(default_factory=list)


class LabUploadDraftOut(BaseModel):
    """Review-only OCR draft. Nothing is persisted until the patient confirms via
    `POST /patients/{id}/lab-results`."""

    provider_used: str
    confidence_avg: float
    parsed_values: list[LabUploadDraftItemOut]
    warnings: list[str] = Field(default_factory=list)
    raw_text_sha256: str = ""
    low_confidence: bool = False
    manual_fallback: bool = False
    # Exam date detected from the report (ISO YYYY-MM-DD), distinct from upload time.
    extracted_test_date: str | None = None
    test_date_label: str | None = None
    test_date_confidence: float = 0.0
