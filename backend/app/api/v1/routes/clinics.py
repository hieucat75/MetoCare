"""Clinic CRUD + lifecycle routes (Clinic SaaS Phase C0, M01).

Thin routes — all logic in `app.services.clinic`. Every write is scoped by
the caller's server-resolved `TenantContext.clinic_id`
(`app/api/deps_tenant.py`), never a client-supplied path param alone
(TENANT_ARCHITECTURE.md §4). Gated end-to-end by the `CLINIC_SAAS` feature
flag (fail-closed default, `app/api/deps_clinic_saas.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.api.deps_clinic_saas import require_clinic_saas_enabled
from app.api.deps_tenant import (
    TenantContext,
    get_tenant_context,
    require_platform_admin,
    require_platform_override,
)
from app.core.rbac import (
    assert_clinic_writable,
    assert_path_clinic_matches_tenant,
    require_clinic_roles,
)
from app.models.clinic import ClinicRole
from app.schemas.clinic import ClinicCreate, ClinicListOut, ClinicOut, ClinicSettingsUpdate
from app.schemas.clinic_membership import (
    ClinicMembershipOut,
    MyClinicMembershipListOut,
    MyClinicMembershipOut,
)
from app.services import clinic as clinic_service
from app.services import clinic_membership as membership_service

router = APIRouter(
    prefix="/clinics", tags=["clinics"], dependencies=[Depends(require_clinic_saas_enabled)]
)

_CLINIC_NOT_FOUND_DETAIL = "Không tìm thấy phòng khám."
_MEMBERSHIP_NOT_FOUND_DETAIL = "Không tìm thấy thành viên."


@router.post("", response_model=ClinicOut, status_code=status.HTTP_201_CREATED)
def create_clinic(
    payload: ClinicCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> ClinicOut:
    """Self-serve clinic onboarding — the caller becomes the new clinic's Owner
    (created in `trial` status with a default trial subscription row)."""
    clinic = clinic_service.create_clinic(
        db,
        owner_user_id=user.id,
        name=payload.name,
        legal_name=payload.legal_name,
        tax_code=payload.tax_code,
        license_no=payload.license_no,
        clinic_type=payload.clinic_type,
        address=payload.address,
        phone=payload.phone,
        email=payload.email,
    )
    db.commit()
    return ClinicOut.model_validate(clinic)


@router.get("", response_model=ClinicListOut)
def list_clinics(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    _admin: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_session),
) -> ClinicListOut:
    """Platform-wide clinic listing — Super/Internal Admin only (audited
    ops-level access; genuinely multi-tenant, so it uses the ops-listing
    dependency rather than the single-clinic `require_platform_override`)."""
    items, total = clinic_service.list_clinics(
        db, skip=skip, limit=limit, status_filter=status_filter
    )
    return ClinicListOut(total=total, items=[ClinicOut.model_validate(c) for c in items])


@router.get("/me", response_model=ClinicOut)
def get_my_clinic(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicOut:
    """The caller's current active clinic — FE bootstrap/clinic-switcher call."""
    clinic = clinic_service.get_clinic(db, tenant.clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    return ClinicOut.model_validate(clinic)


@router.get("/me/membership", response_model=ClinicMembershipOut)
def get_my_membership(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicMembershipOut:
    """The caller's own membership row (roles/branch scope) at their current
    active clinic — pairs with `GET /clinics/me`. Without this, a frontend
    has no way to know which RBAC_MATRIX.md role(s) the caller holds and must
    guess menu/action visibility from probing 403s."""
    assert tenant.membership_id is not None  # guaranteed by get_tenant_context
    membership = membership_service.get_membership_by_id(db, membership_id=tenant.membership_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_MEMBERSHIP_NOT_FOUND_DETAIL
        )
    return ClinicMembershipOut.model_validate(membership)


@router.get("/memberships/mine", response_model=MyClinicMembershipListOut)
def list_my_memberships(
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> MyClinicMembershipListOut:
    """Every clinic the caller is an active member of — the clinic-switcher's
    data source. Deliberately depends on `current_user`, not
    `get_tenant_context`: a caller with 0 or 2+ active memberships must still
    be able to see their own choices (or the empty state) rather than being
    403/400'd before they can even list them."""
    memberships = membership_service.list_my_memberships(db, user_id=user.id)
    items: list[MyClinicMembershipOut] = []
    for membership in memberships:
        clinic = clinic_service.get_clinic(db, membership.clinic_id)
        if clinic is None:
            continue
        items.append(
            MyClinicMembershipOut(
                id=membership.id,
                clinic_id=membership.clinic_id,
                clinic_name=clinic.name,
                clinic_status=clinic.status,
                roles=membership.roles or [],
                branch_ids=membership.branch_ids or [],
                is_primary=membership.is_primary,
            )
        )
    return MyClinicMembershipListOut(items=items)


@router.get("/{clinic_id}", response_model=ClinicOut)
def get_clinic(
    clinic_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    clinic = clinic_service.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    return ClinicOut.model_validate(clinic)


@router.patch("/{clinic_id}", response_model=ClinicOut)
def update_clinic(
    clinic_id: str,
    payload: ClinicSettingsUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, ClinicRole.OWNER, ClinicRole.ADMIN)
    clinic = clinic_service.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    assert_clinic_writable(clinic)
    clinic = clinic_service.update_clinic_settings(
        db, clinic=clinic, actor_id=tenant.user_id, **payload.model_dump(exclude_unset=True)
    )
    db.commit()
    return ClinicOut.model_validate(clinic)


@router.post("/{clinic_id}/deactivate", response_model=ClinicOut)
def deactivate_clinic(
    clinic_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicOut:
    """Owner-initiated voluntary closure (terminal state — a status flip,
    never a hard delete)."""
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, ClinicRole.OWNER)
    clinic = clinic_service.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    clinic = clinic_service.deactivate_clinic(db, clinic=clinic, actor_id=tenant.user_id)
    db.commit()
    return ClinicOut.model_validate(clinic)


@router.post("/{clinic_id}/suspend", response_model=ClinicOut)
def suspend_clinic(
    clinic_id: str,
    tenant: TenantContext = Depends(require_platform_override),
    db: Session = Depends(get_session),
) -> ClinicOut:
    """Platform-only policy-violation suspension."""
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    clinic = clinic_service.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    clinic = clinic_service.suspend_clinic(db, clinic=clinic, actor_id=tenant.user_id)
    db.commit()
    return ClinicOut.model_validate(clinic)


@router.post("/{clinic_id}/restore", response_model=ClinicOut)
def restore_clinic(
    clinic_id: str,
    tenant: TenantContext = Depends(require_platform_override),
    db: Session = Depends(get_session),
) -> ClinicOut:
    """Platform-only restore from suspended/deactivated back to active."""
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    clinic = clinic_service.get_clinic(db, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_CLINIC_NOT_FOUND_DETAIL
        )
    clinic = clinic_service.restore_clinic(db, clinic=clinic, actor_id=tenant.user_id)
    db.commit()
    return ClinicOut.model_validate(clinic)
