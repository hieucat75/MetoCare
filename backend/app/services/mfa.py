"""MFA (TOTP) service — enrollment, verification, backup codes.

TOTP secrets are stored encrypted (User.mfa_secret is an EncryptedString). Backup
codes are stored only as Argon2 hashes and are single-use. No external calls.
"""

from __future__ import annotations

import secrets

import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.security import hash_password, verify_password
from app.models.auth_tokens import MfaBackupCode
from app.models.user import User

_ISSUER = "Metabolic Care Platform"
_BACKUP_CODE_COUNT = 10


def _new_backup_code() -> str:
    # 10 hex chars (~40 bits); single-use + Argon2-hashed at rest.
    return secrets.token_hex(5)


def begin_enrollment(db: Session, user: User) -> tuple[str, str, list[str]]:
    """Generate a TOTP secret + backup codes. MFA stays disabled until verified.

    Returns (secret, provisioning_uri, backup_codes). Backup codes are returned
    in plaintext ONCE for the user to store; only hashes are persisted.
    """
    secret = pyotp.random_base32()
    user.mfa_secret = secret  # encrypted by the ORM type
    user.mfa_enabled = False

    # Replace any prior backup codes.
    db.query(MfaBackupCode).filter(MfaBackupCode.user_id == user.id).delete()
    codes = [_new_backup_code() for _ in range(_BACKUP_CODE_COUNT)]
    for code in codes:
        db.add(MfaBackupCode(user_id=user.id, code_hash=hash_password(code)))
    db.commit()

    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=_ISSUER)
    return secret, uri, codes


def verify_totp(user: User, code: str) -> bool:
    if not user.mfa_secret or not code:
        return False
    # valid_window=1 tolerates ~30s clock skew.
    return pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1)


def confirm_enrollment(db: Session, user: User, code: str) -> bool:
    """Enable MFA once the user proves possession of the secret."""
    if verify_totp(user, code):
        user.mfa_enabled = True
        db.commit()
        return True
    return False


def verify_backup_code(db: Session, user: User, code: str) -> bool:
    if not code:
        return False
    rows = db.execute(
        select(MfaBackupCode).where(
            MfaBackupCode.user_id == user.id, MfaBackupCode.used_at.is_(None)
        )
    ).scalars()
    for bc in rows:
        if verify_password(code, bc.code_hash):
            bc.used_at = utcnow()
            db.commit()
            return True
    return False


def verify_second_factor(
    db: Session, user: User, *, totp_code: str | None, backup_code: str | None
) -> bool:
    """Accept either a valid TOTP or a valid (single-use) backup code."""
    if totp_code and verify_totp(user, totp_code):
        return True
    if backup_code and verify_backup_code(db, user, backup_code):
        return True
    return False
