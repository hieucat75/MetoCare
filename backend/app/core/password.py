"""Password-policy enforcement (BRD §C).

Settings-driven so dev/test can relax while staging/production are held to the
secure defaults (min length + complexity). The startup guard in
config.validate_required_env_vars refuses to boot a real environment whose policy
is relaxed, so this validator and that guard together restore the policy.

Applied only at user-chosen-password entry points (register / change / reset /
admin-create) — never to random backup codes or generated tokens.
"""

from __future__ import annotations

from app.core.config import get_settings


class PasswordPolicyError(ValueError):
    """Raised when a candidate password violates the active policy."""


def validate_password_policy(password: str) -> None:
    """Raise PasswordPolicyError if the password fails the active policy."""
    settings = get_settings()
    if len(password) < settings.password_min_length:
        raise PasswordPolicyError(
            f"Mật khẩu phải có ít nhất {settings.password_min_length} ký tự."
        )
    if settings.password_require_complexity:
        has_letter = any(c.isalpha() for c in password)
        has_digit = any(c.isdigit() for c in password)
        if not (has_letter and has_digit):
            raise PasswordPolicyError("Mật khẩu phải gồm cả chữ và số.")
