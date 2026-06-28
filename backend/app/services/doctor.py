"""Doctor service — Phase 4A: profile, patient list, dashboard, account creation.

Access rules enforced here (not duplicated in routes):
- list_doctor_patients: returns ONLY patients with active consent granted to this
  doctor's user_id OR with an active encounter assigned to this doctor.
- get_doctor_dashboard: counts derived only from the doctor's own patient set.
- create_doctor_account: caller must already hold SUPER_ADMIN + MFA — this
  function does not re-check RBAC; that is the route layer's responsibility.
"""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.security import hash_password
from app.models.ai import AIClinicalRecommendation, RecommendationStatus
from app.models.care import Appointment, CarePlan, CarePlanStatus, Doctor, Encounter
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services import audit

# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def get_doctor_by_user_id(db: Session, user_id: str) -> Doctor | None:
    """Return the Doctor row linked to the given user, or None."""
    return db.execute(select(Doctor).where(Doctor.user_id == user_id)).scalar_one_or_none()


def _require_doctor(db: Session, user_id: str) -> Doctor:
    doc = get_doctor_by_user_id(db, user_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found. Contact an administrator.",
        )
    if not doc.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor account is inactive.",
        )
    return doc


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


def update_doctor_profile(db: Session, doctor: Doctor, data: dict) -> Doctor:
    """Apply partial update to allowed Doctor fields only."""
    allowed = {"full_name", "bio", "avatar_url", "consultation_fee", "specialty"}
    for field, value in data.items():
        if field in allowed and value is not None:
            setattr(doctor, field, value)
    db.flush()
    return doctor


# ---------------------------------------------------------------------------
# Patient list — consent + encounter union
# ---------------------------------------------------------------------------


def _active_consented_patient_ids(db: Session, doctor_user_id: str) -> set[str]:
    """Patient profile IDs where the patient has granted active consent to this doctor."""
    now = utcnow()
    rows = (
        db.execute(
            select(Consent.patient_id).where(
                Consent.granted_to == doctor_user_id,
                Consent.revoked_at.is_(None),
                (Consent.valid_until.is_(None)) | (Consent.valid_until > now),
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


def _encounter_patient_ids(db: Session, doctor_id: str) -> set[str]:
    """Patient profile IDs that have an active encounter assigned to this doctor."""
    rows = (
        db.execute(
            select(Encounter.patient_id).where(
                Encounter.doctor_id == doctor_id,
                Encounter.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


def _pending_item_count(db: Session, patient_id: str) -> int:
    """Count pending AI recommendations + pending-review care plans for one patient."""
    rec_count = db.execute(
        select(func.count())
        .select_from(AIClinicalRecommendation)
        .where(
            AIClinicalRecommendation.patient_id == patient_id,
            AIClinicalRecommendation.status == RecommendationStatus.PENDING_REVIEW,
            AIClinicalRecommendation.deleted_at.is_(None),
        )
    ).scalar_one()
    plan_count = db.execute(
        select(func.count())
        .select_from(CarePlan)
        .where(
            CarePlan.patient_id == patient_id,
            CarePlan.status == CarePlanStatus.PENDING_REVIEW,
            CarePlan.deleted_at.is_(None),
        )
    ).scalar_one()
    return (rec_count or 0) + (plan_count or 0)


def _last_encounter_at(db: Session, patient_id: str, doctor_id: str) -> dt.datetime | None:
    """Most recent encounter date for this patient–doctor pair."""
    return db.execute(
        select(func.max(Encounter.encounter_date)).where(
            Encounter.patient_id == patient_id,
            Encounter.doctor_id == doctor_id,
            Encounter.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def list_doctor_patients(
    db: Session,
    doctor_id: str,
    doctor_user_id: str,
    *,
    risk: str | None = None,
    has_pending_review: bool = False,
) -> list[dict]:
    """Return patients visible to this doctor (consented + encounter-assigned)."""
    patient_ids = _active_consented_patient_ids(db, doctor_user_id) | _encounter_patient_ids(
        db, doctor_id
    )
    if not patient_ids:
        return []

    stmt = (
        select(PatientProfile, User)
        .join(User, PatientProfile.user_id == User.id)
        .where(PatientProfile.id.in_(patient_ids), User.is_active.is_(True))
    )
    if risk is not None:
        stmt = stmt.where(PatientProfile.risk_segment == risk.lower())

    rows = db.execute(stmt).all()
    result = []
    for profile, user in rows:
        pending = _pending_item_count(db, profile.id)
        if has_pending_review and pending == 0:
            continue
        result.append(
            {
                "patient_id": profile.id,
                "full_name": profile.full_name or user.full_name,
                "risk_segment": profile.risk_segment,
                "last_encounter_at": _last_encounter_at(db, profile.id, doctor_id),
                "pending_items": pending,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Dashboard aggregate
# ---------------------------------------------------------------------------


def get_doctor_dashboard(
    db: Session,
    doctor_id: str,
    doctor_user_id: str,
) -> dict:
    """Aggregate dashboard counts for the authenticated doctor."""
    patient_ids = _active_consented_patient_ids(db, doctor_user_id) | _encounter_patient_ids(
        db, doctor_id
    )

    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + dt.timedelta(days=1)

    appts_today = (
        db.execute(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.scheduled_at >= today_start,
                Appointment.scheduled_at < today_end,
                Appointment.status.in_(["requested", "confirmed"]),
            )
        ).scalar_one()
        or 0
    )

    if patient_ids:
        pending_reviews = (
            db.execute(
                select(func.count())
                .select_from(AIClinicalRecommendation)
                .where(
                    AIClinicalRecommendation.patient_id.in_(patient_ids),
                    AIClinicalRecommendation.status == RecommendationStatus.PENDING_REVIEW,
                    AIClinicalRecommendation.deleted_at.is_(None),
                )
            ).scalar_one()
            or 0
        )

        pending_approvals = (
            db.execute(
                select(func.count())
                .select_from(CarePlan)
                .where(
                    CarePlan.patient_id.in_(patient_ids),
                    CarePlan.status == CarePlanStatus.PENDING_REVIEW,
                    CarePlan.deleted_at.is_(None),
                )
            ).scalar_one()
            or 0
        )

        alert_rows = db.execute(
            select(PatientProfile, User)
            .join(User, PatientProfile.user_id == User.id)
            .where(
                PatientProfile.id.in_(patient_ids),
                PatientProfile.risk_segment == "high",
                User.is_active.is_(True),
            )
            .limit(5)
        ).all()
        recent_alerts = [
            {
                "patient_id": p.id,
                "full_name": p.full_name or u.full_name,
                "risk_segment": p.risk_segment,
            }
            for p, u in alert_rows
        ]
    else:
        pending_reviews = 0
        pending_approvals = 0
        recent_alerts = []

    return {
        "appointments_today": appts_today,
        "pending_reviews": pending_reviews,
        "pending_approvals": pending_approvals,
        "total_patients": len(patient_ids),
        "recent_alerts": recent_alerts,
    }


# ---------------------------------------------------------------------------
# Admin: create doctor account
# ---------------------------------------------------------------------------


def create_doctor_account(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    specialty: str | None,
    license_no: str | None,
    bio: str | None,
    clinic_id: str | None,
    requester_id: str,
) -> tuple[User, Doctor]:
    """Create a User(role=DOCTOR) + linked Doctor row in one transaction.

    Raises HTTPException 409 if the email is already registered.
    Caller must commit after this returns.
    """
    normalized_email = email.lower().strip()
    existing = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=UserRole.DOCTOR,
        is_active=True,
        mfa_enabled=False,
    )
    db.add(user)
    db.flush()

    doctor = Doctor(
        user_id=user.id,
        full_name=full_name,
        specialty=specialty,
        license_no=license_no,
        bio=bio,
        clinic_id=clinic_id,
    )
    db.add(doctor)
    db.flush()

    audit.record(
        db,
        actor_type="admin",
        actor_id=requester_id,
        action="create_doctor_account",
        resource_type="user",
        resource_id=user.id,
        severity="warning",
    )
    return user, doctor
