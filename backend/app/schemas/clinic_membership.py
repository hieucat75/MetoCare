"""Clinic membership + invitation request/response schemas (Clinic SaaS Phase C0)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class ClinicInvitationCreate(BaseModel):
    roles: list[str] = Field(min_length=1)
    branch_ids: list[str] = Field(default_factory=list)
    invited_email: str | None = None
    invited_phone: str | None = None


class ClinicInvitationOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    clinic_id: str
    invited_email: str | None
    invited_phone: str | None
    roles: list[str]
    branch_ids: list[str]
    status: str
    expires_at: dt.datetime
    invited_by_user_id: str
    accepted_by_user_id: str | None
    created_at: dt.datetime


class ClinicInvitationCreateOut(ClinicInvitationOut):
    # Present only once, at creation — never persisted/returned again after.
    raw_token: str


class ClinicInvitationListOut(BaseModel):
    total: int
    items: list[ClinicInvitationOut]


class ClinicInvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=1)


class ClinicMembershipOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    user_id: str
    clinic_id: str
    roles: list[str]
    branch_ids: list[str]
    doctor_profile_id: str | None
    status: str
    is_primary: bool
    joined_at: dt.date | None
    left_at: dt.date | None
    created_at: dt.datetime
    updated_at: dt.datetime


class ClinicMembershipListOut(BaseModel):
    total: int
    items: list[ClinicMembershipOut]


class ClinicMembershipUpdate(BaseModel):
    roles: list[str] | None = Field(default=None, min_length=1)
    branch_ids: list[str] | None = None
    status: str | None = Field(default=None, pattern="^(invited|active|suspended|removed)$")


class MyClinicMembershipOut(BaseModel):
    """One entry in the caller's own clinic-switcher list — `GET
    /clinics/memberships/mine`. Distinct from `ClinicMembershipOut` (the
    Owner/Admin staff-management view of one clinic's members): this always
    reflects the CALLER's own row and includes the clinic's display name,
    which staff-list consumers already get by fetching the clinic itself."""

    model_config = {"from_attributes": True}

    id: str
    clinic_id: str
    clinic_name: str
    clinic_status: str
    roles: list[str]
    branch_ids: list[str]
    is_primary: bool


class MyClinicMembershipListOut(BaseModel):
    items: list[MyClinicMembershipOut]
