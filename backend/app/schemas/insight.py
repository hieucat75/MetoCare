"""Response schemas for the Clinical Insight Engine (PA-11).

Mirror the ``services.clinical_insight`` dataclasses. ``from_attributes`` lets the
routes build these directly from the service dataclasses via ``model_validate``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator


class TrendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    direction: str  # up | down | flat | none
    pct: float | None = None  # signed % change vs previous reading
    improved: bool | None = None  # True=better, False=worse, None=stable/unknown
    label: str


class MetricInsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric_type: str
    label: str
    value: float
    unit: str | None = None
    # P0 clinical-integrity: ORIGINAL value+unit as recorded (value/unit stay
    # canonical for internal logic). `display` is the formatted original for the UI.
    original_value: float | None = None
    original_unit: str | None = None
    display: str | None = None
    status: str  # normal | low | high | critical | unknown

    @model_validator(mode="after")
    def _populate_display(self) -> MetricInsightOut:
        from app.utils.number_format import format_lab_display

        disp_value = self.original_value if self.original_value is not None else self.value
        disp_unit = self.original_unit if self.original_unit is not None else self.unit
        self.display = format_lab_display(disp_value, disp_unit)
        return self
    trend: TrendOut
    meaning: str
    risks: list[str]
    lifestyle: list[str]
    follow_up: str
    priority: str  # monitor | watch | see_doctor
    priority_label: str
    disclaimer: str


class HealthSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    abnormal_count: int
    improved: list[str]
    worsened: list[str]
    stable: list[str]
    positives: list[str]
    focus: list[str]
    overall_risk: str  # low | medium | high
    top_action: str
    disclaimer: str
