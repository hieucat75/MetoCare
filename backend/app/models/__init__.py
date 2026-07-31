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
    DoctorReviewDecision,
    Encounter,
)
from .clinic import (
    ClinicBranch,
    ClinicInvitation,
    ClinicInvitationStatus,
    ClinicMembership,
    ClinicMembershipStatus,
    ClinicPatientRelationship,
    ClinicPatientRelationshipStatus,
    ClinicRole,
    ClinicService,
    ClinicServiceStatus,
    ClinicSubscription,
    ClinicSubscriptionStatus,
    SubscriptionPlan,
)
from .clinical import (
    HealthMetric,
    LabDocument,
    LabResult,
    Medication,
    RiskScore,
    SymptomLog,
)
from .consent import TermsConsent
from .consultation import (
    Consultation,
    ConsultationAccessGrant,
    ConsultationNote,
    ConsultationPayment,
    ConsultationReview,
    ConsultationStatus,
    ConsultationType,
    DoctorVerificationStatus,
    PaymentProvider,
    PaymentStatus,
)
from .drug_catalog import DrugEntry
from .drug_knowledge_ai_generation import KnowledgeAIGeneration
from .drug_knowledge_content import (
    DrugContraindication,
    DrugMonitoring,
    DrugPatientEducation,
    DrugSideEffect,
    DrugUsage,
)
from .drug_knowledge_core import (
    DrugClass,
    DrugIngredient,
    DrugProduct,
    DrugProductIngredient,
    DrugProductName,
)
from .drug_knowledge_governance import ClinicalSpecialty, KnowledgeReviewSpecialty
from .drug_knowledge_lifecycle_transition import KnowledgeLifecycleTransition
from .drug_knowledge_references import DrugReference, KnowledgeReferenceLink
from .governance import AuditLog, Consent
from .medical_document import (
    DocumentExtraction,
    DocumentPage,
    ExtractionCandidate,
    MedicalDocument,
    PromotionLink,
)
from .meto import MetoAuditLog, MetoConsent, MetoConversation, MetoMessage
from .notification import Notification
from .nutrition import NutritionLog
from .ocr_case import OCRCase
from .patient import PatientProfile
from .triage_log import TriageLog
from .user import User, UserRole

__all__ = [
    "MetoAuditLog",
    "MetoConsent",
    "MetoConversation",
    "MetoMessage",
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
    "ClinicBranch",
    "ClinicInvitation",
    "ClinicInvitationStatus",
    "ClinicMembership",
    "ClinicMembershipStatus",
    "ClinicPatientRelationship",
    "ClinicPatientRelationshipStatus",
    "ClinicRole",
    "ClinicService",
    "ClinicServiceStatus",
    "ClinicSubscription",
    "ClinicSubscriptionStatus",
    "SubscriptionPlan",
    "Consent",
    "TermsConsent",
    "Consultation",
    "ConsultationAccessGrant",
    "ConsultationNote",
    "ConsultationPayment",
    "ConsultationReview",
    "ConsultationStatus",
    "ConsultationType",
    "DoctorVerificationStatus",
    "PaymentProvider",
    "PaymentStatus",
    "Doctor",
    "DoctorAvailability",
    "DoctorClinic",
    "DoctorReviewDecision",
    "Encounter",
    "HealthMetric",
    "LabDocument",
    "LabResult",
    "MedicalDocument",
    "DocumentPage",
    "DocumentExtraction",
    "ExtractionCandidate",
    "PromotionLink",
    "Medication",
    "MfaBackupCode",
    "PatientProfile",
    "RefreshToken",
    "RiskScore",
    "Notification",
    "NutritionLog",
    "OCRCase",
    "SymptomLog",
    "DrugEntry",
    "ClinicalSpecialty",
    "KnowledgeReviewSpecialty",
    "DrugReference",
    "KnowledgeReferenceLink",
    "KnowledgeAIGeneration",
    "KnowledgeLifecycleTransition",
    "DrugClass",
    "DrugIngredient",
    "DrugProduct",
    "DrugProductIngredient",
    "DrugProductName",
    "DrugUsage",
    "DrugPatientEducation",
    "DrugSideEffect",
    "DrugMonitoring",
    "DrugContraindication",
    "TriageLog",
    "User",
    "UserRole",
]
