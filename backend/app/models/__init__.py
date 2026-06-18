"""ORM models registry.

Importing this package imports every model module so that all tables register
with ``Base.metadata`` before ``create_all`` / Alembic autogenerate runs.
"""

from .ai import AIClinicalRecommendation, AIConversation, AISession, RecommendationStatus
from .auth_tokens import MfaBackupCode, RefreshToken
from .care import (
    Appointment,
    BookingHealthSnapshot,
    CarePlan,
    Clinic,
    Doctor,
    DoctorClinic,
    Encounter,
)
from .clinical import (
    HealthMetric,
    LabDocument,
    LabResult,
    Medication,
    RiskScore,
    SymptomLog,
)
from .governance import AuditLog, Consent
from .nutrition import NutritionLog
from .patient import PatientProfile
from .triage_log import TriageLog
from .user import User, UserRole

__all__ = [
    "AIClinicalRecommendation",
    "AIConversation",
    "AISession",
    "RecommendationStatus",
    "Appointment",
    "AuditLog",
    "BookingHealthSnapshot",
    "CarePlan",
    "Clinic",
    "Consent",
    "Doctor",
    "DoctorClinic",
    "Encounter",
    "HealthMetric",
    "LabDocument",
    "LabResult",
    "Medication",
    "MfaBackupCode",
    "PatientProfile",
    "RefreshToken",
    "RiskScore",
    "NutritionLog",
    "SymptomLog",
    "TriageLog",
    "User",
    "UserRole",
]
