"""ORM models registry.

Importing this package imports every model module so that all tables register
with ``Base.metadata`` before ``create_all`` / Alembic autogenerate runs.
"""

from .ai import AIClinicalRecommendation, AIConversation, AISession, RecommendationStatus
from .appointment import BookingAppointment
from .auth_tokens import MfaBackupCode, RefreshToken
from .availability import DoctorAvailability
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
from .notification import Notification
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
    "BookingAppointment",
    "BookingHealthSnapshot",
    "CarePlan",
    "Clinic",
    "Consent",
    "Doctor",
    "DoctorAvailability",
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
    "Notification",
    "NutritionLog",
    "SymptomLog",
    "TriageLog",
    "User",
    "UserRole",
]
