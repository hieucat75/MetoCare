"""Aggregate v1 API router."""

from __future__ import annotations

from fastapi import APIRouter

from .routes import (
    admin,
    admin_ai_sessions,
    admin_patients,
    ai,
    ai_sessions,
    auth,
    booking,
    care_plans,
    clinical_copilot,
    consent,
    consultations,
    doctor,
    doctor_portal,
    doctor_review,
    encounters,
    health,
    health_timeline,
    lab,
    lab_intelligence,
    lab_reference,
    lab_upload,
    marketplace,
    medications,
    meto,
    narrative,
    notifications,
    patient_insight,
    patients,
    system,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(lab.router)
api_router.include_router(lab_intelligence.router)
api_router.include_router(lab_upload.router)
api_router.include_router(lab_reference.router)
api_router.include_router(ai.router)
api_router.include_router(consent.router)
api_router.include_router(admin.router)
api_router.include_router(admin_ai_sessions.router)
api_router.include_router(admin_patients.router)
api_router.include_router(encounters.router)
api_router.include_router(care_plans.router)
api_router.include_router(ai_sessions.router)
api_router.include_router(doctor_review.router, prefix="/doctor", tags=["doctor_review"])
api_router.include_router(doctor_portal.router)
api_router.include_router(clinical_copilot.router)
api_router.include_router(patients.router)
api_router.include_router(health_timeline.router, prefix="/patients")
api_router.include_router(booking.router)
api_router.include_router(notifications.router)
api_router.include_router(patient_insight.router)
api_router.include_router(narrative.router)
api_router.include_router(medications.router)
api_router.include_router(doctor.router)
api_router.include_router(marketplace.router)
api_router.include_router(consultations.router)
api_router.include_router(meto.router)
