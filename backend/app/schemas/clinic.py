"""Clinic + branch request/response schemas (Clinic SaaS Phase C0)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class ClinicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    tax_code: str | None = Field(default=None, max_length=20)
    license_no: str | None = Field(default=None, max_length=64)
    clinic_type: str | None = Field(default=None, max_length=32)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)


class ClinicSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    tax_code: str | None = Field(default=None, max_length=20)
    license_no: str | None = Field(default=None, max_length=64)
    clinic_type: str | None = Field(default=None, max_length=32)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    branding: dict | None = None
    cancellation_policy: dict | None = None
    queue_config: dict | None = None
    overbooking_policy: dict | None = None


class ClinicOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    legal_name: str | None
    tax_code: str | None
    license_no: str | None
    clinic_type: str | None
    status: str
    address: str | None
    phone: str | None
    email: str | None
    branding: dict | None
    cancellation_policy: dict | None
    queue_config: dict | None
    overbooking_policy: dict | None
    deactivated_at: dt.datetime | None
    restored_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime


class ClinicListOut(BaseModel):
    total: int
    items: list[ClinicOut]


class ClinicBranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    working_hours: dict
    address: dict | None = None
    phone: str | None = Field(default=None, max_length=32)


class ClinicBranchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    working_hours: dict | None = None
    address: dict | None = None
    phone: str | None = Field(default=None, max_length=32)


class ClinicBranchStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|paused|archived)$")


class ClinicBranchOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    clinic_id: str
    name: str
    address: dict | None
    phone: str | None
    working_hours: dict
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


class ClinicBranchListOut(BaseModel):
    total: int
    items: list[ClinicBranchOut]
