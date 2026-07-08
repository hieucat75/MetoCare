"""Centralized RBAC guards (T5 / C4).

Thin helpers that raise HTTPException(403) when an actor violates scope.

Rules:
  - INTERNAL_ADMIN / SUPER_ADMIN bypass all scope checks (read + write).
  - MEDICAL_REVIEWER: read-only — bypass read checks, blocked on writes elsewhere.
  - DOCTOR: must have an active DoctorClinic relation to the patient's clinic,
    or be the directly assigned doctor on the record.
  - CLINIC_ADMIN: must be associated with the target clinic.
  - PATIENT: own records only.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care import Clinic, Doctor, DoctorClinic
from app.models.clinic import (
    ClinicMembership,
    ClinicMembershipStatus,
    ClinicPatientRelationship,
    ClinicPatientRelationshipStatus,
    ClinicRole,
)
from app.models.user import UserRole

# Roles that may bypass scope checks for read access
_ADMIN_ROLES = frozenset(
    {
        UserRole.INTERNAL_ADMIN,
        UserRole.SUPER_ADMIN,
        UserRole.MEDICAL_REVIEWER,
    }
)

# Roles that may bypass scope checks for both read and write
_WRITE_ADMIN_ROLES = frozenset(
    {
        UserRole.INTERNAL_ADMIN,
        UserRole.SUPER_ADMIN,
    }
)


def _is_admin(role: str) -> bool:
    return role in _ADMIN_ROLES


def _is_write_admin(role: str) -> bool:
    return role in _WRITE_ADMIN_ROLES


def assert_patient_owns(current_user_id: str, patient_id: str, *, role: str) -> None:
    """Raise 403 unless the caller is the patient (or an admin).

    Used for read operations — admins and reviewers pass through.
    """
    if _is_admin(role):
        return
    if current_user_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this patient's records.",
        )


def assert_doctor_assigned(
    db: Session,
    current_user_id: str,
    patient_clinic_id: str | None,
    *,
    role: str,
    assigned_doctor_user_id: str | None = None,
) -> None:
    """Raise 403 unless doctor is assigned to the patient's clinic or is the direct doctor.

    - Admins/reviewers bypass.
    - Doctor must have an active DoctorClinic row for patient_clinic_id,
      OR be the directly assigned doctor (assigned_doctor_user_id == current_user_id).
    """
    if _is_admin(role):
        return
    if role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors or admins may perform this action.",
        )
    # Direct assignment check
    if assigned_doctor_user_id is not None and assigned_doctor_user_id == current_user_id:
        return
    # Clinic-scope check
    if patient_clinic_id is not None:
        doctor_row = db.execute(
            select(Doctor).where(Doctor.user_id == current_user_id)
        ).scalar_one_or_none()
        if doctor_row is not None:
            link = db.execute(
                select(DoctorClinic).where(
                    DoctorClinic.doctor_id == doctor_row.id,
                    DoctorClinic.clinic_id == patient_clinic_id,
                    DoctorClinic.is_active.is_(True),
                )
            ).scalar_one_or_none()
            if link is not None:
                return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Doctor is not assigned to this patient's clinic.",
    )


def assert_clinic_membership(
    db: Session,
    current_user_id: str,
    clinic_id: str,
    *,
    role: str,
    required_roles: Iterable[str] | None = None,
) -> ClinicMembership | None:
    """Raise 403 unless the caller has an ACTIVE `ClinicMembership` at `clinic_id`.

    Replaces the old `assert_clinic_scope` stub (`rbac.py`, historically
    "we accept any clinic_admin role" — TENANT_ARCHITECTURE.md §1), which
    authorized *any* CLINIC_ADMIN platform-role user for *any* clinic id. The
    real check is a membership-table lookup, generalizing
    `assert_doctor_assigned`'s pattern (§above) to all 7 clinic roles via
    `ClinicMembership` (TENANT_ARCHITECTURE.md §4).

    Platform admins (INTERNAL_ADMIN/SUPER_ADMIN) bypass — their cross-tenant
    access is the separate, always-audited `require_platform_override` path
    (`app/core/tenant_context.py`), never a silent bypass here.

    If `required_roles` is given, the membership must additionally hold at
    least one of those clinic roles (RBAC_MATRIX.md §2 rule 2 — every
    permission check resolves against the roles held at *this* clinic only).

    Returns the membership row (None only for a bypassing platform admin) so
    callers can read `branch_ids`/`roles` without a second query.
    """
    if _is_admin(role):
        return None
    membership = db.execute(
        select(ClinicMembership).where(
            ClinicMembership.user_id == current_user_id,
            ClinicMembership.clinic_id == clinic_id,
            ClinicMembership.status == ClinicMembershipStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền truy cập vào phòng khám này.",
        )
    if required_roles is not None:
        allowed = set(required_roles)
        if not allowed & set(membership.roles or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vai trò của bạn không đủ quyền cho thao tác này.",
            )
    return membership


def assert_clinic_writable(clinic: Clinic) -> None:
    """Raise 403 if the clinic's lifecycle status blocks writes (BR-M01-02/03).

    `suspended`/`expired` block writes only (reads are allowed elsewhere in
    the route/service, this guard is called only from write paths).
    `deactivated` blocks everything except the platform-override restore
    path (that path must not call this guard).
    """
    if clinic.status == "deactivated":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phòng khám đã ngừng hoạt động và không thể thao tác.",
        )
    if clinic.status in ("suspended", "expired"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phòng khám đang tạm ngừng hoặc đã hết hạn — không thể thực hiện thao tác này.",
        )


def require_clinic_roles(current_roles: Iterable[str], *allowed: str) -> None:
    """Raise 403 unless `current_roles` (a resolved `TenantContext.roles`,
    `app/api/deps_tenant.py`) intersects `allowed`. Route-level companion to
    `assert_clinic_membership` for the common case where `TenantContext` has
    already resolved membership + roles once per request, and the route only
    needs to check role sufficiency for the specific action.
    """
    if not set(current_roles) & set(allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vai trò của bạn không đủ quyền cho thao tác này.",
        )


def assert_path_clinic_matches_tenant(tenant_clinic_id: str, path_clinic_id: str) -> None:
    """Raise 403 if a route's path `clinic_id` does not equal the
    server-resolved `TenantContext.clinic_id`.

    This is the concrete, resource-level enforcement of
    TENANT_ARCHITECTURE.md §4's closing rule: a client-supplied `clinic_id`
    (here, the URL path) is never trusted as authorization truth by itself —
    it must match the clinic already selected/validated via the caller's own
    active membership. A mismatch is a 403 (not a silent filter), never a 404
    (to avoid leaking which clinic ids are also invalid vs. simply
    not-yours).
    """
    if tenant_clinic_id != path_clinic_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền truy cập vào phòng khám này.",
        )


def assert_doctor_clinic_scope_for_patient(
    db: Session, *, doctor_user_id: str, patient_id: str
) -> None:
    """Raise 403 unless the patient is not yet clinic-scoped, or the calling
    doctor holds an active `ClinicMembership` with the `doctor` role at a
    clinic the patient has an active `ClinicPatientRelationship` with.

    Closes the confirmed cross-clinic Clinical Copilot gap
    (`docs/clinic-saas/THREAT_MODEL.md` §10): the pre-existing
    `doctor_portal._require_timeline_access` -> `patients._check_read_access`
    chain is consent-only and has no notion of clinic membership, so any
    doctor with an active consent record could read/analyze a patient
    regardless of which clinic (if any) actually treats them. This check is
    ADDITIVE to that consent gate, never a replacement for it — callers must
    keep calling `_require_timeline_access` (or the equivalent consent check)
    first.

    Deliberately a no-op for patients with zero `ClinicPatientRelationship`
    rows (every patient today, since Phase C0 does not yet create these rows)
    so this does not change any current production behavior; it activates
    automatically once a clinic actually links a patient (C1+). Does not
    apply to the consultation-scoped branch of Clinical Copilot access
    (`assert_doctor_can_view`) — marketplace consultations are deliberately
    clinic-agnostic by design (`REUSE_AND_GAP_MATRIX.md`).
    """
    patient_clinic_ids = set(
        db.execute(
            select(ClinicPatientRelationship.clinic_id).where(
                ClinicPatientRelationship.patient_id == patient_id,
                ClinicPatientRelationship.status == ClinicPatientRelationshipStatus.ACTIVE,
            )
        ).scalars()
    )
    if not patient_clinic_ids:
        return

    memberships = db.execute(
        select(ClinicMembership).where(
            ClinicMembership.user_id == doctor_user_id,
            ClinicMembership.status == ClinicMembershipStatus.ACTIVE,
        )
    ).scalars()
    doctor_clinic_ids = {m.clinic_id for m in memberships if ClinicRole.DOCTOR in (m.roles or [])}

    if not (patient_clinic_ids & doctor_clinic_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không thuộc phòng khám đang quản lý hồ sơ bệnh nhân này.",
        )
