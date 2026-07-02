"""Health tracking schemas."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, model_validator


class MetricUpdate(BaseModel):
    """Partial-update payload for PATCH /metrics/{metric_id}.

    All fields are optional — only provided fields are applied.
    """

    metric_type: str | None = None
    value: float | None = None
    unit: str | None = None
    measured_at: dt.datetime | None = None
    source: str | None = None
    normal_range_min: float | None = None
    normal_range_max: float | None = None


class MetricCreate(BaseModel):
    metric_type: str = Field(..., examples=["fasting_glucose"])
    value: float
    unit: str | None = None
    measured_at: dt.datetime | None = None
    source: str | None = "manual"
    normal_range_min: float | None = None
    normal_range_max: float | None = None


class MetricOut(BaseModel):
    id: str
    metric_type: str
    value: float
    unit: str | None
    # P0 clinical-integrity: ORIGINAL value+unit as recorded (e.g. 88 µmol/L).
    # value/unit above stay CANONICAL for internal classification. `display` is
    # the formatted original the UI should show. All three are additive/back-compat.
    original_value: float | None = None
    original_unit: str | None = None
    display: str | None = None
    measured_at: dt.datetime
    status: str | None
    source: str | None = None  # self_report/manual | lab_result | device …
    clinical_message: str | None = (
        None  # canonical Vietnamese clinical text (single source of truth)
    )
    is_critical: bool = False  # True only when canonical re-classification is 'critical'

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _populate_display(self) -> MetricOut:
        """Compute the formatted ORIGINAL-unit display string (P0 integrity)."""
        from app.utils.number_format import format_lab_display

        disp_value = self.original_value if self.original_value is not None else self.value
        disp_unit = self.original_unit if self.original_unit is not None else self.unit
        self.display = format_lab_display(disp_value, disp_unit)
        return self

    @model_validator(mode="after")
    def _populate_clinical_message(self) -> MetricOut:
        """Compute canonical clinical_message for patient-facing banner.

        UNIT-SAFE: normalises value to canonical unit (e.g. mmol/L → mg/dL for
        glucose) before re-classifying, so that old HealthMetric rows that were
        promoted with the wrong unit (e.g. value=5.7 stored as mmol/L instead of
        102.7 mg/dL) still get the correct clinical message.

        This is the SINGLE SOURCE OF TRUTH for clinical text.  The frontend must
        display this field and must NOT recompute clinical meaning from raw
        value/unit/thresholds.

        Algorithm:
          1. Normalise value+unit → canonical unit (mg/dL for glucose).
          2. Re-classify using canonical thresholds.
          3. Map (biomarker, status) → Vietnamese clinical message.
          4. Return None only when biomarker is unknown/unsupported.
        """
        if self.clinical_message is not None:
            return self  # caller already set it — honour that

        try:
            from app.domain.lab_interpreter import _ALIAS_INDEX, classify_value
            from app.domain.lab_normalization import normalize_value_to_si
            from app.services.lab import get_clinical_message

            # Normalise to canonical unit (no-op when already canonical).
            # HEURISTIC GUARD: for glucose metrics, if the stored unit is missing/
            # unknown AND the value is implausibly small for mg/dL (< 30), treat it
            # as mmol/L.  No human survives fasting glucose < 30 mg/dL without
            # emergency care, so any value this small with an unknown unit MUST be
            # in mmol/L from an OCR path that dropped the unit string.
            raw_value = self.value
            raw_unit = self.unit or ""
            glucose_metrics = {"fasting_glucose", "postprandial_glucose"}
            if self.metric_type in glucose_metrics:
                unit_clean = raw_unit.strip().lower().replace(" ", "")
                if unit_clean not in ("mg/dl", "mmol/l", "mmol") and raw_value < 30:
                    # Unit unknown and value implausibly small → must be mmol/L
                    raw_unit = "mmol/L"

            # HEURISTIC GUARD (general): for any biomarker with a known SI/display
            # unit, if the stored value exceeds the physiological_max for the
            # canonical unit, the value must be expressed in the SI unit.
            # This covers two failure modes from old _promote_row code:
            #   A) unit=None/'' AND value=87.7 (µmol/L dropped during promotion)
            #   B) unit='mg/dL' AND value=87.66 (µmol/L value stored with wrong unit)
            # Both: 87.7 > physiological_max(30 mg/dL) → treat as µmol/L
            # → normalize → 0.992 mg/dL → NORMAL (not CRITICAL)
            spec = _ALIAS_INDEX.get(self.metric_type)
            if spec and spec.si_unit and spec.physiological_max is not None:
                unit_norm = raw_unit.strip().lower().replace("µ", "u").replace("μ", "u")
                si_norm = spec.si_unit.strip().lower().replace("µ", "u").replace("μ", "u")
                already_si = unit_norm == si_norm
                if not already_si and raw_value > spec.physiological_max:
                    # Value exceeds what is physiologically possible in the
                    # canonical unit → must be in the SI unit (stored incorrectly).
                    raw_unit = spec.si_unit

            canonical_value, _ = normalize_value_to_si(raw_value, raw_unit, self.metric_type)
            # Re-classify using canonical thresholds.
            status_enum = classify_value(self.metric_type, canonical_value)
            if status_enum is not None and status_enum.value != "unknown":
                canonical_status = status_enum.value
                self.is_critical = canonical_status == "critical"
                self.clinical_message = get_clinical_message(self.metric_type, canonical_status)
                # Also update status to the canonical re-classification so that
                # callers reading MetricOut.status get the correct value (even
                # if the DB row has a stale/wrong status from before the unit-
                # normalization fix in _promote_row).
                self.status = canonical_status
        except Exception:  # noqa: BLE001 — schema must never crash
            pass

        return self


class TrendOut(BaseModel):
    metric_type: str
    days: int
    count: int
    min: float | None = None
    max: float | None = None
    avg: float | None = None
    first: float | None = None
    last: float | None = None
    direction: str | None = None
