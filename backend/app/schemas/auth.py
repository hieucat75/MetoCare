"""Auth schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None
    # Self-service registration is patient-only; elevated roles are provisioned
    # by an admin (not via this public endpoint).
    role: UserRole = UserRole.PATIENT


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Required only when the account has MFA enabled.
    totp_code: str | None = None
    backup_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    mfa: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class MfaEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str
    backup_codes: list[str]


class MfaVerifyRequest(BaseModel):
    totp_code: str


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    full_name: str | None = None
    mfa_enabled: bool = False
    # Populated for PATIENT role callers; None for all other roles.
    patient_profile_id: str | None = None

    model_config = {"from_attributes": True}
