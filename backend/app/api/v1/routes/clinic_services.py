"""Clinic service/pricing catalog routes (Clinic SaaS Phase C0, M05)."""

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
from app.schemas.clinic_service import (
    ClinicServiceCreate,
    ClinicServiceListOut,
    ClinicServiceOut,
    ClinicServiceUpdate,
)
from app.services import clinic as clinic_service_lookup
from app.services import clinic_branch as branch_lookup
from app.services import clinic_service_catalog as catalog_service
from app.services.clinic_branch import ClinicBranchError
from app.services.clinic_service_catalog import ClinicServiceError

router = APIRouter(
    prefix="/clinics/{clinic_id}/services",
    tags=["clinic_services"],
    dependencies=[Depends(require_clinic_saas_enabled)],
)

_SERVICE_NOT_FOUND_DETAIL = "Không tìm thấy dịch vụ."
_CLINIC_NOT_FOUND_DETAIL = "Không tìm thấy phòng khám."
_BRANCH_NOT_FOUND_DETAIL = "Không tìm thấy chi nhánh."
_MANAGE_ROLES = (ClinicRole.OWNER, ClinicRole.ADMIN)


@router.post("", response_model=ClinicServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(
    clinic_id: str,
    payload: ClinicServiceCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicServiceOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    clinic = clinic_service_lookup.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    assert_clinic_writable(clinic)
    try:
        service = catalog_service.create_service(
            db,
            clinic_id=clinic_id,
            actor_id=tenant.user_id,
            name=payload.name,
            code=payload.code,
            specialty=payload.specialty,
            duration_minutes=payload.duration_minutes,
            price=payload.price,
            type=payload.type,
            branch_ids=payload.branch_ids,
            doctor_ids=payload.doctor_ids,
            package_visit_count=payload.package_visit_count,
            duration_months=payload.duration_months,
            included_items=payload.included_items,
            benefits=payload.benefits,
            cancellation_refund_policy=payload.cancellation_refund_policy,
        )
    except (ClinicBranchError, ClinicServiceError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ClinicServiceOut.model_validate(service)


@router.get("", response_model=ClinicServiceListOut)
def list_services(
    clinic_id: str,
    branch_id: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicServiceListOut:
    """Read access: every clinic role per RBAC_MATRIX.md M05 row (Owner/Admin
    full, everyone else R). `branch_id` (AC-M05-03) narrows to one branch for
    a branch-switcher UX.

    Codex PR review fix (P1): visibility is now ALWAYS derived from
    `TenantContext.branch_ids`, never trusted purely from the client — an
    explicit `branch_id` must be one of the caller's own membership branches
    (else 403); when omitted, a branch-scoped membership (non-empty
    `tenant.branch_ids`) defaults to exactly that scope rather than falling
    through to "every branch." A membership with no branch restriction
    (`tenant.branch_ids` empty, e.g. Owner/Admin) still sees everything,
    same as before.

    Codex second-pass review P2: an unrestricted (Owner/Admin) caller's
    explicit `branch_id` was never checked against `clinic_id` at all — a
    garbage/foreign id silently filtered to a misleading empty result
    instead of 404. Now validated via `get_branch` regardless of whether the
    caller's own membership is branch-scoped."""
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    if branch_id is not None and tenant.branch_ids and branch_id not in tenant.branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền xem chi nhánh này."
        )
    if branch_id is not None and not tenant.branch_ids:
        if branch_lookup.get_branch(db, clinic_id=clinic_id, branch_id=branch_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_BRANCH_NOT_FOUND_DETAIL
            )
    effective_branch_ids: list[str] | None
    if branch_id is not None:
        effective_branch_ids = [branch_id]
    elif tenant.branch_ids:
        effective_branch_ids = list(tenant.branch_ids)
    else:
        effective_branch_ids = None
    items, total = catalog_service.list_services(
        db, clinic_id=clinic_id, branch_ids=effective_branch_ids, skip=skip, limit=limit
    )
    return ClinicServiceListOut(
        total=total, items=[ClinicServiceOut.model_validate(s) for s in items]
    )


@router.patch("/{service_id}", response_model=ClinicServiceOut)
def update_service(
    clinic_id: str,
    service_id: str,
    payload: ClinicServiceUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicServiceOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    clinic = clinic_service_lookup.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    assert_clinic_writable(clinic)
    service = catalog_service.get_service(db, clinic_id=clinic_id, service_id=service_id)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_SERVICE_NOT_FOUND_DETAIL
        )
    try:
        service = catalog_service.update_service(
            db, service=service, actor_id=tenant.user_id, **payload.model_dump(exclude_unset=True)
        )
    except (ClinicBranchError, ClinicServiceError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ClinicServiceOut.model_validate(service)
