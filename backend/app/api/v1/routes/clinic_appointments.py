"""Clinic appointment management routes (Clinic SaaS C1 M07).

RBAC per RBAC_MATRIX.md's "Appointments (M07)" row + this milestone's
explicit row-level rule: all 6 non-Accountant clinic roles read the full
roster, but a caller whose *only* clinic role is `doctor` is scoped to their
own-assigned appointments (read AND write) — Owner/Admin/Reception/Nurse/
Care Coordinator are never row-scoped. Working-hours override is Owner/Admin
only (`is_override_allowed`), never re-derived by the service layer — the
route computes it from the resolved `TenantContext.roles` and passes a plain
boolean down, matching how every other Clinic SaaS service takes
pre-validated booleans/ids from routes rather than re-deriving RBAC itself.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.deps_clinic_saas import require_clinic_saas_enabled
from app.api.deps_tenant import TenantContext, get_tenant_context
from app.core.rbac import (
    assert_clinic_writable,
    assert_path_clinic_matches_tenant,
    require_clinic_roles,
)
from app.models.clinic import (
    ClinicAppointment,
    ClinicAppointmentSource,
    ClinicMembership,
    ClinicRole,
)
from app.schemas.clinic_appointment import (
    ClinicAppointmentArrivedOverrideRequest,
    ClinicAppointmentCancelRequest,
    ClinicAppointmentCreateRequest,
    ClinicAppointmentListOut,
    ClinicAppointmentNoShowRequest,
    ClinicAppointmentOut,
    ClinicAppointmentRescheduleRequest,
)
from app.services import clinic as clinic_service_lookup
from app.services import clinic_appointments as appointments_service
from app.services.clinic_appointments import (
    ClinicAppointmentConflictError,
    ClinicAppointmentError,
)

router = APIRouter(
    prefix="/clinics/{clinic_id}/appointments",
    tags=["clinic_appointments"],
    dependencies=[Depends(require_clinic_saas_enabled)],
)

_CLINIC_NOT_FOUND_DETAIL = "Không tìm thấy phòng khám."
_APPOINTMENT_NOT_FOUND_DETAIL = "Không tìm thấy lịch hẹn."
_FORBIDDEN_OWN_APPOINTMENT_DETAIL = (
    "Bạn chỉ có thể thao tác trên lịch hẹn được phân công cho mình."
)
_DOCTOR_SELF_BOOKING_ONLY_DETAIL = "Bác sĩ chỉ có thể tự đặt lịch cho chính mình."
_FORBIDDEN_BRANCH_DETAIL = "Bạn không có quyền truy cập chi nhánh này."

_READ_ROLES = (
    ClinicRole.OWNER,
    ClinicRole.ADMIN,
    ClinicRole.DOCTOR,
    ClinicRole.NURSE,
    ClinicRole.RECEPTIONIST,
    ClinicRole.CARE_COORDINATOR,
)
_CREATE_ROLES = (ClinicRole.OWNER, ClinicRole.ADMIN, ClinicRole.RECEPTIONIST, ClinicRole.DOCTOR)
_MUTATE_ROLES = (ClinicRole.OWNER, ClinicRole.ADMIN, ClinicRole.RECEPTIONIST, ClinicRole.DOCTOR)
_OWNER_ADMIN_ROLES = (ClinicRole.OWNER, ClinicRole.ADMIN)


def _is_doctor_only(roles: frozenset[str]) -> bool:
    return set(roles) == {ClinicRole.DOCTOR}


def _has_owner_admin_access(roles: frozenset[str]) -> bool:
    return bool(set(roles) & set(_OWNER_ADMIN_ROLES))


def _assert_actor_branch_scope(tenant: TenantContext, branch_id: str) -> None:
    """Raise 403 unless `branch_id` is within the caller's own membership
    scope. `tenant.branch_ids` empty means unrestricted (matches
    `clinic_services.list_services`'s established convention — Owner/Admin
    typically hold no branch restriction; Reception/Nurse/Care Coordinator/
    Doctor memberships may be scoped to specific branches, and per this
    milestone's explicit instruction a branch-scoped role must never act
    outside its own branch)."""
    if tenant.branch_ids and branch_id not in tenant.branch_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_BRANCH_DETAIL)


def _own_doctor_profile_id(db: Session, tenant: TenantContext) -> str | None:
    if tenant.membership_id is None:
        return None
    membership = db.get(ClinicMembership, tenant.membership_id)
    return membership.doctor_profile_id if membership is not None else None


def _created_by_source(tenant: TenantContext) -> str:
    return (
        ClinicAppointmentSource.DOCTOR
        if _is_doctor_only(tenant.roles)
        else ClinicAppointmentSource.RECEPTION
    )


def _load_clinic_or_404(db: Session, clinic_id: str):
    clinic = clinic_service_lookup.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    return clinic


def _assert_doctor_owns_appointment(
    db: Session, tenant: TenantContext, appointment: ClinicAppointment
) -> None:
    """A doctor-only caller may only read/write appointments assigned to
    them. 403 (not 404) — this is an authorization boundary within the same
    clinic, not existence-obscurity across clinics."""
    if not _is_doctor_only(tenant.roles):
        return
    own_doctor_id = _own_doctor_profile_id(db, tenant)
    if own_doctor_id is None or appointment.doctor_id != own_doctor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_OWN_APPOINTMENT_DETAIL
        )


def _load_appointment_for_mutation(
    db: Session, tenant: TenantContext, clinic_id: str, appointment_id: str
) -> ClinicAppointment:
    appointment = appointments_service.get_own_clinic_appointment(
        db, clinic_id=clinic_id, appointment_id=appointment_id
    )
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_APPOINTMENT_NOT_FOUND_DETAIL
        )
    _assert_doctor_owns_appointment(db, tenant, appointment)
    _assert_actor_branch_scope(tenant, appointment.branch_id)
    return appointment


@router.get("", response_model=ClinicAppointmentListOut)
def list_appointments(
    clinic_id: str,
    branch_id: str | None = Query(default=None),
    doctor_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: dt.datetime | None = Query(default=None),
    date_to: dt.datetime | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicAppointmentListOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_READ_ROLES)

    effective_doctor_id = doctor_id
    if _is_doctor_only(tenant.roles):
        own_doctor_id = _own_doctor_profile_id(db, tenant)
        if own_doctor_id is None:
            return ClinicAppointmentListOut(total=0, items=[])
        # Doctor-only callers are always scoped to their own assignments,
        # regardless of what the client requested via `doctor_id`.
        effective_doctor_id = own_doctor_id

    # Branch scoping ALWAYS derives from TenantContext.branch_ids, never
    # trusted purely from the client (same fix M05's list_services applied
    # after its own Codex review — clinic_services.py's docstring). An
    # explicit `branch_id` must be one of the caller's own membership
    # branches; when omitted, a branch-scoped membership defaults to exactly
    # that scope rather than silently falling through to "every branch."
    if branch_id is not None:
        _assert_actor_branch_scope(tenant, branch_id)
        effective_branch_ids = [branch_id]
    elif tenant.branch_ids:
        effective_branch_ids = list(tenant.branch_ids)
    else:
        effective_branch_ids = None

    items, total = appointments_service.list_appointments(
        db,
        clinic_id=clinic_id,
        branch_ids=effective_branch_ids,
        doctor_id=effective_doctor_id,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )
    return ClinicAppointmentListOut(
        total=total, items=[ClinicAppointmentOut.model_validate(a) for a in items]
    )


@router.post("", response_model=ClinicAppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    clinic_id: str,
    payload: ClinicAppointmentCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicAppointmentOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_CREATE_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    _assert_actor_branch_scope(tenant, payload.branch_id)

    if _is_doctor_only(tenant.roles):
        own_doctor_id = _own_doctor_profile_id(db, tenant)
        if own_doctor_id is None or payload.doctor_id != own_doctor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=_DOCTOR_SELF_BOOKING_ONLY_DETAIL
            )

    # Override reason only has effect for Owner/Admin (plan §3) — a non-
    # owner/admin caller's reason string is passed through but the service
    # is told `is_override_allowed=False`, so it still enforces the real
    # working-hours check and cannot be bypassed via a Receptionist/Doctor-
    # supplied reason.
    is_override_allowed = _has_owner_admin_access(tenant.roles)

    try:
        appointment = appointments_service.create_appointment(
            db,
            clinic_id=clinic_id,
            actor_id=tenant.user_id,
            branch_id=payload.branch_id,
            patient_id=payload.patient_id,
            doctor_id=payload.doctor_id,
            service_id=payload.service_id,
            start_time=payload.start_time,
            created_by_source=_created_by_source(tenant),
            notes=payload.notes,
            override_working_hours_reason=payload.override_working_hours_reason,
            is_override_allowed=is_override_allowed,
        )
    except ClinicAppointmentConflictError as exc:
        # Codex M08 R3 P1: a concurrent-transition stale loser is a conflict
        # (client should reload), not a validation failure.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClinicAppointmentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ClinicAppointmentOut.model_validate(appointment)


@router.get("/{appointment_id}", response_model=ClinicAppointmentOut)
def get_appointment(
    clinic_id: str,
    appointment_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicAppointmentOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_READ_ROLES)
    appointment = appointments_service.get_own_clinic_appointment(
        db, clinic_id=clinic_id, appointment_id=appointment_id
    )
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_APPOINTMENT_NOT_FOUND_DETAIL
        )
    _assert_doctor_owns_appointment(db, tenant, appointment)
    _assert_actor_branch_scope(tenant, appointment.branch_id)
    return ClinicAppointmentOut.model_validate(appointment)


@router.post("/{appointment_id}/confirm", response_model=ClinicAppointmentOut)
def confirm_appointment(
    clinic_id: str,
    appointment_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicAppointmentOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MUTATE_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    appointment = _load_appointment_for_mutation(db, tenant, clinic_id, appointment_id)
    try:
        appointment = appointments_service.confirm_appointment(
            db, appointment=appointment, actor_id=tenant.user_id
        )
    except ClinicAppointmentConflictError as exc:
        # Codex M08 R3 P1: a concurrent-transition stale loser is a conflict
        # (client should reload), not a validation failure.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClinicAppointmentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ClinicAppointmentOut.model_validate(appointment)


@router.post("/{appointment_id}/cancel", response_model=ClinicAppointmentOut)
def cancel_appointment(
    clinic_id: str,
    appointment_id: str,
    payload: ClinicAppointmentCancelRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicAppointmentOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MUTATE_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    appointment = _load_appointment_for_mutation(db, tenant, clinic_id, appointment_id)
    try:
        appointment = appointments_service.cancel_appointment(
            db, appointment=appointment, actor_id=tenant.user_id, reason=payload.reason
        )
    except ClinicAppointmentConflictError as exc:
        # Codex M08 R3 P1: a concurrent-transition stale loser is a conflict
        # (client should reload), not a validation failure.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClinicAppointmentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ClinicAppointmentOut.model_validate(appointment)


@router.post(
    "/{appointment_id}/reschedule",
    response_model=ClinicAppointmentOut,
    status_code=status.HTTP_201_CREATED,
)
def reschedule_appointment(
    clinic_id: str,
    appointment_id: str,
    payload: ClinicAppointmentRescheduleRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicAppointmentOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MUTATE_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    original = _load_appointment_for_mutation(db, tenant, clinic_id, appointment_id)
    if payload.branch_id is not None:
        _assert_actor_branch_scope(tenant, payload.branch_id)

    is_override_allowed = _has_owner_admin_access(tenant.roles)
    try:
        new_appointment = appointments_service.reschedule_appointment(
            db,
            clinic_id=clinic_id,
            actor_id=tenant.user_id,
            original=original,
            new_start_time=payload.start_time,
            reason=payload.reason,
            created_by_source=_created_by_source(tenant),
            new_branch_id=payload.branch_id,
            new_doctor_id=payload.doctor_id,
            is_override_allowed=is_override_allowed,
        )
    except ClinicAppointmentConflictError as exc:
        # Codex M08 R3 P1: a concurrent-transition stale loser is a conflict
        # (client should reload), not a validation failure.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClinicAppointmentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ClinicAppointmentOut.model_validate(new_appointment)


@router.post("/{appointment_id}/no-show", response_model=ClinicAppointmentOut)
def mark_no_show(
    clinic_id: str,
    appointment_id: str,
    payload: ClinicAppointmentNoShowRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicAppointmentOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MUTATE_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    appointment = _load_appointment_for_mutation(db, tenant, clinic_id, appointment_id)
    try:
        appointment = appointments_service.mark_no_show(
            db, appointment=appointment, actor_id=tenant.user_id, reason=payload.reason
        )
    except ClinicAppointmentConflictError as exc:
        # Codex M08 R3 P1: a concurrent-transition stale loser is a conflict
        # (client should reload), not a validation failure.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClinicAppointmentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ClinicAppointmentOut.model_validate(appointment)


@router.post("/{appointment_id}/arrived-override", response_model=ClinicAppointmentOut)
def mark_arrived_override(
    clinic_id: str,
    appointment_id: str,
    payload: ClinicAppointmentArrivedOverrideRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicAppointmentOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MUTATE_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    appointment = _load_appointment_for_mutation(db, tenant, clinic_id, appointment_id)
    try:
        appointment = appointments_service.mark_arrived_override(
            db, appointment=appointment, actor_id=tenant.user_id, reason=payload.reason
        )
    except ClinicAppointmentConflictError as exc:
        # Codex M08 R3 P1: a concurrent-transition stale loser is a conflict
        # (client should reload), not a validation failure.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClinicAppointmentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ClinicAppointmentOut.model_validate(appointment)


@router.post("/run-no-show-job")
def run_no_show_job(
    clinic_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> dict:
    """Owner/Admin-gated manual trigger for BR-M07-05's idempotent
    end-of-day job — no task-scheduler infra exists in this codebase to hook
    a real cron into yet (M07_IMPLEMENTATION_PLAN.md §5)."""
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_OWNER_ADMIN_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    count = appointments_service.run_no_show_job(db, clinic_id=clinic_id, actor_id=tenant.user_id)
    db.commit()
    return {"transitioned_count": count}
