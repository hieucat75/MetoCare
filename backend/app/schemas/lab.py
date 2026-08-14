"""Lab schemas."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class LabDocumentCreate(BaseModel):
    storage_key: str
    file_type: str | None = None
    lab_name: str | None = None


# --- PR-B: manual structured lab entry (no OCR/file) ---


class LabResultItemIn(BaseModel):
    test_name: str = Field(..., min_length=1, max_length=128)
    value: float | None = None
    unit: str | None = Field(None, max_length=64)
    reference_range: str | None = Field(None, max_length=128)
    original_value: float | None = None
    original_unit: str | None = Field(None, max_length=64)
    original_reference_range: str | None = Field(None, max_length=128)
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
    # Single source of truth for patient-facing clinical message (Vietnamese).
    # Frontend must read this field; no hardcoded status->message maps allowed.
    clinical_message: str | None = None
    test_date: dt.date | None
    verified_by_user: bool
    # OCR originals (may be None for manual entries)
    original_value: float | None = None
    original_unit: str | None = None
    original_reference_range: str | None = None
    original_test_name: str | None = None
    # P0 clinical-integrity: formatted ORIGINAL-unit display string for the UI
    # (e.g. "88 µmol/L"). Never the canonical/SI-converted number.
    display: str | None = None
    # SI-normalized fields
    normalized_value_si: float | None = None
    normalized_unit_si: str | None = None
    data_quality_flag: str | None = None
    created_at: dt.datetime

    # ── Unified LabResult contract (additive; legacy fields above unchanged) ──
    # See app.domain.lab_semantics.LabSemantics. Every field here is derived
    # by the SAME resolver MetricOut uses, so the two screens cannot disagree.
    display_name: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    reference_unit: str | None = None
    reference_display: str | None = None
    reference_source: str | None = None
    severity: str | None = None
    interpretation_state: str | None = None
    needs_review: bool = False
    rule_version: str | None = None

    @model_validator(mode="after")
    def _populate_display(self) -> LabResultOut:
        """Compute the formatted ORIGINAL-unit display string (P0 integrity)."""
        from app.utils.number_format import format_lab_display

        disp_value = self.original_value if self.original_value is not None else self.value
        disp_unit = self.original_unit if self.original_unit is not None else self.unit
        self.display = format_lab_display(disp_value, disp_unit)
        return self

    @model_validator(mode="after")
    def _populate_clinical_message(self) -> LabResultOut:
        """Resolve status/severity/reference/message via the single shared
        resolver (`lab_semantics.resolve_lab_semantics`) — never independently.

        `original_reference_range` (whatever the patient/UI chose to display —
        source-printed, catalog, or manual) is passed through as the DISPLAY
        range only; it never changes what status/severity this row gets, which
        is always computed against the canonical registry's own bounds.
        """
        if not self.canonical_name:
            return self

        from app.domain.lab_semantics import resolve_lab_semantics

        try:
            semantics = resolve_lab_semantics(
                self.canonical_name,
                self.value,
                self.unit,
                printed_reference_text=self.original_reference_range or self.reference_range,
                printed_reference_unit=self.original_unit,
                normalized_value_si=self.normalized_value_si,
                normalized_unit_si=self.normalized_unit_si,
            )
        except Exception:  # noqa: BLE001 — schema must never crash, but must fail
            # CLOSED, not open: leaving whatever status was set upstream (which
            # could be a stale confident severity from before a reassignment)
            # is exactly the #153/#154 hazard this resolver exists to remove.
            self.status = "unknown"
            self.severity = "unknown"
            self.interpretation_state = "needs_review"
            self.needs_review = True
            self.clinical_message = None
            self.reference_range = None
            return self

        if semantics is None:
            # canonical_name genuinely unrecognised — never covered by
            # canonical classification either, not a new gap.
            if self.clinical_message is None and self.canonical_name and self.status:
                from app.services.lab import get_clinical_message

                self.clinical_message = get_clinical_message(self.canonical_name, self.status)
            return self

        self.status = semantics.status
        self.severity = semantics.severity
        self.interpretation_state = semantics.interpretation_state
        self.needs_review = semantics.needs_review
        self.clinical_message = semantics.clinical_message
        self.display_name = semantics.display_name
        self.reference_low = semantics.reference_low
        self.reference_high = semantics.reference_high
        self.reference_unit = semantics.reference_unit
        self.reference_display = semantics.reference_display
        self.reference_source = semantics.reference_source
        self.rule_version = semantics.rule_version
        # Legacy field: an uninterpretable row clears reference_range so a
        # patient cannot self-derive "above/below range" from a row we just
        # called unreadable — reference_display carries the None too.
        if semantics.needs_review:
            self.reference_range = None
        return self

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


class LabResultEditIn(BaseModel):
    """Extended partial-update payload for PATCH /patients/{id}/lab-results/{id}.

    All fields optional — only provided fields are applied.
    Extends the existing /correct endpoint’s scope to include metadata fields.
    """

    value: float | None = None
    unit: str | None = None
    test_name: str | None = Field(None, max_length=128)
    reference_range: str | None = Field(None, max_length=128)
    test_date: dt.date | None = None
    source_type: str | None = Field(None, max_length=64)
