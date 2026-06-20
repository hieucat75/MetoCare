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
