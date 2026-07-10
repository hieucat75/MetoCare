"""Clinic check-in & queue routes (Clinic SaaS C1 M08).

RBAC per RBAC_MATRIX.md's M08 row (Owner/Admin/Nurse/Reception manage,
Doctor own-scoped, CC read-only, Accountant none):
- `_READ_ROLES` may list/display; a doctor-only caller is row-scoped to
  entries with their own `doctor_profile_id` (hardened from M07's `_is_doctor_only`
  pattern).
- `_MANAGE_ROLES` (Owner/Admin/Reception/Nurse) may check-in/walk-in/leave/
  priority.
- `_ACT_ROLES` (= manage + doctor) may call/missed-call/start/complete —
  doctor-only callers on their OWN entries only, and blocked from calling
  an over-missed-call-cap entry (BR-M08-04: reception handles those).

Two routers because the check-in action lives on the appointment resource
(`POST /clinics/{cid}/appointments/{aid}/check-in`, plan §4) while
everything else lives under `/clinics/{cid}/queue`.

Error mapping: race/conflict losers (duplicate check-in, duplicate active
entry, conditional-UPDATE loser) -> 409; domain validation -> 400;
cross-clinic -> 404; scope/role -> 403. `db.commit()` only in routes.
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
from app.models.clinic import ClinicAppointment, ClinicMembership, ClinicQueueEntry, ClinicRole
from app.schemas.clinic_queue import (
    ClinicQueueDisplayEntryOut,
    ClinicQueueDisplayOut,
    ClinicQueueEntryOut,
    ClinicQueueListOut,
    ClinicQueuePriorityRequest,
    ClinicQueueWalkInRequest,
)
from app.services import clinic as clinic_service_lookup
from app.services import clinic_appointments as appointments_service
from app.services import clinic_queue as queue_service
from app.services.clinic_appointments import (
    ClinicAppointmentConflictError,
    ClinicAppointmentError,
)
from app.services.clinic_queue import ClinicQueueConflictError, ClinicQueueError

router = APIRouter(
    prefix="/clinics/{clinic_id}/queue",
    tags=["clinic_queue"],
    dependencies=[Depends(require_clinic_saas_enabled)],
)
# Check-in is an action on the appointment resource (plan §4).
checkin_router = APIRouter(
    prefix="/clinics/{clinic_id}/appointments",
    tags=["clinic_queue"],
    dependencies=[Depends(require_clinic_saas_enabled)],
)

_CLINIC_NOT_FOUND_DETAIL = "Không tìm thấy phòng khám."
_APPOINTMENT_NOT_FOUND_DETAIL = "Không tìm thấy lịch hẹn."
_ENTRY_NOT_FOUND_DETAIL = "Không tìm thấy lượt chờ."
_FORBIDDEN_OWN_ENTRY_DETAIL = "Bạn chỉ có thể thao tác trên lượt chờ được phân công cho mình."
_FORBIDDEN_BRANCH_DETAIL = "Bạn không có quyền truy cập chi nhánh này."
_FORBIDDEN_OVER_CAP_DETAIL = (
    "Lượt chờ đã vượt số lần gọi nhỡ tối đa — cần lễ tân xử lý (gọi lại hoặc hủy lượt)."
)

_READ_ROLES = (
    ClinicRole.OWNER,
    ClinicRole.ADMIN,
    ClinicRole.DOCTOR,
    ClinicRole.NURSE,
    ClinicRole.RECEPTIONIST,
    ClinicRole.CARE_COORDINATOR,
)
_MANAGE_ROLES = (
    ClinicRole.OWNER,
    ClinicRole.ADMIN,
    ClinicRole.RECEPTIONIST,
    ClinicRole.NURSE,
)
_ACT_ROLES = (*_MANAGE_ROLES, ClinicRole.DOCTOR)


def _is_doctor_scoped(roles: frozenset[str]) -> bool:
    """Own-entry scoping applies to any caller who can act ONLY by virtue of
    their doctor role — i.e. holds `doctor` and no manage role. Codex M08 R1
    P1: the previous exact-set test (`roles == {doctor}`) let a
    doctor+care_coordinator membership skip own-entry enforcement entirely,
    since CC isn't a manage role but the set-equality check no longer
    matched."""
    return ClinicRole.DOCTOR in roles and not (set(roles) & set(_MANAGE_ROLES))


def _assert_actor_branch_scope(tenant: TenantContext, branch_id: str) -> None:
    """Empty `tenant.branch_ids` means unrestricted (M05/M07 convention);
    a branch-scoped membership must never act outside its own branches."""
    if tenant.branch_ids and branch_id not in tenant.branch_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_BRANCH_DETAIL)


def _own_doctor_profile_id(db: Session, tenant: TenantContext) -> str | None:
    if tenant.membership_id is None:
        return None
    membership = db.get(ClinicMembership, tenant.membership_id)
    return membership.doctor_profile_id if membership is not None else None


def _load_clinic_or_404(db: Session, clinic_id: str):
    clinic = clinic_service_lookup.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    return clinic


def _assert_doctor_owns_entry(
    db: Session, tenant: TenantContext, entry: ClinicQueueEntry
) -> None:
    """403 (not 404) — an authorization boundary within the same clinic, not
    existence-obscurity across clinics (M07 precedent)."""
    if not _is_doctor_scoped(tenant.roles):
        return
    own_doctor_id = _own_doctor_profile_id(db, tenant)
    if own_doctor_id is None or entry.doctor_id != own_doctor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_OWN_ENTRY_DETAIL
        )


def _load_entry_for_action(
    db: Session, tenant: TenantContext, clinic_id: str, entry_id: str
) -> ClinicQueueEntry:
    entry = queue_service.get_own_queue_entry(db, clinic_id=clinic_id, entry_id=entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ENTRY_NOT_FOUND_DETAIL)
    _assert_doctor_owns_entry(db, tenant, entry)
    _assert_actor_branch_scope(tenant, entry.branch_id)
    return entry


def _effective_branch_ids(tenant: TenantContext, branch_id: str | None) -> list[str] | None:
    """Branch scoping ALWAYS derives from `TenantContext.branch_ids` (M05/M07
    pattern): an explicit branch_id must be within the caller's own scope;
    when omitted, a branch-scoped membership defaults to exactly its scope."""
    if branch_id is not None:
        _assert_actor_branch_scope(tenant, branch_id)
        return [branch_id]
    if tenant.branch_ids:
        return list(tenant.branch_ids)
    return None


def _entry_out(db: Session, clinic, entry: ClinicQueueEntry) -> ClinicQueueEntryOut:
    return ClinicQueueEntryOut.model_validate(
        queue_service.get_entry_out(db, clinic=clinic, entry=entry)
    )


# ---------------------------------------------------------------------------
# Check-in (appointment resource) + walk-in
# ---------------------------------------------------------------------------


@checkin_router.post(
    "/{appointment_id}/check-in",
    response_model=ClinicQueueEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def check_in_appointment(
    clinic_id: str,
    appointment_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicQueueEntryOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    appointment = appointments_service.get_own_clinic_appointment(
        db, clinic_id=clinic_id, appointment_id=appointment_id
    )
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_APPOINTMENT_NOT_FOUND_DETAIL
        )
    _assert_actor_branch_scope(tenant, appointment.branch_id)
    try:
        entry = queue_service.check_in_appointment(
            db, clinic=clinic, appointment=appointment, actor_id=tenant.user_id
        )
    except (ClinicQueueConflictError, ClinicAppointmentConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ClinicQueueError, ClinicAppointmentError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _entry_out(db, clinic, entry)


@router.post("/walk-in", response_model=ClinicQueueEntryOut, status_code=status.HTTP_201_CREATED)
def walk_in_check_in(
    clinic_id: str,
    payload: ClinicQueueWalkInRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicQueueEntryOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    _assert_actor_branch_scope(tenant, payload.branch_id)
    try:
        entry = queue_service.walk_in_check_in(
            db,
            clinic=clinic,
            actor_id=tenant.user_id,
            branch_id=payload.branch_id,
            patient_id=payload.patient_id,
            service_id=payload.service_id,
            doctor_id=payload.doctor_id,
            notes=payload.notes,
        )
    except (ClinicQueueConflictError, ClinicAppointmentConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ClinicQueueError, ClinicAppointmentError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _entry_out(db, clinic, entry)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@router.get("", response_model=ClinicQueueListOut)
def list_queue(
    clinic_id: str,
    branch_id: str | None = Query(default=None),
    doctor_id: str | None = Query(default=None),
    service_date: dt.date | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicQueueListOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_READ_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)

    effective_doctor_id = doctor_id
    if _is_doctor_scoped(tenant.roles):
        own_doctor_id = _own_doctor_profile_id(db, tenant)
        if own_doctor_id is None:
            return ClinicQueueListOut(total=0, items=[])
        # Doctor-only callers are always scoped to their own entries,
        # regardless of the client-requested `doctor_id`.
        effective_doctor_id = own_doctor_id

    items, total = queue_service.list_queue(
        db,
        clinic=clinic,
        branch_ids=_effective_branch_ids(tenant, branch_id),
        doctor_id=effective_doctor_id,
        service_date=service_date,
        status=status_filter,
    )
    return ClinicQueueListOut(
        total=total, items=[ClinicQueueEntryOut.model_validate(item) for item in items]
    )


@router.get("/display", response_model=ClinicQueueDisplayOut)
def display_queue(
    clinic_id: str,
    branch_id: str | None = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicQueueDisplayOut:
    """Public-screen payload — deliberately still an AUTHENTICATED endpoint
    (the physical screen runs an authenticated session, plan §4): masked
    initials + number + status + doctor only, no PHI (AC-M08-03).

    Codex M08 R2 P1: a doctor-scoped caller gets the same own-entry filter
    as the staff list — without it this route was the one read that ignored
    the RBAC matrix's "Doctor ✓ (own)" row. The physical screen runs under a
    reception/admin session, which is unrestricted here."""
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_READ_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)

    effective_doctor_id = None
    if _is_doctor_scoped(tenant.roles):
        own_doctor_id = _own_doctor_profile_id(db, tenant)
        if own_doctor_id is None:
            return ClinicQueueDisplayOut(items=[])
        effective_doctor_id = own_doctor_id

    items = queue_service.display_queue(
        db,
        clinic=clinic,
        branch_ids=_effective_branch_ids(tenant, branch_id),
        doctor_id=effective_doctor_id,
    )
    return ClinicQueueDisplayOut(
        items=[ClinicQueueDisplayEntryOut.model_validate(item) for item in items]
    )


# ---------------------------------------------------------------------------
# Entry transitions
# ---------------------------------------------------------------------------


@router.post("/{entry_id}/call", response_model=ClinicQueueEntryOut)
def call_entry(
    clinic_id: str,
    entry_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicQueueEntryOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_ACT_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    entry = _load_entry_for_action(db, tenant, clinic_id, entry_id)
    # BR-M08-04: past the missed-call cap, only reception-side roles may
    # keep calling (or remove) — the doctor is blocked until resolved.
    # Codex M08 R4 P1: the block itself is audited (durable PHI-free trail
    # for a prohibited attempt), same denial discipline as the service layer.
    if _is_doctor_scoped(tenant.roles):
        config = queue_service.get_queue_config(clinic)
        if entry.missed_call_count >= config["max_missed_calls"]:
            queue_service.record_entry_denial(
                db,
                entry=entry,
                actor_id=tenant.user_id,
                action="clinic_queue_transition_denied",
                details={
                    "from": entry.status,
                    "to": "called",
                    "reason": "over_missed_call_cap_doctor",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_OVER_CAP_DETAIL
            )
    try:
        entry = queue_service.call_entry(db, entry=entry, actor_id=tenant.user_id)
    except ClinicQueueConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClinicQueueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _entry_out(db, clinic, entry)


@router.post("/{entry_id}/missed-call", response_model=ClinicQueueEntryOut)
def mark_missed_call(
    clinic_id: str,
    entry_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicQueueEntryOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_ACT_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    entry = _load_entry_for_action(db, tenant, clinic_id, entry_id)
    try:
        config = queue_service.get_queue_config(clinic)
        entry = queue_service.mark_missed_call(
            db,
            entry=entry,
            actor_id=tenant.user_id,
            max_missed_calls=config["max_missed_calls"],
        )
    except ClinicQueueConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClinicQueueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _entry_out(db, clinic, entry)


@router.post("/{entry_id}/start-consultation", response_model=ClinicQueueEntryOut)
def start_consultation(
    clinic_id: str,
    entry_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicQueueEntryOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_ACT_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    entry = _load_entry_for_action(db, tenant, clinic_id, entry_id)
    appointment = db.get(ClinicAppointment, entry.appointment_id)
    try:
        entry = queue_service.start_consultation(
            db, entry=entry, appointment=appointment, actor_id=tenant.user_id
        )
    except (ClinicQueueConflictError, ClinicAppointmentConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ClinicQueueError, ClinicAppointmentError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _entry_out(db, clinic, entry)


@router.post("/{entry_id}/complete", response_model=ClinicQueueEntryOut)
def complete_entry(
    clinic_id: str,
    entry_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicQueueEntryOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_ACT_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    entry = _load_entry_for_action(db, tenant, clinic_id, entry_id)
    appointment = db.get(ClinicAppointment, entry.appointment_id)
    try:
        entry = queue_service.complete_entry(
            db, entry=entry, appointment=appointment, actor_id=tenant.user_id
        )
    except (ClinicQueueConflictError, ClinicAppointmentConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ClinicQueueError, ClinicAppointmentError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _entry_out(db, clinic, entry)


@router.post("/{entry_id}/leave", response_model=ClinicQueueEntryOut)
def leave_entry(
    clinic_id: str,
    entry_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicQueueEntryOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    entry = _load_entry_for_action(db, tenant, clinic_id, entry_id)
    try:
        entry = queue_service.leave_entry(db, entry=entry, actor_id=tenant.user_id)
    except ClinicQueueConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClinicQueueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _entry_out(db, clinic, entry)


@router.post("/{entry_id}/priority", response_model=ClinicQueueEntryOut)
def set_priority(
    clinic_id: str,
    entry_id: str,
    payload: ClinicQueuePriorityRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicQueueEntryOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    clinic = _load_clinic_or_404(db, clinic_id)
    assert_clinic_writable(clinic)
    entry = _load_entry_for_action(db, tenant, clinic_id, entry_id)
    try:
        entry = queue_service.set_priority(
            db,
            entry=entry,
            actor_id=tenant.user_id,
            is_priority=payload.is_priority,
            reason=payload.reason,
        )
    except ClinicQueueConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ClinicQueueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _entry_out(db, clinic, entry)
