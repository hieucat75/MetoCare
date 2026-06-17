"""Pydantic schemas for MetoCare API.

Organised by domain:
  auth      — registration, login, token, MFA
  patient   — patient profile CRUD
  health    — metric tracking, trends
  lab       — lab document upload, OCR, interpretation
  clinical  — medication, risk score, symptom log
  ai        — chat, triage, metabolic score
  consent   — consent grant/revoke
  care      — doctor, clinic, appointment, care plan note
  admin     — user management, audit log, system stats
  common    — shared Message / ErrorResponse
"""

from .admin import (
    AuditLogFilter,
    AuditLogOut,
    SystemStatsOut,
    UserAdminOut,
    UserRoleUpdate,
    UserStatusUpdate,
)
from .ai import (
    ChatRequest,
    ChatResponse,
    ScoreRequest,
    ScoreResponse,
    TriageRequest,
    TriageResponse,
    VitalIn,
)
from .auth import (
    LoginRequest,
    LogoutRequest,
    MfaEnrollResponse,
    MfaVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from .care import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentUpdate,
    CarePlanApprove,
    CarePlanCreate,
    CarePlanNoteCreate,
    CarePlanNoteOut,
    CarePlanOut,
    CarePlanUpdate,
    ClinicCreate,
    ClinicOut,
    DoctorCreate,
    DoctorOut,
    DoctorSummaryOut,
    DoctorUpdate,
    EncounterCreate,
    EncounterOut,
    EncounterUpdate,
)
from .clinical import (
    AIClinicalRecommendationOut,
    AIClinicalRecommendationReview,
    AISessionOut,
    MedicationCreate,
    MedicationOut,
    MedicationUpdate,
    RiskScoreOut,
    SymptomLogCreate,
    SymptomLogOut,
)
from .common import ErrorResponse, Message
from .consent import ConsentGrant, ConsentOut
from .health import MetricCreate, MetricOut, TrendOut
from .lab import (
    InterpretationOut,
    InterpretedBiomarkerOut,
    LabDocumentCreate,
    LabDocumentOut,
    LabDocumentStatusOut,
)
from .patient import (
    PatientProfileCreate,
    PatientProfileOut,
    PatientProfileUpdate,
    PatientSummaryOut,
)

__all__ = [
    # admin
    "AuditLogFilter", "AuditLogOut", "SystemStatsOut",
    "UserAdminOut", "UserRoleUpdate", "UserStatusUpdate",
    # ai
    "ChatRequest", "ChatResponse",
    "ScoreRequest", "ScoreResponse",
    "TriageRequest", "TriageResponse",
    "VitalIn",
    # auth
    "LoginRequest", "LogoutRequest", "MfaEnrollResponse", "MfaVerifyRequest",
    "RefreshRequest", "RegisterRequest", "TokenResponse", "UserOut",
    # care
    "AppointmentCreate", "AppointmentOut", "AppointmentUpdate",
    "CarePlanNoteCreate", "CarePlanNoteOut",
    "ClinicCreate", "ClinicOut",
    "DoctorCreate", "DoctorOut", "DoctorSummaryOut", "DoctorUpdate",
    "EncounterCreate", "EncounterOut", "EncounterUpdate",
    "CarePlanCreate", "CarePlanOut", "CarePlanUpdate", "CarePlanApprove",
    # clinical
    "MedicationCreate", "MedicationOut", "MedicationUpdate",
    "RiskScoreOut", "SymptomLogCreate", "SymptomLogOut",
    "AISessionOut", "AIClinicalRecommendationOut", "AIClinicalRecommendationReview",
    # common
    "ErrorResponse", "Message",
    # consent
    "ConsentGrant", "ConsentOut",
    # health
    "MetricCreate", "MetricOut", "TrendOut",
    # lab
    "InterpretationOut", "InterpretedBiomarkerOut",
    "LabDocumentCreate", "LabDocumentOut", "LabDocumentStatusOut",
    # patient
    "PatientProfileCreate", "PatientProfileOut", "PatientProfileUpdate", "PatientSummaryOut",
]
