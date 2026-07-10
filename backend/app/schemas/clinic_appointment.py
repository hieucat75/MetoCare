"""Clinic appointment management schemas (Clinic SaaS C1 M07).

A single output shape (`ClinicAppointmentOut`) — no field-level RBAC
narrowing is needed here, unlike M06's Care Coordinator narrowing:
RBAC_MATRIX.md's "Appointments (M07)" row gives all 6 non-Accountant roles
the same field visibility (row-level scoping for Doctor is enforced in the
route, not by hiding fields)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

_STATUS_PATTERN = (
    r"^(pending|confirmed|arrived|in_queue|in_consultation|completed|cancelled|no_show)$"
)


class ClinicAppointmentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    clinic_id: str
    branch_id: str
    patient_id: str
    doctor_id: str | None
    service_id: str
    price_snapshot: Decimal
    start_time: dt.datetime
    end_time: dt.datetime
    status: str
    created_by_user_id: str
    created_by_source: str
    linked_care_plan_item_id: str | None
    cancellation_reason: str | None
    cancelled_by_user_id: str | None
    cancelled_at: dt.datetime | None
    reschedule_of_id: str | None
    notes: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class ClinicAppointmentListOut(BaseModel):
    total: int
    items: list[ClinicAppointmentOut]


class ClinicAppointmentCreateRequest(BaseModel):
    branch_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    doctor_id: str | None = None
    service_id: str = Field(min_length=1)
    start_time: dt.datetime
    notes: str | None = Field(default=None, max_length=2000)
    # Owner/Admin-only — the route enforces the role check (`_has_full_access`),
    # not this schema; a non-owner/admin caller's reason string is ignored by
    # the service layer's `is_override_allowed=False`.
    override_working_hours_reason: str | None = Field(default=None, max_length=255)


class ClinicAppointmentCancelRequest(BaseModel):
    # Required — BR-M07-04's policy-violation flagging needs a real reason to
    # record/report, not an optional afterthought.
    reason: str = Field(min_length=1, max_length=500)


class ClinicAppointmentRescheduleRequest(BaseModel):
    start_time: dt.datetime
    reason: str = Field(min_length=1, max_length=500)
    branch_id: str | None = None
    doctor_id: str | None = None


class ClinicAppointmentNoShowRequest(BaseModel):
    # Optional — manual override case; the automated end-of-day job path
    # doesn't go through this schema at all.
    reason: str | None = Field(default=None, max_length=500)


class ClinicAppointmentArrivedOverrideRequest(BaseModel):
    # Required — BRD's "No-show → Arrived, lễ tân override có lý do".
    reason: str = Field(min_length=1, max_length=500)
