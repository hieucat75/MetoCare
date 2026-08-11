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
        """Derive clinical_message from canonical_name + status (single source of truth).

        Applies the same physiological_max heuristic as MetricOut so that LabResult
        rows that were stored with the wrong unit (e.g. creatinine 87.66 µmol/L stored
        as value=87.66, unit='mg/dL') are re-classified correctly at serialization time.

        Algorithm:
          1. Use normalized_value_si if available; else raw value.
          2. Apply physiological_max guard: if value > physiological_max for the
             canonical unit AND unit is NOT the SI unit, treat value as SI unit and
             re-normalize to canonical unit.
          3. Re-classify using canonical thresholds.
          4. Derive clinical_message from (canonical_name, canonical_status).
        """
        if not self.canonical_name:
            return self

        # P0 read-path guard. Rows ALREADY in production can carry an analyte and
        # a unit from different dimensions — `rbc` with `L/L` is a hematocrit
        # fraction filed as a red cell count. Classifying such a row produced
        # "Nguy hiểm" on this screen and "Rất thấp" on the metrics screen for the
        # same record. Neither claim is supportable, so make none: no severity,
        # no reference comparison, and a message that says only what is true.
        # Runs BEFORE any classification, so it also covers rows written before
        # the write-path fix and ahead of data remediation.
        from app.domain.analyte_units import NEEDS_REVIEW_MESSAGE, is_unsafe_pair

        if is_unsafe_pair(self.canonical_name, self.unit):
            self.status = "unknown"
            self.clinical_message = NEEDS_REVIEW_MESSAGE
            return self

        try:
            from app.domain.lab_interpreter import _ALIAS_INDEX, classify_value
            from app.domain.lab_normalization import normalize_value_to_si
            from app.services.lab import get_clinical_message

            spec = _ALIAS_INDEX.get(self.canonical_name)
            if spec is None:
                # Unknown biomarker — fall through to DB status
                if self.clinical_message is None and self.status:
                    self.clinical_message = get_clinical_message(self.canonical_name, self.status)
                return self

            # Prefer normalized_value_si when available (more accurate).
            raw_value = (
                self.normalized_value_si if self.normalized_value_si is not None else self.value
            )
            raw_unit = (
                self.normalized_unit_si
                if self.normalized_unit_si is not None
                else (self.unit or "")
            )

            if raw_value is None:
                if self.clinical_message is None and self.status:
                    self.clinical_message = get_clinical_message(self.canonical_name, self.status)
                return self

            # Physiological_max heuristic: if value exceeds what is physiologically
            # possible in the canonical unit, it must be expressed in the SI unit.
            if spec.si_unit and spec.physiological_max is not None:
                unit_norm = (raw_unit or "").strip().lower().replace("µ", "u").replace("μ", "u")
                # Guard: check if already in CANONICAL unit (not SI unit).
                # For creatinine: canonical='mg/dL', si='µmol/L'.
                # If raw_unit IS mg/dL, already_canonical=True → skip heuristic.
                # If raw_unit is µmol/L (old mis-stored row), already_canonical=False
                # and value 88 > physiological_max 30 → re-treat as SI unit → correct.
                canonical_norm = spec.unit.strip().lower().replace("µ", "u").replace("μ", "u")
                already_canonical = unit_norm == canonical_norm
                if not already_canonical and raw_value > spec.physiological_max:
                    # Value is physiologically impossible in canonical unit → must be SI unit.
                    raw_unit = spec.si_unit

            canonical_value, _ = normalize_value_to_si(raw_value, raw_unit, self.canonical_name)
            status_enum = classify_value(self.canonical_name, canonical_value)
            if status_enum is not None and status_enum.value != "unknown":
                canonical_status = status_enum.value
                self.status = canonical_status
                self.clinical_message = get_clinical_message(self.canonical_name, canonical_status)
            elif self.clinical_message is None and self.status:
                self.clinical_message = get_clinical_message(self.canonical_name, self.status)
        except Exception:  # noqa: BLE001 — schema must never crash
            if self.clinical_message is None and self.canonical_name and self.status:
                from app.services.lab import get_clinical_message

                self.clinical_message = get_clinical_message(self.canonical_name, self.status)
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
