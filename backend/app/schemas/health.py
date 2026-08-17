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
    # Confirmed source-report reference range text carried over from the
    # promoting LabResult (see HealthMetric.source_reference_text). Passed
    # into resolve_lab_semantics below so this schema resolves the same
    # SOURCE_REPORT provenance LabResultOut does for the same result — never
    # read/parsed independently.
    source_reference_text: str | None = None
    display: str | None = None
    measured_at: dt.datetime
    status: str | None
    source: str | None = None  # self_report/manual | lab_result | device …
    clinical_message: str | None = (
        None  # canonical Vietnamese clinical text (single source of truth)
    )
    is_critical: bool = False  # True only when canonical re-classification is 'critical'

    # ── Unified LabResult contract (additive; legacy fields above unchanged) ──
    # See app.domain.lab_semantics.LabSemantics. Every field here is derived
    # by the SAME resolver LabResultOut uses, so the two screens cannot disagree.
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
        """Resolve status/severity/reference/message via the single shared
        resolver (`lab_semantics.resolve_lab_semantics`) — never independently.

        This is the SINGLE SOURCE OF TRUTH for clinical text. The frontend must
        display these fields and must NOT recompute clinical meaning from raw
        value/unit/thresholds.

        Always resolves fresh — a `clinical_message` set upstream (e.g. by a
        caller before construction) is exactly as unsupportable as one
        computed here for a guarded/unsafe analyte-unit pair, so it is never
        trusted as a way to skip resolution.
        """
        from app.domain.lab_semantics import resolve_lab_semantics

        try:
            semantics = resolve_lab_semantics(
                self.metric_type,
                self.value,
                self.unit,
                printed_reference_text=self.source_reference_text,
                printed_reference_unit=self.original_unit,
                normalized_value_si=None,
                normalized_unit_si=None,
            )
        except Exception:  # noqa: BLE001 — schema must never crash, but must fail
            # CLOSED, not open: leaving whatever status was set upstream (which
            # could be a stale confident severity) is exactly the #153/#154
            # hazard this resolver exists to remove.
            self.status = "unknown"
            self.is_critical = False
            self.severity = "unknown"
            self.interpretation_state = "needs_review"
            self.needs_review = True
            self.clinical_message = None
            return self

        if semantics is None:
            # metric_type is a non-lab vital (BP, weight, ...) never covered by
            # canonical classification — keep whatever the caller's own
            # classifier (health_metrics.classify_status) already set.
            return self

        self.status = semantics.status
        self.is_critical = semantics.status == "critical"
        self.clinical_message = semantics.clinical_message
        self.severity = semantics.severity
        self.interpretation_state = semantics.interpretation_state
        self.needs_review = semantics.needs_review
        self.display_name = semantics.display_name
        self.reference_low = semantics.reference_low
        self.reference_high = semantics.reference_high
        self.reference_unit = semantics.reference_unit
        self.reference_display = semantics.reference_display
        self.reference_source = semantics.reference_source
        self.rule_version = semantics.rule_version
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
