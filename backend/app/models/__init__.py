"""ORM models registry.

Importing this package imports every model module so that all tables register
with ``Base.metadata`` before ``create_all`` / Alembic autogenerate runs.
"""

from .ai import AIConversation
from .auth_tokens import MfaBackupCode, RefreshToken
from .care import Appointment, Clinic, Doctor
from .clinical import (
    HealthMetric,
    LabDocument,
    LabResult,
    Medication,
    RiskScore,
    SymptomLog,
)
from .governance import AuditLog, Consent
from .patient import PatientProfile
from .user import User, UserRole

__all__ = [
    "AIConversation",
    "Appointment",
    "AuditLog",
    "Clinic",
    "Consent",
    "Doctor",
    "HealthMetric",
    "LabDocument",
    "LabResult",
    "Medication",
    "MfaBackupCode",
    "PatientProfile",
    "RefreshToken",
    "RiskScore",
    "SymptomLog",
    "User",
    "UserRole",
]
