"""Clinic service/pricing catalog schemas (Clinic SaaS C0 base + C1 M05 fields).

Field set per `docs/brd/v2.0/m05-services-pricing.md` §5.3. `code`/`specialty`/
`duration_minutes`/`type` are required at creation (BRD "Bắt buộc" column) but
optional on update (partial-update convention already used by every other
Clinic SaaS PATCH schema in this codebase)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

_CODE_PATTERN = r"^[A-Z0-9-]+$"
_TYPE_PATTERN = r"^(single|package)$"
_STATUS_PATTERN = r"^(active|inactive)$"
# Codex second-pass review P1: money as float loses precision; Decimal +
# explicit max_digits/decimal_places (matching the DB's Numeric(12,2)) +
# an upper bound reject overflow/non-finite values at the API boundary.
_PRICE_FIELD = Field(ge=0, le=Decimal("9999999999.99"), max_digits=12, decimal_places=2)


class ClinicServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=32, pattern=_CODE_PATTERN)
    specialty: str = Field(min_length=1, max_length=64)
    duration_minutes: int = Field(ge=5, le=240)
    price: Decimal = _PRICE_FIELD
    type: str = Field(default="single", pattern=_TYPE_PATTERN)
    branch_ids: list[str] | None = None
    doctor_ids: list[str] | None = None
    package_visit_count: int | None = Field(default=None, ge=1)
    duration_months: int | None = Field(default=None, ge=1)
    included_items: dict | None = None
    benefits: dict | None = None
    cancellation_refund_policy: dict | None = None
    # type<->package-field cross-field validation (Codex round-4 fix) lives
    # in the service layer (`clinic_service_catalog._assert_type_field_consistency`),
    # not here — Update needs the same invariant checked against the FINAL
    # merged state (existing row + PATCH payload), which a schema-only
    # validator can't see (no DB access). One shared function, one set of
    # error messages, for both Create and Update.


class ClinicServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=32, pattern=_CODE_PATTERN)
    specialty: str | None = Field(default=None, min_length=1, max_length=64)
    duration_minutes: int | None = Field(default=None, ge=5, le=240)
    price: Decimal | None = Field(
        default=None, ge=0, le=Decimal("9999999999.99"), max_digits=12, decimal_places=2
    )
    type: str | None = Field(default=None, pattern=_TYPE_PATTERN)
    branch_ids: list[str] | None = None
    doctor_ids: list[str] | None = None
    package_visit_count: int | None = Field(default=None, ge=1)
    duration_months: int | None = Field(default=None, ge=1)
    included_items: dict | None = None
    benefits: dict | None = None
    cancellation_refund_policy: dict | None = None
    status: str | None = Field(default=None, pattern=_STATUS_PATTERN)


class ClinicServiceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    clinic_id: str
    name: str
    code: str | None
    specialty: str | None
    duration_minutes: int | None
    price: Decimal
    type: str
    branch_ids: list[str] | None
    doctor_ids: list[str] | None
    package_visit_count: int | None
    duration_months: int | None
    included_items: dict | None
    benefits: dict | None
    cancellation_refund_policy: dict | None
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


class ClinicServiceListOut(BaseModel):
    total: int
    items: list[ClinicServiceOut]
