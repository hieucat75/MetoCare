"""Aggregate v1 API router."""

from __future__ import annotations

from fastapi import APIRouter

from .routes import (
    admin,
    ai,
    ai_sessions,
    auth,
    booking,
    care_plans,
    consent,
    doctor,
    doctor_review,
    encounters,
    health,
    health_timeline,
    lab,
    lab_intelligence,
    lab_reference,
    lab_upload,
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
api_router.include_router(encounters.router)
api_router.include_router(care_plans.router)
api_router.include_router(ai_sessions.router)
api_router.include_router(doctor_review.router, prefix="/doctor", tags=["doctor_review"])
api_router.include_router(patients.router)
api_router.include_router(health_timeline.router, prefix="/patients")
api_router.include_router(booking.router)
api_router.include_router(notifications.router)
api_router.include_router(patient_insight.router)
api_router.include_router(narrative.router)
api_router.include_router(doctor.router)
