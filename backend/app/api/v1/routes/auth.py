"""Authentication routes: register, login, me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, current_user, get_session
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_session)) -> TokenResponse:
    # Public registration is patient-only; elevated roles need admin provisioning.
    role = UserRole.PATIENT if payload.role != UserRole.PATIENT else payload.role
    try:
        user = auth.register(
            db,
            email=str(payload.email),
            password=payload.password,
            full_name=payload.full_name,
            role=role,
        )
    except auth.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    token = auth.issue_token(user)
    return TokenResponse(access_token=token, role=user.role.value, user_id=user.id)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_session)) -> TokenResponse:
    try:
        user = auth.authenticate(db, email=str(payload.email), password=payload.password)
    except auth.AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    token = auth.issue_token(user)
    return TokenResponse(access_token=token, role=user.role.value, user_id=user.id)


@router.get("/me", response_model=UserOut)
def me(
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_session),
) -> UserOut:
    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return UserOut.model_validate(db_user)
