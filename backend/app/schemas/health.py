"""Health tracking schemas."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


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
    measured_at: dt.datetime
    status: str | None
    source: str | None = None  # self_report/manual | lab_result | device …

    model_config = {"from_attributes": True}


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
