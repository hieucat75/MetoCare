"""Doctor Portal P0 schemas.

Response/request shapes for the doctor-facing clinical workspace:
- dashboard stats
- patient roster (search / risk filter / sort / pagination)
- per-patient clinical timeline
- the UNIFIED review queue (labs + AI recommendations + care plans)
- review decision dispatch

These shapes are contract-fixed: the frontend client re-points to them
byte-for-byte, so field names and literal enum values must not drift.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared literals
# ---------------------------------------------------------------------------

RiskSegment = Literal["low", "medium", "high", "very_high"]
ItemType = Literal["lab_result", "ai_session", "care_plan"]
QueuePriority = Literal["urgent", "high", "normal", "low"]
QueueStatus = Literal["pending_review", "in_review", "approved", "rejected", "request_info"]
TimelineEventType = Literal[
    "lab_uploaded",
    "lab_approved",
    "metric_logged",
    "care_plan_created",
    "care_plan_approved",
    "ai_session",
    "consent_granted",
    "consent_revoked",
]
ReviewDecision = Literal["approved", "rejected", "request_info"]


# ---------------------------------------------------------------------------
# 1. GET /doctor/stats
# ---------------------------------------------------------------------------


class DoctorStats(BaseModel):
    pending_reviews: int
    urgent_reviews: int
    total_patients: int
    reviews_today: int
    avg_review_time_min: float | None = None


# ---------------------------------------------------------------------------
# 2. GET /doctor/patients
# ---------------------------------------------------------------------------


class DoctorPatient(BaseModel):
    # NOTE: this is the PatientProfile.id — it is the id the frontend uses to
    # navigate to /patients/{id}/profile, which is keyed by PatientProfile.id.
    id: str
    full_name: str | None = None
    email: str
    risk_segment: RiskSegment | None = None
    last_metric_at: str | None = None  # ISO-8601
    pending_labs: int = 0
    active_care_plans: int = 0
    consented: bool = False


class DoctorPatientListResponse(BaseModel):
    total: int
    items: list[DoctorPatient]


# ---------------------------------------------------------------------------
# 3. GET /doctor/patients/{patient_id}/timeline
# ---------------------------------------------------------------------------


class TimelineEvent(BaseModel):
    id: str
    event_type: TimelineEventType
    description: str
    occurred_at: str  # ISO-8601
    actor: str | None = None
    metadata: dict | None = None


# ---------------------------------------------------------------------------
# 4. GET /doctor/queue
# ---------------------------------------------------------------------------


class QueueItem(BaseModel):
    # Composite routable id: "{item_type}:{underlying_uuid}" so the PATCH review
    # endpoint can dispatch back to the correct domain (e.g. "lab_result:<uuid>").
    id: str
    patient_id: str
    patient_name: str | None = None
    item_type: ItemType
    priority: QueuePriority
    status: QueueStatus
    summary: str | None = None
    submitted_at: str  # ISO-8601
    assigned_doctor_id: str | None = None


class QueueResponse(BaseModel):
    total: int
    pending_count: int
    items: list[QueueItem]


# ---------------------------------------------------------------------------
# 5. PATCH /doctor/queue/{item_id}/review
# ---------------------------------------------------------------------------


class ReviewDecisionPayload(BaseModel):
    decision: ReviewDecision
    comment: str = Field(min_length=1)
    internal_note: str | None = None


# ---------------------------------------------------------------------------
# 6. GET /doctor/appointments
# ---------------------------------------------------------------------------

AppointmentStatus = Literal["pending", "confirmed", "cancelled", "completed"]


class DoctorAppointment(BaseModel):
    id: str
    patient_id: str
    patient_name: str | None = None
    slot_start: str  # ISO-8601
    slot_end: str  # ISO-8601
    status: AppointmentStatus
    notes: str | None = None
    created_at: str
    updated_at: str


class DoctorAppointmentStats(BaseModel):
    today: int
    upcoming: int
    pending_confirmation: int
    completed: int


class DoctorAppointmentListResponse(BaseModel):
    total: int
    stats: DoctorAppointmentStats
    items: list[DoctorAppointment]
