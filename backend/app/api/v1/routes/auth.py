"""Authentication routes: register, login (with MFA), refresh, logout, MFA setup."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, enforce_rate_limit, get_session
from app.core.config import get_settings
from app.core.phone import normalize_vn_phone
from app.core.ratelimit import get_lockout
from app.core.security import decode_token
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.schemas.auth import (
    AccountUpdateRequest,
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    MfaEnrollResponse,
    MfaVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.schemas.common import Message
from app.services import audit, auth, mfa

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    request: Request, payload: RegisterRequest, db: Session = Depends(get_session)
) -> TokenResponse:
    enforce_rate_limit(request, "register")
    # Public self-registration is always patient-only.
    role = UserRole.PATIENT
    normalized_phone: str | None = None
    if payload.phone:
        normalized_phone = normalize_vn_phone(payload.phone)
        if normalized_phone is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Số điện thoại di động Việt Nam không hợp lệ.",
            )
    try:
        user = auth.register(
            db,
            email=str(payload.email) if payload.email else None,
            phone=normalized_phone,
            password=payload.password,
            full_name=payload.full_name,
            role=role,
        )
    except auth.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    access, refresh = auth.issue_tokens(db, user, mfa=False)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        role=user.role.value,
        user_id=user.id,
        mfa=False,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request, payload: LoginRequest, db: Session = Depends(get_session)
) -> TokenResponse:
    enforce_rate_limit(request, "login")
    settings = get_settings()
    lockout = get_lockout()
    # Patients log in by phone, admin/doctor by email. Normalize phone for a
    # stable lookup + lockout key; reject a malformed phone early.
    phone_id: str | None = None
    if payload.phone:
        phone_id = normalize_vn_phone(payload.phone)
        if phone_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Số điện thoại di động Việt Nam không hợp lệ.",
            )
    lkey = phone_id or str(payload.email).lower()
    if lockout.is_locked(
        lkey,
        max_failures=settings.lockout_max_failures,
        cooldown_seconds=settings.lockout_cooldown_minutes * 60,
    ):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to repeated failed logins.",
        )

    try:
        user = auth.authenticate(
            db,
            email=str(payload.email) if payload.email else None,
            phone=phone_id,
            password=payload.password,
        )
    except auth.AuthError as exc:
        lockout.record_failure(lkey)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    mfa_ok = False
    if user.mfa_enabled:
        mfa_ok = mfa.verify_second_factor(
            db, user, totp_code=payload.totp_code, backup_code=payload.backup_code
        )
        if not mfa_ok:
            lockout.record_failure(lkey)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA code required or invalid.",
            )

    # Successful login (incl. MFA when enabled) clears the lockout counter.
    lockout.reset(lkey)
    access, refresh = auth.issue_tokens(db, user, mfa=mfa_ok)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        role=user.role.value,
        user_id=user.id,
        mfa=mfa_ok,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request, payload: RefreshRequest, db: Session = Depends(get_session)
) -> TokenResponse:
    enforce_rate_limit(request, "refresh")
    try:
        access, new_refresh, user = auth.refresh_session(db, payload.refresh_token)
    except auth.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    # mfa level is preserved by refresh_session via the stored token.
    claims = decode_token(access) or {}
    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        role=user.role.value,
        user_id=user.id,
        mfa=bool(claims.get("mfa")),
    )


@router.post("/logout", response_model=Message)
def logout(
    payload: LogoutRequest,
    actor: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> Message:
    auth.revoke_refresh(db, payload.refresh_token, actor_id=actor.id)
    return Message(message="logged out")


@router.get("/me", response_model=UserOut)
def me(
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> UserOut:
    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return _user_out(db, db_user)


def _user_out(db: Session, db_user: User) -> UserOut:
    """Build a UserOut, resolving patient_profile_id for PATIENT callers."""
    out = UserOut.model_validate(db_user)
    if db_user.role == UserRole.PATIENT:
        profile = db.execute(
            select(PatientProfile).where(PatientProfile.user_id == db_user.id)
        ).scalar_one_or_none()
        out.patient_profile_id = profile.id if profile is not None else None
    return out


@router.post("/change-password", response_model=Message)
def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    actor: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> Message:
    """Change the current user's password (PR-F).

    Requires the correct current password. Rate-limited to deter brute force.
    """
    enforce_rate_limit(request, "login")
    try:
        auth.change_password(
            db,
            user_id=actor.id,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except auth.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return Message(message="password changed")


@router.patch("/account", response_model=UserOut)
def update_account(
    payload: AccountUpdateRequest,
    actor: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> UserOut:
    """Update account settings: email + notification preferences (PR-F)."""
    try:
        db_user = auth.update_account(
            db, user_id=actor.id, data=payload.model_dump(exclude_unset=True)
        )
    except auth.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _user_out(db, db_user)


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
def mfa_enroll(
    actor: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> MfaEnrollResponse:
    db_user = db.get(User, actor.id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="user not found")
    secret, uri, codes = mfa.begin_enrollment(db, db_user)
    audit.record(
        db,
        actor_type="user",
        actor_id=actor.id,
        action="mfa_enroll",
        resource_type="user",
        resource_id=actor.id,
    )
    db.commit()
    return MfaEnrollResponse(secret=secret, provisioning_uri=uri, backup_codes=codes)


@router.post("/mfa/verify", response_model=Message)
def mfa_verify(
    request: Request,
    payload: MfaVerifyRequest,
    actor: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> Message:
    enforce_rate_limit(request, "mfa_verify")
    db_user = db.get(User, actor.id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if not mfa.confirm_enrollment(db, db_user, payload.totp_code):
        raise HTTPException(status_code=400, detail="invalid TOTP code")
    return Message(message="mfa enabled")
