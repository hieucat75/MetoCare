"""Clinic branch CRUD routes (Clinic SaaS Phase C0, M02)."""

from __future__ import annotations

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
from app.models.clinic import ClinicRole
from app.schemas.clinic import (
    ClinicBranchCreate,
    ClinicBranchListOut,
    ClinicBranchOut,
    ClinicBranchStatusUpdate,
    ClinicBranchUpdate,
)
from app.services import clinic as clinic_service
from app.services import clinic_branch as branch_service
from app.services.clinic_branch import ClinicBranchError

router = APIRouter(
    prefix="/clinics/{clinic_id}/branches",
    tags=["clinic_branches"],
    dependencies=[Depends(require_clinic_saas_enabled)],
)

_BRANCH_NOT_FOUND_DETAIL = "Không tìm thấy chi nhánh."
_CLINIC_NOT_FOUND_DETAIL = "Không tìm thấy phòng khám."


def _load_clinic_or_404(db: Session, clinic_id: str):
    clinic = clinic_service.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    return clinic


@router.post("", response_model=ClinicBranchOut, status_code=status.HTTP_201_CREATED)
def create_branch(
    clinic_id: str,
    payload: ClinicBranchCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicBranchOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, ClinicRole.OWNER, ClinicRole.ADMIN)
    assert_clinic_writable(_load_clinic_or_404(db, clinic_id))
    try:
        branch = branch_service.create_branch(
            db,
            clinic_id=clinic_id,
            actor_id=tenant.user_id,
            name=payload.name,
            working_hours=payload.working_hours,
            address=payload.address,
            phone=payload.phone,
        )
    except ClinicBranchError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return ClinicBranchOut.model_validate(branch)


_BRANCH_READ_ROLES = (
    ClinicRole.OWNER,
    ClinicRole.ADMIN,
    ClinicRole.DOCTOR,
    ClinicRole.NURSE,
    ClinicRole.RECEPTIONIST,
    ClinicRole.CARE_COORDINATOR,
)  # RBAC_MATRIX.md M02 row: Accountant is the one role marked ✗ (not R) here.


@router.get("", response_model=ClinicBranchListOut)
def list_branches(
    clinic_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicBranchListOut:
    """Read access per RBAC_MATRIX.md M02 row: Owner/Admin full, Doctor/Nurse/
    Reception/Care Coordinator read-only, Accountant forbidden."""
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_BRANCH_READ_ROLES)
    items, total = branch_service.list_branches(db, clinic_id=clinic_id, skip=skip, limit=limit)
    return ClinicBranchListOut(
        total=total, items=[ClinicBranchOut.model_validate(b) for b in items]
    )


@router.patch("/{branch_id}", response_model=ClinicBranchOut)
def update_branch(
    clinic_id: str,
    branch_id: str,
    payload: ClinicBranchUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicBranchOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, ClinicRole.OWNER, ClinicRole.ADMIN)
    assert_clinic_writable(_load_clinic_or_404(db, clinic_id))
    branch = branch_service.get_branch(db, clinic_id=clinic_id, branch_id=branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_BRANCH_NOT_FOUND_DETAIL
        )
    try:
        branch = branch_service.update_branch(
            db, branch=branch, actor_id=tenant.user_id, **payload.model_dump(exclude_unset=True)
        )
    except ClinicBranchError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return ClinicBranchOut.model_validate(branch)


@router.post("/{branch_id}/status", response_model=ClinicBranchOut)
def set_branch_status(
    clinic_id: str,
    branch_id: str,
    payload: ClinicBranchStatusUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicBranchOut:
    """Pause/archive a branch — no hard delete ever (DATA_MODEL.md §2)."""
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, ClinicRole.OWNER, ClinicRole.ADMIN)
    assert_clinic_writable(_load_clinic_or_404(db, clinic_id))
    branch = branch_service.get_branch(db, clinic_id=clinic_id, branch_id=branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_BRANCH_NOT_FOUND_DETAIL
        )
    branch = branch_service.set_branch_status(
        db, branch=branch, actor_id=tenant.user_id, status_value=payload.status
    )
    db.commit()
    return ClinicBranchOut.model_validate(branch)
