"""Auth schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.user import UserRole


class ConsentInput(BaseModel):
    """Terms of Use + Privacy Policy acceptance captured at registration.

    Optional on RegisterRequest so existing callers stay valid (non-breaking).
    """

    accepted: bool = False
    terms_version: str = Field(max_length=32)
    privacy_version: str = Field(max_length=32)
    app_version: str | None = Field(default=None, max_length=32)
    locale: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    device_platform: str | None = Field(default=None, max_length=64)
    accepted_source: str | None = Field(default=None, max_length=32)
    accepted_language: str | None = Field(default=None, max_length=32)


class RegisterRequest(BaseModel):
    # Patients self-register with `phone`; `email` path is kept for compatibility
    # (e.g. admin-provisioned / legacy). Exactly one identifier is required.
    email: EmailStr | None = None
    phone: str | None = None
    # Build/test phase policy: passwords are only required to be >=6 chars
    # (no complexity rules).
    password: str = Field(min_length=6)
    full_name: str | None = None
    # Self-service registration is patient-only; elevated roles are provisioned
    # by an admin (not via this public endpoint).
    role: UserRole = UserRole.PATIENT
    # Optional legal-consent block (Terms + Privacy). When present and accepted,
    # a terms_consents row is written atomically with the new account.
    consent: ConsentInput | None = None

    @model_validator(mode="after")
    def _one_identifier(self) -> RegisterRequest:
        if bool(self.email) == bool(self.phone):
            raise ValueError("provide exactly one of email or phone")
        return self


class LoginRequest(BaseModel):
    # Patients log in with `phone`; admin/doctor with `email`. Exactly one.
    email: EmailStr | None = None
    phone: str | None = None
    password: str
    # Required only when the account has MFA enabled.
    totp_code: str | None = None
    backup_code: str | None = None

    @model_validator(mode="after")
    def _one_identifier(self) -> LoginRequest:
        if bool(self.email) == bool(self.phone):
            raise ValueError("provide exactly one of email or phone")
        return self


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
    email: str | None = None
    phone: str | None = None
    role: str
    full_name: str | None = None
    mfa_enabled: bool = False
    # PR-F: notification preferences
    notify_medication: bool = True
    notify_lab_results: bool = True
    notify_doctor_messages: bool = True
    # Populated for PATIENT role callers; None for all other roles.
    patient_profile_id: str | None = None
    # Latest Terms version the user has accepted (None if never) — login gate.
    accepted_terms_version: str | None = None

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class AccountUpdateRequest(BaseModel):
    """Partial update of account-level settings (PR-F). All fields optional."""

    email: EmailStr | None = None
    notify_medication: bool | None = None
    notify_lab_results: bool | None = None
    notify_doctor_messages: bool | None = None
