"""Doctor Portal P0 service — dashboard, roster, timeline, unified review queue.

Layering: this service is the doctor-facing clinical *workspace*. It is kept
separate from ``app.services.doctor`` (marketplace self-service ``/doctors/me``)
and ``app.services.doctor_review`` (the AI-recommendation review workflow),
which it composes rather than duplicates.

Scoping rule (patient population + queue):
    A doctor may see a patient / act on an item when EITHER
      (a) the patient granted this doctor an active consent, OR
      (b) the patient has an encounter assigned to this doctor.
    This mirrors ``doctor.list_doctor_patients`` (consent OR encounter). For the
    AI-recommendation slice of the queue we delegate to
    ``DoctorReviewService.get_pending_queue`` so its clinic/consent/encounter
    scoping stays the single source of truth.

PHI (patient full_name) decrypts transparently via the ``EncryptedString`` ORM
type on read, so ``profile.full_name`` is already plaintext here.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.models.ai import (
    AIClinicalRecommendation,
    RecommendationStatus,
)
from app.models.care import (
    CarePlan,
    CarePlanStatus,
    Doctor,
    DoctorReviewDecision,
    Encounter,
)
from app.models.clinical import HealthMetric, LabResult
from app.models.governance import Consent
from app.models.patient import PatientProfile
from app.models.user import User
from app.services import audit
from app.services.care_plan import DoctorCarePlanService
from app.services.doctor_review import DoctorReviewService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class NotFound(Exception):
    """Queue item / patient not found."""


class PermissionDenied(Exception):
    """Doctor not permitted to act on this item."""


class InvalidTransition(Exception):
    """The requested review decision is not valid for the item's current state."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HIGH_RISK_SEGMENTS = frozenset({"high", "very_high"})
# Risk ordering for "risk desc" sort (unknown risk sorts last).
_RISK_ORDER = {"very_high": 4, "high": 3, "medium": 2, "low": 1}

# Map an item domain into the composite id prefix.
_ITEM_TYPE_LAB = "lab_result"
_ITEM_TYPE_AI = "ai_session"
_ITEM_TYPE_CARE = "care_plan"


def _iso(value: dt.datetime | dt.date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


# ---------------------------------------------------------------------------
# Doctor resolution
# ---------------------------------------------------------------------------


def _get_doctor(db: Session, user_id: str) -> Doctor | None:
    return db.execute(select(Doctor).where(Doctor.user_id == user_id)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Patient population (consent OR encounter) — shared by stats + roster + queue
# ---------------------------------------------------------------------------


def _consented_patient_ids(db: Session, doctor_user_id: str) -> set[str]:
    """PatientProfile ids with any active consent granted to this doctor's user id."""
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


def _profile_scope_consented_ids(db: Session, doctor_user_id: str) -> set[str]:
    """PatientProfile ids with an active consent covering scope='profile'.

    ``data_scope='*'`` also covers 'profile'. Used only for the ``consented``
    flag on the roster (a stricter check than mere visibility).
    """
    now = utcnow()
    rows = (
        db.execute(
            select(Consent.patient_id).where(
                Consent.granted_to == doctor_user_id,
                Consent.data_scope.in_(("*", "profile")),
                Consent.revoked_at.is_(None),
                (Consent.valid_until.is_(None)) | (Consent.valid_until > now),
                Consent.valid_from <= now,
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


def _encounter_patient_ids(db: Session, doctor_id: str) -> set[str]:
    """PatientProfile ids with an encounter assigned to this doctor."""
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


def _visible_patient_ids(db: Session, doctor: Doctor) -> set[str]:
    return _consented_patient_ids(db, doctor.user_id) | _encounter_patient_ids(db, doctor.id)


# ---------------------------------------------------------------------------
# Per-patient count helpers
# ---------------------------------------------------------------------------


def _pending_labs_count(db: Session, patient_ids: list[str]) -> dict[str, int]:
    """Labs awaiting doctor review, keyed by patient_id.

    There is no dedicated lab review-status column; a lab is "pending review"
    when a doctor has not yet verified it (``verified_by_doctor is False``).
    """
    if not patient_ids:
        return {}
    rows = db.execute(
        select(LabResult.patient_id, func.count())
        .where(
            LabResult.patient_id.in_(patient_ids),
            LabResult.deleted_at.is_(None),
            LabResult.verified_by_doctor.is_(False),
        )
        .group_by(LabResult.patient_id)
    ).all()
    return {pid: cnt for pid, cnt in rows}


def _active_care_plans_count(db: Session, patient_ids: list[str]) -> dict[str, int]:
    if not patient_ids:
        return {}
    rows = db.execute(
        select(CarePlan.patient_id, func.count())
        .where(
            CarePlan.patient_id.in_(patient_ids),
            CarePlan.status == CarePlanStatus.ACTIVE,
            CarePlan.deleted_at.is_(None),
        )
        .group_by(CarePlan.patient_id)
    ).all()
    return {pid: cnt for pid, cnt in rows}


def _last_metric_at(db: Session, patient_ids: list[str]) -> dict[str, dt.datetime]:
    if not patient_ids:
        return {}
    rows = db.execute(
        select(HealthMetric.patient_id, func.max(HealthMetric.measured_at))
        .where(
            HealthMetric.patient_id.in_(patient_ids),
            HealthMetric.deleted_at.is_(None),
        )
        .group_by(HealthMetric.patient_id)
    ).all()
    return {pid: ts for pid, ts in rows if ts is not None}


# ---------------------------------------------------------------------------
# 1. Stats
# ---------------------------------------------------------------------------


def get_stats(db: Session, doctor_user_id: str) -> dict:
    """Aggregate dashboard stats for the calling doctor.

    Derived from the unified queue population: pending/urgent counts come from
    the same three sources the queue exposes. ``reviews_today`` and
    ``avg_review_time_min`` are sourced from AIClinicalRecommendation review
    timestamps (the only domain that records a reviewer + reviewed_at).
    """
    doctor = _get_doctor(db, doctor_user_id)
    if doctor is None:
        return {
            "pending_reviews": 0,
            "urgent_reviews": 0,
            "total_patients": 0,
            "reviews_today": 0,
            "avg_review_time_min": None,
        }

    items = _build_queue_items(db, doctor)
    pending_items = [i for i in items if i["status"] == "pending_review"]
    pending_reviews = len(pending_items)
    urgent_reviews = sum(1 for i in pending_items if i["priority"] == "urgent")

    total_patients = len(_visible_patient_ids(db, doctor))

    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + dt.timedelta(days=1)

    reviews_today = (
        db.execute(
            select(func.count())
            .select_from(AIClinicalRecommendation)
            .where(
                AIClinicalRecommendation.reviewed_by_doctor_id == doctor.id,
                AIClinicalRecommendation.reviewed_at >= today_start,
                AIClinicalRecommendation.reviewed_at < today_end,
            )
        ).scalar_one()
        or 0
    )

    # avg minutes submitted(created_at) -> reviewed(reviewed_at) for this doctor.
    reviewed_rows = db.execute(
        select(
            AIClinicalRecommendation.created_at,
            AIClinicalRecommendation.reviewed_at,
        ).where(
            AIClinicalRecommendation.reviewed_by_doctor_id == doctor.id,
            AIClinicalRecommendation.reviewed_at.is_not(None),
        )
    ).all()
    durations: list[float] = []
    for created_at, reviewed_at in reviewed_rows:
        if created_at is None or reviewed_at is None:
            continue
        delta = _as_naive(reviewed_at) - _as_naive(created_at)
        minutes = delta.total_seconds() / 60.0
        if minutes >= 0:
            durations.append(minutes)
    avg_review_time_min = round(sum(durations) / len(durations), 2) if durations else None

    return {
        "pending_reviews": pending_reviews,
        "urgent_reviews": urgent_reviews,
        "total_patients": total_patients,
        "reviews_today": reviews_today,
        "avg_review_time_min": avg_review_time_min,
    }


def _as_naive(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


# ---------------------------------------------------------------------------
# 2. Patient roster
# ---------------------------------------------------------------------------

_VALID_SORTS = frozenset({"risk", "last_activity", "pending", "name"})
_VALID_RISK_FILTERS = frozenset({"low", "medium", "high"})


def list_patients(
    db: Session,
    doctor_user_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    risk: str | None = None,
    sort: str = "risk",
) -> tuple[int, list[dict]]:
    """Return (total_before_pagination, page_of_patient_dicts)."""
    doctor = _get_doctor(db, doctor_user_id)
    if doctor is None:
        return 0, []

    patient_ids = _visible_patient_ids(db, doctor)
    if not patient_ids:
        return 0, []

    stmt = (
        select(PatientProfile, User)
        .join(User, PatientProfile.user_id == User.id)
        .where(PatientProfile.id.in_(patient_ids), User.is_active.is_(True))
    )
    rows = db.execute(stmt).all()

    ids = [p.id for p, _ in rows]
    pending_labs = _pending_labs_count(db, ids)
    care_plans = _active_care_plans_count(db, ids)
    last_metric = _last_metric_at(db, ids)
    profile_consented = _profile_scope_consented_ids(db, doctor.user_id)
    # PHI (name/email/risk) is only exposed to a doctor with a real care
    # relationship: a profile-scope consent OR an encounter. A patient visible
    # only via a narrow consent (e.g. ai_use) must NOT leak identity/risk.
    phi_authorized = profile_consented | _encounter_patient_ids(db, doctor.id)

    q = (search or "").strip().lower()
    risk_filter = (risk or "").strip().lower() or None

    enriched: list[dict] = []
    for profile, user in rows:
        authorized = profile.id in phi_authorized
        # Mask sensitive fields BEFORE building the search haystack so a masked
        # patient can NOT be discovered by name/email search.
        full_name = (profile.full_name or user.full_name) if authorized else None
        email = (user.email or "") if authorized else ""
        seg = profile.risk_segment if authorized else None

        if risk_filter is not None:
            # 'high' includes very_high; low/medium are exact.
            if risk_filter == "high":
                if seg not in _HIGH_RISK_SEGMENTS:
                    continue
            elif seg != risk_filter:
                continue

        if q:
            haystack = " ".join(filter(None, [full_name, email])).lower()
            if q not in haystack:
                continue

        enriched.append(
            {
                "id": profile.id,
                "full_name": full_name,
                "email": email,
                "risk_segment": seg,
                "last_metric_at": _iso(last_metric.get(profile.id)),
                "pending_labs": pending_labs.get(profile.id, 0),
                "active_care_plans": care_plans.get(profile.id, 0),
                "consented": profile.id in profile_consented,
            }
        )

    _sort_patients(enriched, sort)

    total = len(enriched)
    page = enriched[offset : offset + limit]
    return total, page


def _sort_patients(rows: list[dict], sort: str) -> None:
    key = sort if sort in _VALID_SORTS else "risk"
    if key == "name":
        rows.sort(key=lambda r: (r["full_name"] or "").lower())
    elif key == "pending":
        rows.sort(
            key=lambda r: (r["pending_labs"], (r["full_name"] or "").lower()),
            reverse=False,
        )
        rows.sort(key=lambda r: r["pending_labs"], reverse=True)
    elif key == "last_activity":
        rows.sort(
            key=lambda r: r["last_metric_at"] or "",
            reverse=True,
        )
    else:  # risk desc, then name asc
        rows.sort(key=lambda r: (r["full_name"] or "").lower())
        rows.sort(key=lambda r: _RISK_ORDER.get(r["risk_segment"] or "", 0), reverse=True)


# ---------------------------------------------------------------------------
# 4/5. Unified queue building
# ---------------------------------------------------------------------------


def _lab_priority(row: LabResult) -> str:
    """Derive queue priority from lab clinical signal."""
    status = (row.status or "").lower()
    if status == "critical":
        return "urgent"
    if status in ("high", "low"):
        return "high"
    if (row.data_quality_flag or "").lower() == "flag":
        return "high"
    return "normal"


def _lab_summary(row: LabResult) -> str:
    parts = [row.test_name or row.canonical_name or "Xét nghiệm"]
    if row.value is not None:
        unit = f" {row.unit}" if row.unit else ""
        parts.append(f"= {row.value}{unit}")
    if row.status:
        parts.append(f"({row.status})")
    return " ".join(parts)


def _map_care_plan_status(status: str) -> str:
    s = (status or "").upper()
    if s == CarePlanStatus.PENDING_REVIEW:
        return "pending_review"
    if s in (CarePlanStatus.APPROVED, CarePlanStatus.ACTIVE):
        return "approved"
    if s == CarePlanStatus.REJECTED:
        return "rejected"
    return "pending_review"


def _map_rec_status(status: str) -> str:
    s = (status or "").lower()
    if s == RecommendationStatus.PENDING_REVIEW:
        return "pending_review"
    if s == RecommendationStatus.ACCEPTED:
        return "approved"
    if s == RecommendationStatus.REJECTED:
        return "rejected"
    if s == RecommendationStatus.REQUEST_INFO:
        return "request_info"
    return "pending_review"


def _patient_name_map(db: Session, patient_ids: set[str]) -> dict[str, str | None]:
    if not patient_ids:
        return {}
    rows = db.execute(
        select(PatientProfile.id, PatientProfile.full_name).where(
            PatientProfile.id.in_(patient_ids)
        )
    ).all()
    return {pid: name for pid, name in rows}


def _build_queue_items(db: Session, doctor: Doctor) -> list[dict]:
    """Unify pending labs + AI recs + care plans into one list of dicts.

    Only ``pending_review`` items are surfaced (the review inbox); acted-upon
    items drop out. Scope is the doctor's visible patient population, except the
    AI slice which defers to ``DoctorReviewService.get_pending_queue`` scoping.
    """
    visible = _visible_patient_ids(db, doctor)
    items: list[dict] = []

    # (a) lab_result — pending doctor verification, for visible patients.
    if visible:
        lab_rows = db.execute(
            select(LabResult).where(
                LabResult.patient_id.in_(visible),
                LabResult.deleted_at.is_(None),
                LabResult.verified_by_doctor.is_(False),
            )
        ).scalars().all()
        for row in lab_rows:
            items.append(
                {
                    "id": f"{_ITEM_TYPE_LAB}:{row.id}",
                    "patient_id": row.patient_id,
                    "item_type": _ITEM_TYPE_LAB,
                    "priority": _lab_priority(row),
                    "status": "pending_review",
                    "summary": _lab_summary(row),
                    "submitted_at": row.created_at,
                    "assigned_doctor_id": None,
                }
            )

    # (b) ai_session — reuse DoctorReviewService scoping (clinic/consent/encounter).
    doctor_user = db.get(User, doctor.user_id) if doctor.user_id else None
    if doctor_user is not None:
        recs = DoctorReviewService(db).get_pending_queue(doctor_user)
        for rec in recs:
            items.append(
                {
                    "id": f"{_ITEM_TYPE_AI}:{rec.id}",
                    "patient_id": rec.patient_id,
                    "item_type": _ITEM_TYPE_AI,
                    "priority": _rec_priority(rec),
                    "status": _map_rec_status(rec.status),
                    "summary": _rec_summary(rec),
                    "submitted_at": rec.created_at,
                    "assigned_doctor_id": (
                        rec.reviewed_by_doctor_id if rec.reviewed_by_doctor_id else None
                    ),
                }
            )

    # (c) care_plan — pending review, for visible patients.
    if visible:
        plan_rows = db.execute(
            select(CarePlan).where(
                CarePlan.patient_id.in_(visible),
                CarePlan.status == CarePlanStatus.PENDING_REVIEW,
                CarePlan.deleted_at.is_(None),
            )
        ).scalars().all()
        for plan in plan_rows:
            items.append(
                {
                    "id": f"{_ITEM_TYPE_CARE}:{plan.id}",
                    "patient_id": plan.patient_id,
                    "item_type": _ITEM_TYPE_CARE,
                    "priority": "normal",
                    "status": _map_care_plan_status(plan.status),
                    "summary": plan.title,
                    "submitted_at": plan.created_at,
                    "assigned_doctor_id": plan.approved_by_doctor_id,
                }
            )

    # Attach decrypted patient names (single batched read).
    name_map = _patient_name_map(db, {i["patient_id"] for i in items})
    for i in items:
        i["patient_name"] = name_map.get(i["patient_id"])
        i["submitted_at"] = _iso(i["submitted_at"]) or _iso(utcnow())

    return items


def _rec_priority(rec: AIClinicalRecommendation) -> str:
    """AI recommendations carry no priority column; elevate low-confidence ones."""
    conf = rec.ai_confidence
    if conf is not None and conf < 0.5:
        return "high"
    return "normal"


def _rec_summary(rec: AIClinicalRecommendation) -> str:
    return f"AI: {rec.recommendation_type}"


def get_queue(
    db: Session,
    doctor_user_id: str,
    *,
    status: str | None = None,
    priority: str | None = None,
    item_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return the unified review queue for the calling doctor."""
    doctor = _get_doctor(db, doctor_user_id)
    if doctor is None:
        return {"total": 0, "pending_count": 0, "items": []}

    items = _build_queue_items(db, doctor)
    pending_count = sum(1 for i in items if i["status"] == "pending_review")

    if status:
        items = [i for i in items if i["status"] == status]
    if priority:
        items = [i for i in items if i["priority"] == priority]
    if item_type:
        items = [i for i in items if i["item_type"] == item_type]

    # Newest first, urgent surfaced by priority within same time is not required
    # by the contract; keep a stable, useful order: submitted_at desc.
    items.sort(key=lambda i: i["submitted_at"] or "", reverse=True)

    total = len(items)
    page = items[offset : offset + limit]
    return {"total": total, "pending_count": pending_count, "items": page}


# ---------------------------------------------------------------------------
# 3. Timeline (consent-gated; mapping delegates to the FE-facing enum)
# ---------------------------------------------------------------------------

# Source event_type (from HealthTimelineEngine) -> FE-facing timeline enum.
# Engine emits: abnormal_lab, lab_result, blood_pressure, weight_change,
# medication_started, symptom (see app.domain.health_timeline).
_TIMELINE_TYPE_MAP = {
    "abnormal_lab": "lab_uploaded",
    "lab_result": "lab_uploaded",
    "lab_uploaded": "lab_uploaded",
    "lab_approved": "lab_approved",
    "blood_pressure": "metric_logged",
    "weight_change": "metric_logged",
    "metric_logged": "metric_logged",
    "medication_started": "metric_logged",
    "symptom": "metric_logged",
    "care_plan_created": "care_plan_created",
    "care_plan_approved": "care_plan_approved",
    "ai_session": "ai_session",
    "consent_granted": "consent_granted",
    "consent_revoked": "consent_revoked",
}


def map_timeline_event_type(source_type: str) -> str:
    """Best-effort map a source event_type into the FE timeline enum."""
    key = (source_type or "").lower()
    if key in _TIMELINE_TYPE_MAP:
        return _TIMELINE_TYPE_MAP[key]
    # Prefix/substring heuristics for unknowns.
    if "lab" in key:
        return "lab_uploaded"
    if "care_plan" in key:
        return "care_plan_created"
    if "consent" in key:
        return "consent_granted"
    if "ai" in key or "session" in key:
        return "ai_session"
    return "metric_logged"


# ---------------------------------------------------------------------------
# 5. Review dispatch
# ---------------------------------------------------------------------------


def parse_item_id(item_id: str) -> tuple[str, str]:
    """Split the composite queue id into (item_type, underlying_uuid).

    Raises NotFound on a malformed / unknown item_type.
    """
    if ":" not in item_id:
        raise NotFound(f"Malformed queue item id '{item_id}'.")
    prefix, _, uuid = item_id.partition(":")
    if prefix not in (_ITEM_TYPE_LAB, _ITEM_TYPE_AI, _ITEM_TYPE_CARE) or not uuid:
        raise NotFound(f"Unknown queue item type in '{item_id}'.")
    return prefix, uuid


def _item_patient_id(db: Session, item_type: str, uuid: str) -> str | None:
    """Resolve the underlying item's patient_id, or None if missing/soft-deleted.

    Used to server-side scope-gate ``review_item`` BEFORE any domain dispatch, so
    a doctor cannot review an item for a patient outside their visible population
    by crafting a composite id.
    """
    if item_type == _ITEM_TYPE_AI:
        row = db.get(AIClinicalRecommendation, uuid)
    elif item_type == _ITEM_TYPE_CARE:
        row = db.get(CarePlan, uuid)
    elif item_type == _ITEM_TYPE_LAB:
        row = db.get(LabResult, uuid)
    else:
        return None
    if row is None or getattr(row, "deleted_at", None) is not None:
        return None
    return row.patient_id


def _record_decision(
    db: Session,
    *,
    item_type: str,
    item_id: str,
    patient_id: str,
    doctor_id: str,
    decision: str,
    comment: str | None,
    internal_note: str | None,
) -> None:
    """Persist the reviewer's (potentially-PHI) comment + internal_note, encrypted.

    Kept OUT of AuditLog (which is contractually PHI-free); the domain action's
    PHI-free audit trail is recorded separately by each ``_review_*`` path.
    """
    db.add(
        DoctorReviewDecision(
            item_type=item_type,
            item_id=item_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            decision=decision,
            comment=comment,
            internal_note=internal_note,
        )
    )
    db.flush()


def review_item(
    db: Session,
    *,
    item_id: str,
    doctor_user_id: str,
    decision: str,
    comment: str,
    internal_note: str | None = None,
) -> dict:
    """Dispatch a review decision to the correct domain, return updated QueueItem dict."""
    item_type, uuid = parse_item_id(item_id)
    doctor = _get_doctor(db, doctor_user_id)
    if doctor is None:
        raise PermissionDenied("User is not registered as a doctor.")

    # Server-side scope gate: resolve the item's patient and confirm the doctor is
    # related (consent OR encounter) BEFORE any domain action runs. A generic
    # message is used so the error leaks NO patient name / PHI / summary.
    patient_id = _item_patient_id(db, item_type, uuid)
    if patient_id is None:
        raise NotFound(f"Queue item '{item_id}' not found.")
    if patient_id not in _visible_patient_ids(db, doctor):
        raise PermissionDenied("Not permitted to review this item.")

    doctor_user = db.get(User, doctor.user_id) if doctor.user_id else None

    if item_type == _ITEM_TYPE_AI:
        return _review_ai(db, uuid, doctor, doctor_user, decision, comment, internal_note)
    if item_type == _ITEM_TYPE_CARE:
        return _review_care_plan(db, uuid, doctor, decision, comment, internal_note)
    if item_type == _ITEM_TYPE_LAB:
        return _review_lab(db, uuid, doctor, decision, comment, internal_note)
    raise NotFound(f"Unknown queue item type '{item_type}'.")


_DECISION_TO_AI_ACTION = {
    "approved": "accept",
    "rejected": "reject",
    "request_info": "request_info",
}


def _review_ai(
    db: Session,
    rec_id: str,
    doctor: Doctor,
    doctor_user: User | None,
    decision: str,
    comment: str,
    internal_note: str | None = None,
) -> dict:
    if doctor_user is None:
        raise PermissionDenied("Doctor user account not found.")
    rec = db.get(AIClinicalRecommendation, rec_id)
    if rec is None or rec.deleted_at is not None:
        raise NotFound(f"AI recommendation {rec_id} not found.")
    patient_id = rec.patient_id
    action = _DECISION_TO_AI_ACTION[decision]
    try:
        DoctorReviewService(db).review(
            recommendation_id=rec_id,
            action=action,  # type: ignore[arg-type]
            doctor=doctor_user,
            notes=comment,
        )
    except ValueError as exc:
        # "not in pending_review status" -> invalid transition (409)
        raise InvalidTransition(str(exc)) from exc
    db.flush()
    _record_decision(
        db,
        item_type=_ITEM_TYPE_AI,
        item_id=rec_id,
        patient_id=patient_id,
        doctor_id=doctor.id,
        decision=decision,
        comment=comment,
        internal_note=internal_note,
    )
    updated = db.get(AIClinicalRecommendation, rec_id)
    return _rec_to_queue_item(db, updated)


def _review_care_plan(
    db: Session,
    plan_id: str,
    doctor: Doctor,
    decision: str,
    comment: str,
    internal_note: str | None = None,
) -> dict:
    plan = db.get(CarePlan, plan_id)
    if plan is None or plan.deleted_at is not None:
        raise NotFound(f"Care plan {plan_id} not found.")
    if plan.status != CarePlanStatus.PENDING_REVIEW:
        raise InvalidTransition(
            f"Care plan {plan_id} is not in PENDING_REVIEW (is {plan.status})."
        )
    patient_id = plan.patient_id

    if decision == "approved":
        try:
            DoctorCarePlanService(db).approve(care_plan_id=plan_id, doctor=doctor)
        except ValueError as exc:
            raise InvalidTransition(str(exc)) from exc
    else:
        # reject / request_info: care_plan has no reject service — transition via
        # direct SQL UPDATE (same pattern the approve path uses to bypass the C2
        # ORM validator) and audit consistently.
        new_status = (
            CarePlanStatus.REJECTED if decision == "rejected" else CarePlanStatus.PENDING_REVIEW
        )
        db.execute(
            update(CarePlan).where(CarePlan.id == plan_id).values(status=new_status)
        )
        db.flush()
        audit.record(
            db,
            actor_type="doctor",
            actor_id=doctor.user_id,
            action=f"care_plan.{decision}",
            resource_type="care_plan",
            resource_id=plan_id,
            outcome="success",
            severity="info",
        )

    _record_decision(
        db,
        item_type=_ITEM_TYPE_CARE,
        item_id=plan_id,
        patient_id=patient_id,
        doctor_id=doctor.id,
        decision=decision,
        comment=comment,
        internal_note=internal_note,
    )
    updated = db.get(CarePlan, plan_id)
    return _care_plan_to_queue_item(db, updated)


def _review_lab(
    db: Session,
    lab_id: str,
    doctor: Doctor,
    decision: str,
    comment: str,
    internal_note: str | None = None,
) -> dict:
    row = db.get(LabResult, lab_id)
    if row is None or row.deleted_at is not None:
        raise NotFound(f"Lab result {lab_id} not found.")
    if row.verified_by_doctor:
        raise InvalidTransition(f"Lab result {lab_id} has already been reviewed.")
    patient_id = row.patient_id

    # Both approve/reject mark the lab as doctor-reviewed; a rejected/request_info
    # lab records the outcome in the audit trail (there is no lab reject column).
    db.execute(
        update(LabResult).where(LabResult.id == lab_id).values(verified_by_doctor=True)
    )
    db.flush()
    audit.record(
        db,
        actor_type="doctor",
        actor_id=doctor.user_id,
        action=f"lab_result.{decision}",
        resource_type="lab_result",
        resource_id=lab_id,
        outcome="success",
        severity="info",
    )
    _record_decision(
        db,
        item_type=_ITEM_TYPE_LAB,
        item_id=lab_id,
        patient_id=patient_id,
        doctor_id=doctor.id,
        decision=decision,
        comment=comment,
        internal_note=internal_note,
    )
    updated = db.get(LabResult, lab_id)
    return _lab_to_queue_item(db, updated, decision)


# ---------------------------------------------------------------------------
# Single-item re-mappers (post-review response)
# ---------------------------------------------------------------------------


def _one_patient_name(db: Session, patient_id: str) -> str | None:
    profile = db.get(PatientProfile, patient_id)
    return profile.full_name if profile is not None else None


def _rec_to_queue_item(db: Session, rec: AIClinicalRecommendation) -> dict:
    return {
        "id": f"{_ITEM_TYPE_AI}:{rec.id}",
        "patient_id": rec.patient_id,
        "patient_name": _one_patient_name(db, rec.patient_id),
        "item_type": _ITEM_TYPE_AI,
        "priority": _rec_priority(rec),
        "status": _map_rec_status(rec.status),
        "summary": _rec_summary(rec),
        "submitted_at": _iso(rec.created_at) or _iso(utcnow()),
        "assigned_doctor_id": rec.reviewed_by_doctor_id,
    }


def _care_plan_to_queue_item(db: Session, plan: CarePlan) -> dict:
    return {
        "id": f"{_ITEM_TYPE_CARE}:{plan.id}",
        "patient_id": plan.patient_id,
        "patient_name": _one_patient_name(db, plan.patient_id),
        "item_type": _ITEM_TYPE_CARE,
        "priority": "normal",
        "status": _map_care_plan_status(plan.status),
        "summary": plan.title,
        "submitted_at": _iso(plan.created_at) or _iso(utcnow()),
        "assigned_doctor_id": plan.approved_by_doctor_id,
    }


def _lab_to_queue_item(db: Session, row: LabResult, decision: str) -> dict:
    status = {"approved": "approved", "rejected": "rejected", "request_info": "request_info"}[
        decision
    ]
    return {
        "id": f"{_ITEM_TYPE_LAB}:{row.id}",
        "patient_id": row.patient_id,
        "patient_name": _one_patient_name(db, row.patient_id),
        "item_type": _ITEM_TYPE_LAB,
        "priority": _lab_priority(row),
        "status": status,
        "summary": _lab_summary(row),
        "submitted_at": _iso(row.created_at) or _iso(utcnow()),
        "assigned_doctor_id": None,
    }
