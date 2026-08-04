"""Aggregate v1 API router."""

from __future__ import annotations

from fastapi import APIRouter

from .routes import (
    account,
    admin,
    admin_ai_sessions,
    admin_patients,
    ai,
    ai_sessions,
    auth,
    booking,
    care_plans,
    clinic_appointments,
    clinic_branches,
    clinic_members,
    clinic_patients,
    clinic_queue,
    clinic_services,
    clinic_subscriptions,
    clinical_copilot,
    clinics,
    consent,
    consultations,
    dashboard,
    doctor,
    doctor_portal,
    doctor_review,
    documents,
    encounters,
    health,
    health_timeline,
    lab,
    lab_intelligence,
    lab_reference,
    lab_upload,
    marketplace,
    medication_knowledge,
    medication_schedule,
    medication_source,
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
# Patient self-service GDPR data-subject rights — export + account deletion.
api_router.include_router(account.router)
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
# Medical Document Intelligence (Journey 2) — secure upload → OCR → per-candidate
# confirm → promote. Gated by FeatureFlag.OCR (fail-closed default).
api_router.include_router(documents.router)
# Journey 3 — action-first patient dashboard (BRD §I).
api_router.include_router(dashboard.router)
api_router.include_router(health_timeline.router, prefix="/patients")
api_router.include_router(booking.router)
api_router.include_router(notifications.router)
api_router.include_router(patient_insight.router)
api_router.include_router(narrative.router)
api_router.include_router(medications.router)
# Journey 3 — medication schedule / reminder (deterministic + in-app) / adherence.
api_router.include_router(medication_schedule.router)
# BRD §F — reverse provenance: medication → source document + OCR origin.
# Additive read; gated by the same fail-closed `documents` consent as /documents.
api_router.include_router(medication_source.router)
# Medication Knowledge K2 Slice 1 — read-only retrieval (gated by
# FeatureFlag.MEDICATION_KNOWLEDGE_RETRIEVAL, fail-closed default; see
# app/api/deps_medication_knowledge.py).
api_router.include_router(medication_knowledge.router)
api_router.include_router(doctor.router)
api_router.include_router(marketplace.router)
api_router.include_router(consultations.router)
api_router.include_router(meto.router)
# Clinic SaaS Phase C0 — multi-tenant foundation (gated by FeatureFlag.CLINIC_SAAS,
# fail-closed default; see app/api/deps_clinic_saas.py).
api_router.include_router(clinics.router)
api_router.include_router(clinic_branches.router)
api_router.include_router(clinic_members.router)
api_router.include_router(clinic_members.accept_router)
api_router.include_router(clinic_services.router)
api_router.include_router(clinic_patients.router)
api_router.include_router(clinic_appointments.router)
api_router.include_router(clinic_queue.router)
api_router.include_router(clinic_queue.checkin_router)
api_router.include_router(clinic_subscriptions.router)
