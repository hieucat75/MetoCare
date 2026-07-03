"""Admin — Patient Records Management routes.

INTERNAL_ADMIN / SUPER_ADMIN + MFA only. List/search/filter/paginate patient
records system-wide, view a single patient's aggregated detail, and
activate/deactivate the underlying account. Every read/write is audited.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_session, require_mfa, require_roles
from app.models.user import UserRole
from app.schemas.admin_patient import (
    AdminPatientAuditEntryOut,
    AdminPatientConsentOut,
    AdminPatientConsultationOut,
    AdminPatientDetailOut,
    AdminPatientListItemOut,
    AdminPatientListOut,
    PatientStatusUpdate,
)
from app.services import admin_patients, audit
from app.services.admin_patients import age_from_dob
from app.services.patient_summary import build_summary

router = APIRouter(prefix="/admin/patients", tags=["admin-patients"])

_admin_only = require_roles(UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)


@router.get("", response_model=AdminPatientListOut)
def list_patients(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    gender: str | None = Query(default=None),
    has_labs: bool | None = Query(default=None),
    has_meds: bool | None = Query(default=None),
    has_consent: bool | None = Query(default=None),
    created_from: dt.date | None = Query(default=None),
    created_to: dt.date | None = Query(default=None),
    age_group: str | None = Query(default=None),
    sort: str = Query(default="created_at_desc"),
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> AdminPatientListOut:
    """List patients system-wide with search/filter/pagination. Admin + MFA only."""
    is_active = {"active": True, "inactive": False}.get(status_filter or "")
    items, total = admin_patients.list_patients(
        db,
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        gender=gender,
        has_labs=has_labs,
        has_meds=has_meds,
        has_consent=has_consent,
        created_from=created_from,
        created_to=created_to,
        age_group=age_group,
        sort=sort,
    )
    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="patient_list",
    )
    db.commit()
    return AdminPatientListOut(
        total=total, items=[AdminPatientListItemOut(**item) for item in items]
    )


@router.get("/{patient_id}", response_model=AdminPatientDetailOut)
def get_patient_detail(
    patient_id: str,
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> AdminPatientDetailOut:
    """Get full patient detail: profile, clinical summary, consent, consultations, audit trail."""
    found = admin_patients.get_patient(db, patient_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    profile, user = found

    consent = admin_patients.get_patient_consent(db, profile.user_id)
    consultations = admin_patients.get_patient_consultations(db, patient_id)
    audit_entries = admin_patients.get_patient_audit_log(
        db, patient_id=patient_id, user_id=profile.user_id
    )
    last_activity = audit_entries[0].timestamp if audit_entries else None
    summary = build_summary(db, patient_id=patient_id)

    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_read",
        resource_type="patient_detail",
        resource_id=patient_id,
    )
    db.commit()

    return AdminPatientDetailOut(
        id=profile.id,
        user_id=user.id,
        email=user.email,
        full_name=profile.full_name,
        phone=profile.phone or user.phone,
        dob=profile.dob,
        age=age_from_dob(profile.dob),
        gender=profile.gender,
        address=profile.address,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        waist_cm=profile.waist_cm,
        risk_segment=profile.risk_segment,
        known_conditions=profile.known_conditions,
        allergies=profile.allergies,
        family_history=profile.family_history,
        lifestyle_profile=profile.lifestyle_profile,
        is_active=user.is_active,
        created_at=profile.created_at,
        last_activity_at=last_activity,
        consent_status=(
            "revoked" if consent and consent.revoked_at else "valid" if consent else "none"
        ),
        consent=AdminPatientConsentOut.model_validate(consent) if consent else None,
        consultations=[AdminPatientConsultationOut(**c) for c in consultations],
        audit_log=[AdminPatientAuditEntryOut.model_validate(a) for a in audit_entries],
        summary=summary,
    )


@router.patch("/{patient_id}/status", response_model=AdminPatientListItemOut)
def update_patient_status(
    patient_id: str,
    payload: PatientStatusUpdate,
    actor: CurrentUser = Depends(_admin_only),
    _mfa: CurrentUser = Depends(require_mfa),
    db: Session = Depends(get_session),
) -> AdminPatientListItemOut:
    """Activate or deactivate the account behind a patient record."""
    try:
        admin_patients.update_patient_status(
            db, patient_id=patient_id, is_active=payload.is_active, requester_id=actor.id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    audit.record(
        db,
        actor_type="admin",
        actor_id=actor.id,
        action="admin_action",
        resource_type="patient_status",
        resource_id=patient_id,
    )
    db.commit()

    # Re-fetch the enriched row (lab/medication counts, consent, last activity)
    # directly by id — NOT via list_patients/search, which is bounded by
    # _CANDIDATE_LIMIT and could miss a patient outside that window, turning a
    # successful write into an unhandled 500 (see PR #85 review).
    item = admin_patients.get_patient_list_item(db, patient_id)
    if item is None:
        # The write above already committed; this would only happen if the
        # patient were deleted in the instant between commit and this read.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return AdminPatientListItemOut(**item)
