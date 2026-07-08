"""Clinic membership + invitation lifecycle routes (Clinic SaaS Phase C0, M03).

Two routers: one scoped under `/clinics/{clinic_id}/...` (Owner/Admin manage
their own staff), and a standalone `/clinic-invitations/accept` for the
invitee (who has no membership yet, so cannot go through `TenantContext`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.api.deps_clinic_saas import require_clinic_saas_enabled
from app.api.deps_tenant import TenantContext, get_tenant_context
from app.core.rbac import assert_path_clinic_matches_tenant, require_clinic_roles
from app.models.clinic import ClinicRole
from app.schemas.clinic_membership import (
    ClinicInvitationAcceptRequest,
    ClinicInvitationCreate,
    ClinicInvitationCreateOut,
    ClinicInvitationListOut,
    ClinicInvitationOut,
    ClinicMembershipListOut,
    ClinicMembershipOut,
    ClinicMembershipUpdate,
)
from app.services import clinic_membership as membership_service
from app.services.clinic_membership import ClinicMembershipError

router = APIRouter(
    prefix="/clinics/{clinic_id}",
    tags=["clinic_members"],
    dependencies=[Depends(require_clinic_saas_enabled)],
)

# Not clinic-scoped — the invitee has no membership yet to resolve a
# TenantContext from; auth is the invitation token itself.
accept_router = APIRouter(
    prefix="/clinic-invitations",
    tags=["clinic_members"],
    dependencies=[Depends(require_clinic_saas_enabled)],
)

_INVITATION_NOT_FOUND_DETAIL = "Không tìm thấy lời mời."
_MEMBERSHIP_NOT_FOUND_DETAIL = "Không tìm thấy thành viên."
_MANAGE_ROLES = (ClinicRole.OWNER, ClinicRole.ADMIN)


@router.post(
    "/invitations", response_model=ClinicInvitationCreateOut, status_code=status.HTTP_201_CREATED
)
def create_invitation(
    clinic_id: str,
    payload: ClinicInvitationCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicInvitationCreateOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    try:
        invitation, raw_token = membership_service.create_invitation(
            db,
            clinic_id=clinic_id,
            actor_id=tenant.user_id,
            roles=payload.roles,
            branch_ids=payload.branch_ids,
            invited_email=payload.invited_email,
            invited_phone=payload.invited_phone,
        )
    except ClinicMembershipError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return ClinicInvitationCreateOut(
        **ClinicInvitationOut.model_validate(invitation).model_dump(), raw_token=raw_token
    )


@router.get("/invitations", response_model=ClinicInvitationListOut)
def list_invitations(
    clinic_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicInvitationListOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    items, total = membership_service.list_invitations(
        db, clinic_id=clinic_id, skip=skip, limit=limit
    )
    return ClinicInvitationListOut(
        total=total, items=[ClinicInvitationOut.model_validate(i) for i in items]
    )


@router.post("/invitations/{invitation_id}/revoke", response_model=ClinicInvitationOut)
def revoke_invitation(
    clinic_id: str,
    invitation_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicInvitationOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    try:
        invitation = membership_service.revoke_invitation(
            db, clinic_id=clinic_id, invitation_id=invitation_id, actor_id=tenant.user_id
        )
    except ClinicMembershipError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return ClinicInvitationOut.model_validate(invitation)


@accept_router.post("/accept", response_model=ClinicMembershipOut)
def accept_invitation(
    payload: ClinicInvitationAcceptRequest,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> ClinicMembershipOut:
    try:
        membership = membership_service.accept_invitation(
            db, raw_token=payload.token, accepting_user_id=user.id
        )
    except ClinicMembershipError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    db.commit()
    return ClinicMembershipOut.model_validate(membership)


@router.get("/members", response_model=ClinicMembershipListOut)
def list_members(
    clinic_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicMembershipListOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    items, total = membership_service.list_memberships(
        db, clinic_id=clinic_id, skip=skip, limit=limit
    )
    return ClinicMembershipListOut(
        total=total, items=[ClinicMembershipOut.model_validate(m) for m in items]
    )


@router.patch("/members/{membership_id}", response_model=ClinicMembershipOut)
def update_member(
    clinic_id: str,
    membership_id: str,
    payload: ClinicMembershipUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_session),
) -> ClinicMembershipOut:
    assert_path_clinic_matches_tenant(tenant.clinic_id, clinic_id)
    require_clinic_roles(tenant.roles, *_MANAGE_ROLES)
    membership = membership_service.get_membership(
        db, clinic_id=clinic_id, membership_id=membership_id
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_MEMBERSHIP_NOT_FOUND_DETAIL
        )
    try:
        membership = membership_service.update_membership(
            db,
            membership=membership,
            actor_id=tenant.user_id,
            roles=payload.roles,
            branch_ids=payload.branch_ids,
            status_value=payload.status,
        )
    except ClinicMembershipError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return ClinicMembershipOut.model_validate(membership)
