"""Clinic patient management schemas (Clinic SaaS C1 M06).

Two distinct output shapes enforce RBAC_MATRIX.md's "Patient admin record
(M06)" row at the field level, not just the route level (BR-M06-03's
"Receptionist never receives clinical content" discipline, generalized to
Care Coordinator's narrower "care context" shape):

- ``ClinicPatientAdminOut`` — full administrative record (Owner/Admin/Doctor/
  Nurse/Reception).
- ``ClinicPatientCareContextOut`` — Care Coordinator's narrow subset: no
  dob/address/internal_notes.

Routes never rely on FastAPI's automatic ``response_model`` filtering for
these two (a Pydantic Union could match the wrong variant since the narrow
shape's fields are a strict subset of the full shape's) — they explicitly
pick a model instance and return it via ``JSONResponse(jsonable_encoder(...))``
instead. See ``app/api/v1/routes/clinic_patients.py``.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

_STATUS_PATTERN = r"^(active|inactive|merged)$"


class ClinicPatientAdminOut(BaseModel):
    """Full administrative record. Fields tied to the clinic relationship
    (id/patient_code/status/internal_notes/first_seen_at/created_at/
    updated_at) are ``None`` when the caller sees this patient only via an
    active cross-clinic ``Consent`` grant and has never linked/created the
    patient at their own clinic — there is no relationship row to source
    them from in that case (M06 plan §1's consent-shared read path)."""

    id: str | None
    patient_id: str
    clinic_id: str
    patient_code: str | None
    status: str | None
    internal_notes: str | None
    first_seen_at: dt.datetime | None
    full_name: str | None
    dob: str | None
    gender: str | None
    address: str | None
    phone: str | None
    created_at: dt.datetime | None
    updated_at: dt.datetime | None


class ClinicPatientCareContextOut(BaseModel):
    id: str
    patient_id: str
    patient_code: str
    status: str
    full_name: str | None
    phone: str | None
    first_seen_at: dt.datetime


class ClinicPatientListOut(BaseModel):
    total: int
    items: list[dict]


class PatientCandidateOut(BaseModel):
    patient_id: str
    full_name: str | None
    dob: str | None
    phone: str | None
    already_linked: bool


class ClinicPatientLinkRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    patient_code: str | None = Field(default=None, min_length=1, max_length=32)


class ClinicPatientCreateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=20)
    dob: str = Field(min_length=1, max_length=10)
    gender: str = Field(min_length=1, max_length=16)
    address: str | None = Field(default=None, max_length=500)
    patient_code: str | None = Field(default=None, min_length=1, max_length=32)
    # AC-M06-02 / BRD §6.8 "hai bệnh nhân dùng chung SĐT": when the
    # phone-exact-match dedup check finds a candidate, create is refused
    # (409 DUPLICATE_CANDIDATE) unless the caller explicitly re-submits with
    # a reason to proceed anyway. Never auto-merges, never auto-blocks.
    override_dedup_reason: str | None = Field(default=None, max_length=255)


class ClinicPatientUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern=_STATUS_PATTERN)
    internal_notes: str | None = Field(default=None, max_length=4000)
