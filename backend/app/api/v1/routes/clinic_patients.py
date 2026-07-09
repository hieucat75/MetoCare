"""Clinic patient management routes (Clinic SaaS C1 M06).

Field-level RBAC enforcement for the "Patient admin record (M06)" row
(RBAC_MATRIX.md §3): full record for Owner/Admin/Doctor/Nurse/Reception,
narrow "care context" for Care Coordinator, 403 for Accountant. The list and
detail routes deliberately do NOT use FastAPI's `response_model` for this —
they pick the correct Pydantic instance in code and return it via
`JSONResponse(jsonable_encoder(...))`, so the narrow shape can never
accidentally carry the full shape's fields (a Union-based response_model
risks Pydantic matching the wrong variant, since the narrow shape's fields
are a strict subset of the full shape's).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.deps_clinic_saas import require_clinic_saas_enabled
from app.api.deps_tenant import TenantContext, get_tenant_context
from app.core.rbac import (
    assert_clinic_writable,
    assert_path_clinic_matches_tenant,
    require_clinic_roles,
)
from app.models.clinic import ClinicRole
from app.schemas.clinic_patient import (
    ClinicPatientCreateRequest,
    ClinicPatientLinkRequest,
    ClinicPatientUpdateRequest,
    PatientCandidateOut,
)
from app.services import clinic as clinic_service_lookup
from app.services import clinic_patients as patients_service
from app.services.clinic_patients import ClinicPatientDuplicateError, ClinicPatientError
from app.services.consent_guard import ConsentGuard

router = APIRouter(
    prefix="/clinics/{clinic_id}/patients",
    tags=["clinic_patients"],
    dependencies=[Depends(require_clinic_saas_enabled)],
)

_CLINIC_NOT_FOUND_DETAIL = "Không tìm thấy phòng khám."
_PATIENT_NOT_FOUND_DETAIL = "Không tìm thấy bệnh nhân."
_FULL_ACCESS_ROLES = (
    ClinicRole.OWNER,
    ClinicRole.ADMIN,
    ClinicRole.DOCTOR,
    ClinicRole.NURSE,
    ClinicRole.RECEPTIONIST,
)
_READ_ROLES = (*_FULL_ACCESS_ROLES, ClinicRole.CARE_COORDINATOR)
_WRITE_ROLES = (ClinicRole.OWNER, ClinicRole.ADMIN, ClinicRole.RECEPTIONIST)
_UPDATE_ROLES = (ClinicRole.OWNER, ClinicRole.ADMIN)


def _has_full_access(roles: frozenset[str]) -> bool:
    return bool(set(roles) & set(_FULL_ACCESS_ROLES))


def _admin_dict(clinic_id: str, row: dict) -> dict:
    return {
        "id": row.get("id"),
        "patient_id": row["patient_id"],
        "clinic_id": clinic_id,
        "patient_code": row.get("patient_code"),
        "status": row.get("status"),
        "internal_notes": row.get("internal_notes"),
        "first_seen_at": row.get("first_seen_at"),
        "full_name": row.get("full_name"),
        "dob": row.get("dob"),
        "gender": row.get("gender"),
        "address": row.get("address"),
        "phone": row.get("phone"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _care_context_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "patient_id": row["patient_id"],
        "patient_code": row["patient_code"],
        "status": row["status"],
        "full_name": row.get("full_name"),
        "phone": row.get("phone"),
        "first_seen_at": row["first_seen_at"],
    }


def _relationship_row(relationship, fields: dict) -> dict:
    return {
        "id": relationship.id,
        "patient_id": relationship.patient_id,
        "patient_code": relationship.patient_code,
        "status": relationship.status,
        "internal_notes": relationship.internal_notes,
        "first_seen_at": relationship.first_seen_at,
        "created_at": relationship.created_at,
        "updated_at": relationship.updated_at,
        **fields,
    }


@router.get("")
def list_patients(
    clinic_id: str,
    search: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> JSONResponse:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_READ_ROLES)
    items, total = patients_service.get_roster(
        db, clinic_id=clinic_id, search=search, skip=skip, limit=limit
    )
    if _has_full_access(tenant.roles):
        payload = {"total": total, "items": [_admin_dict(clinic_id, item) for item in items]}
    else:
        payload = {"total": total, "items": [_care_context_dict(item) for item in items]}
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/search-candidates", response_model=PatientCandidateOut | None)
def search_candidates(
    clinic_id: str,
    phone: str = Query(min_length=1),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> PatientCandidateOut | None:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_WRITE_ROLES)
    try:
        candidate = patients_service.search_candidate(db, clinic_id=clinic_id, phone=phone)
    except ClinicPatientError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return PatientCandidateOut(**candidate) if candidate else None


@router.post("/link", status_code=status.HTTP_201_CREATED)
def link_patient(
    clinic_id: str,
    payload: ClinicPatientLinkRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> JSONResponse:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_WRITE_ROLES)
    clinic = clinic_service_lookup.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL)
    assert_clinic_writable(clinic)
    try:
        relationship = patients_service.link_patient(
            db,
            clinic_id=clinic_id,
            actor_id=tenant.user_id,
            patient_id=payload.patient_id,
            patient_code=payload.patient_code,
        )
    except ClinicPatientError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    fields = patients_service.get_profile_fields(db, patient_id=relationship.patient_id) or {}
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=jsonable_encoder(_admin_dict(clinic_id, _relationship_row(relationship, fields))),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_patient(
    clinic_id: str,
    payload: ClinicPatientCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> JSONResponse:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_WRITE_ROLES)
    clinic = clinic_service_lookup.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL)
    assert_clinic_writable(clinic)
    try:
        relationship = patients_service.create_patient(
            db,
            clinic_id=clinic_id,
            actor_id=tenant.user_id,
            full_name=payload.full_name,
            phone=payload.phone,
            dob=payload.dob,
            gender=payload.gender,
            address=payload.address,
            patient_code=payload.patient_code,
            override_dedup_reason=payload.override_dedup_reason,
        )
    except ClinicPatientDuplicateError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"code": "DUPLICATE_CANDIDATE", "candidate": jsonable_encoder(exc.candidate)},
        )
    except ClinicPatientError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    fields = patients_service.get_profile_fields(db, patient_id=relationship.patient_id) or {}
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=jsonable_encoder(_admin_dict(clinic_id, _relationship_row(relationship, fields))),
    )


@router.get("/{patient_id}")
def get_patient_detail(
    clinic_id: str,
    patient_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> JSONResponse:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_READ_ROLES)
    fields = patients_service.get_profile_fields(db, patient_id=patient_id)
    if fields is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PATIENT_NOT_FOUND_DETAIL)

    relationship = patients_service.get_own_clinic_relationship(
        db, clinic_id=clinic_id, patient_id=patient_id
    )
    has_full_access = _has_full_access(tenant.roles)
    if relationship is None:
        # No own-clinic relationship — only reachable via an active
        # cross-clinic Consent grant (M06 plan §1). Raises ConsentDenied
        # (→ global 403 handler) on failure; never caught here, matching the
        # rest of the codebase's ConsentGuard convention (clinical_copilot.py
        # lets it propagate the same way for its own consent checks).
        if not has_full_access:
            # Care Coordinator's narrow shape has no meaning without an own-
            # clinic relationship row (no patient_code/status to show) — the
            # consent-shared path is an administrative-record concept only.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_PATIENT_NOT_FOUND_DETAIL
            )
        ConsentGuard(db).require(
            patient_id,
            consent_type="clinic_admin_record",
            data_scope="administrative",
            actor_id=clinic_id,
            actor_type="clinic",
        )
        db.commit()
        payload = _admin_dict(clinic_id, {"patient_id": patient_id, **fields})
        return JSONResponse(content=jsonable_encoder(payload))

    row = _relationship_row(relationship, fields)
    payload = _admin_dict(clinic_id, row) if has_full_access else _care_context_dict(row)
    return JSONResponse(content=jsonable_encoder(payload))


@router.patch("/{patient_id}")
def update_patient(
    clinic_id: str,
    patient_id: str,
    payload: ClinicPatientUpdateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> JSONResponse:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_UPDATE_ROLES)
    clinic = clinic_service_lookup.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL)
    assert_clinic_writable(clinic)

    relationship = patients_service.get_own_clinic_relationship(
        db, clinic_id=clinic_id, patient_id=patient_id
    )
    if relationship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PATIENT_NOT_FOUND_DETAIL)
    try:
        relationship = patients_service.update_relationship(
            db,
            relationship=relationship,
            actor_id=tenant.user_id,
            status=payload.status,
            internal_notes=payload.internal_notes,
        )
    except ClinicPatientError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    fields = patients_service.get_profile_fields(db, patient_id=patient_id) or {}
    return JSONResponse(
        content=jsonable_encoder(_admin_dict(clinic_id, _relationship_row(relationship, fields)))
    )
