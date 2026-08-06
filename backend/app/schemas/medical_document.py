"""Pydantic schemas for the Medical Document Intelligence API (§2)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, field_validator

# Bounds for patient correction payloads (§O input validation): a flat map of
# scalar field corrections, not arbitrary/deeply-nested/huge JSON.
_MAX_CORRECTION_KEYS = 20
_MAX_CORRECTION_KEY_LEN = 64
_MAX_CORRECTION_VALUE_LEN = 500


def _validate_corrections(v: dict | None) -> dict | None:
    if v is None:
        return v
    if len(v) > _MAX_CORRECTION_KEYS:
        raise ValueError(f"Tối đa {_MAX_CORRECTION_KEYS} trường chỉnh sửa.")
    for key, val in v.items():
        if not isinstance(key, str) or len(key) > _MAX_CORRECTION_KEY_LEN:
            raise ValueError("Tên trường chỉnh sửa không hợp lệ.")
        if isinstance(val, (dict, list)):
            raise ValueError("Giá trị chỉnh sửa phải là văn bản/số, không lồng nhau.")
        if isinstance(val, str) and len(val) > _MAX_CORRECTION_VALUE_LEN:
            raise ValueError("Giá trị chỉnh sửa quá dài.")
    return v


# ── ingestion ────────────────────────────────────────────────────────────────
class UploadSessionCreate(BaseModel):
    declared_mime: str = Field(..., description="Client-declared MIME (verified at finalize)")
    declared_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    declared_size: int | None = Field(default=None, ge=0)
    doc_type_hint: str | None = Field(
        default=None, description="prescription | lab_report | general (patient's chosen capture)"
    )


class UploadSessionOut(BaseModel):
    upload_id: str
    signed_put_url: str
    method: str
    expires_at: dt.datetime
    status: str


class SignedFileOut(BaseModel):
    url: str
    method: str
    expires_at: dt.datetime


# ── documents ────────────────────────────────────────────────────────────────
class DocumentOut(BaseModel):
    id: str
    doc_type: str | None
    status: str
    object_state: str
    mime: str | None
    size_bytes: int | None
    page_count: int | None
    classification_confidence: float | None
    sha256: str | None
    scan_status: str | None
    failure_reason: str | None
    superseded_by: str | None
    created_at: dt.datetime


class DocumentListOut(BaseModel):
    patient_id: str
    total: int
    items: list[DocumentOut]


# ── extraction / candidates ──────────────────────────────────────────────────
class ExtractionOut(BaseModel):
    id: str
    document_id: str
    schema_version: str
    provider: str
    model: str | None
    extraction_run_id: str
    review_state: str
    created_at: dt.datetime


class CandidateOut(BaseModel):
    id: str
    document_id: str
    candidate_type: str
    ordinal: int
    fields: dict
    field_confidence: dict | None
    status: str
    dedupe_key: str
    reviewed_at: dt.datetime | None


class CandidateListOut(BaseModel):
    document_id: str
    total: int
    items: list[CandidateOut]


# ── review actions ───────────────────────────────────────────────────────────
class ConfirmIn(BaseModel):
    corrections: dict | None = Field(
        default=None, description="Per-field patient corrections (appended to history)"
    )

    _check_corrections = field_validator("corrections")(_validate_corrections)


class MergeIn(BaseModel):
    merge_target_id: str = Field(
        ..., min_length=1, max_length=64, description="Existing canonical record to merge into"
    )
    corrections: dict | None = None

    _check_corrections = field_validator("corrections")(_validate_corrections)


class PromotionOut(BaseModel):
    candidate_id: str
    canonical_type: str
    canonical_id: str
    action: str


class ConfirmResultOut(BaseModel):
    candidate: CandidateOut
    promotion: PromotionOut
