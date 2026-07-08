"""Clinic service/pricing catalog schemas (Clinic SaaS Phase C0, M05)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class ClinicServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price: float = Field(ge=0)
    branch_ids: list[str] | None = None
    package_visit_count: int | None = Field(default=None, ge=1)


class ClinicServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    price: float | None = Field(default=None, ge=0)
    branch_ids: list[str] | None = None
    package_visit_count: int | None = Field(default=None, ge=1)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class ClinicServiceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    clinic_id: str
    name: str
    price: float
    branch_ids: list[str] | None
    package_visit_count: int | None
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


class ClinicServiceListOut(BaseModel):
    total: int
    items: list[ClinicServiceOut]
