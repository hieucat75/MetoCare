"""Admin patient management service (Admin — Patient Records Management).

Provides listing (search/filter/pagination), detail aggregation, and status
updates for the admin-only patient records module.

``PatientProfile.full_name`` / ``phone`` / ``dob`` are Fernet-encrypted
(non-deterministic — see ``app.core.crypto``), so they cannot be filtered,
searched, or sorted at the SQL level. Filters that map to plaintext columns
(gender, account status, created_at range, has-labs/meds/consent) are applied
in SQL to shrink the candidate set; free-text search, age-group filtering,
and name/last-activity sorting are then applied in Python after the ORM has
transparently decrypted each row. ``_CANDIDATE_LIMIT`` bounds this in-memory
pass — see module TODO below for the scaling path.

TODO(export): No CSV/XLSX export infra exists anywhere in this backend yet.
Building it is out of scope here; the frontend disables the export action
with an explanatory tooltip instead of faking success.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models.care import Clinic, Doctor
from app.models.clinical import LabResult, Medication
from app.models.consent import TermsConsent
from app.models.consultation import Consultation
from app.models.governance import AuditLog
from app.models.patient import PatientProfile
from app.models.user import User
from app.services import admin_users

# Safety cap on the in-memory decrypt+filter+sort pass. Comfortably above the
# current patient base; if the platform grows past this, the fix is a blind
# index column for full_name/phone (see app.core.crypto.blind_index) rather
# than raising this constant.
_CANDIDATE_LIMIT = 5000


def age_from_dob(dob: str | None) -> int | None:
    if not dob:
        return None
    try:
        birth = dt.date.fromisoformat(dob[:10])
    except ValueError:
        return None
    today = dt.date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def _birth_year_from_dob(dob: str | None) -> int | None:
    if not dob:
        return None
    try:
        return dt.date.fromisoformat(dob[:10]).year
    except ValueError:
        return None


def _age_group(age: int | None) -> str | None:
    if age is None:
        return None
    if age < 18:
        return "under_18"
    if age <= 34:
        return "18_34"
    if age <= 54:
        return "35_54"
    if age <= 69:
        return "55_69"
    return "70_plus"


def _naive(value: dt.datetime | None) -> dt.datetime:
    """Normalize to a naive datetime for cross-backend sort comparisons.

    SQLite frequently returns naive datetimes even for ``DateTime(timezone=True)``
    columns; comparing a naive and an aware datetime raises TypeError.
    """
    if value is None:
        return dt.datetime.min
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _candidate_query(
    *,
    is_active: bool | None,
    gender: str | None,
    created_from: dt.date | None,
    created_to: dt.date | None,
    has_labs: bool | None,
    has_meds: bool | None,
    has_consent: bool | None,
):
    stmt = select(PatientProfile, User).join(User, PatientProfile.user_id == User.id)

    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if gender:
        stmt = stmt.where(PatientProfile.gender == gender)
    if created_from is not None:
        stmt = stmt.where(PatientProfile.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(PatientProfile.created_at < created_to + dt.timedelta(days=1))

    if has_labs is not None:
        labs_exists = exists(
            select(LabResult.id).where(
                LabResult.patient_id == PatientProfile.id, LabResult.deleted_at.is_(None)
            )
        )
        stmt = stmt.where(labs_exists if has_labs else ~labs_exists)

    if has_meds is not None:
        meds_exists = exists(
            select(Medication.id).where(
                Medication.patient_id == PatientProfile.id, Medication.deleted_at.is_(None),
                Medication.lifecycle_status != "entered_in_error"
            )
        )
        stmt = stmt.where(meds_exists if has_meds else ~meds_exists)

    if has_consent is not None:
        consent_exists = exists(
            select(TermsConsent.id).where(
                TermsConsent.user_id == User.id, TermsConsent.revoked_at.is_(None)
            )
        )
        stmt = stmt.where(consent_exists if has_consent else ~consent_exists)

    return stmt.order_by(PatientProfile.created_at.desc()).limit(_CANDIDATE_LIMIT)


def _counts_for(
    db: Session, patient_ids: list[str]
) -> tuple[dict[str, int], dict[str, int], set[str]]:
    if not patient_ids:
        return {}, {}, set()

    lab_rows = db.execute(
        select(LabResult.patient_id, func.count())
        .where(LabResult.patient_id.in_(patient_ids), LabResult.deleted_at.is_(None))
        .group_by(LabResult.patient_id)
    ).all()
    lab_counts = dict(lab_rows)

    med_rows = db.execute(
        select(Medication.patient_id, func.count())
        .where(Medication.patient_id.in_(patient_ids), Medication.deleted_at.is_(None),
                Medication.lifecycle_status != "entered_in_error")
        .group_by(Medication.patient_id)
    ).all()
    med_counts = dict(med_rows)

    flag_rows = db.execute(
        select(LabResult.patient_id)
        .where(
            LabResult.patient_id.in_(patient_ids),
            LabResult.deleted_at.is_(None),
            LabResult.data_quality_flag == "flag",
        )
        .distinct()
    ).all()
    flagged = {pid for (pid,) in flag_rows}

    return lab_counts, med_counts, flagged


def _consent_status_for(db: Session, user_ids: list[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(TermsConsent.user_id, TermsConsent.revoked_at)
        .where(TermsConsent.user_id.in_(user_ids))
        .order_by(TermsConsent.accepted_at.desc())
    ).all()
    status: dict[str, str] = {}
    for uid, revoked_at in rows:
        if uid in status:
            continue  # newest row per user wins (query is ordered desc)
        status[uid] = "revoked" if revoked_at is not None else "valid"
    for uid in user_ids:
        status.setdefault(uid, "none")
    return status


def _last_activity_for(db: Session, resource_ids: list[str]) -> dict[str, dt.datetime]:
    """Best-effort last-activity timestamp: most recent audited access to this
    patient (by resource_id). Patient logins are not currently audited, so this
    is often None for patients with no admin/doctor interaction — callers must
    treat None as "no recorded activity", not "never active".
    """
    if not resource_ids:
        return {}
    rows = db.execute(
        select(AuditLog.resource_id, func.max(AuditLog.timestamp))
        .where(AuditLog.resource_id.in_(resource_ids))
        .group_by(AuditLog.resource_id)
    ).all()
    return {rid: ts for rid, ts in rows if rid is not None}


def _build_list_item(
    profile: PatientProfile,
    user: User,
    *,
    lab_counts: dict[str, int],
    med_counts: dict[str, int],
    flagged: set[str],
    consent_status: dict[str, str],
    last_activity: dict[str, dt.datetime],
) -> dict:
    return {
        "id": profile.id,
        "user_id": user.id,
        "full_name": profile.full_name,
        "phone": profile.phone or user.phone,
        "gender": profile.gender,
        "birth_year": _birth_year_from_dob(profile.dob),
        "age": age_from_dob(profile.dob),
        "is_active": user.is_active,
        "lab_result_count": lab_counts.get(profile.id, 0),
        "medication_count": med_counts.get(profile.id, 0),
        "has_data_quality_flag": profile.id in flagged,
        "consent_status": consent_status.get(user.id, "none"),
        "created_at": profile.created_at,
        "last_activity_at": last_activity.get(profile.id) or last_activity.get(user.id),
    }


def list_patients(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    is_active: bool | None = None,
    gender: str | None = None,
    has_labs: bool | None = None,
    has_meds: bool | None = None,
    has_consent: bool | None = None,
    created_from: dt.date | None = None,
    created_to: dt.date | None = None,
    age_group: str | None = None,
    sort: str = "created_at_desc",
) -> tuple[list[dict], int]:
    """Return (page_of_enriched_patient_dicts, total_matching_count).

    NOTE: results are bounded by ``_CANDIDATE_LIMIT`` (see module docstring) —
    do not use this to look up a single known patient by id after a mutation;
    use ``get_patient_list_item`` instead, which is not subject to that cap.
    """
    rows = list(
        db.execute(
            _candidate_query(
                is_active=is_active,
                gender=gender,
                created_from=created_from,
                created_to=created_to,
                has_labs=has_labs,
                has_meds=has_meds,
                has_consent=has_consent,
            )
        ).all()
    )

    patient_ids = [p.id for p, _ in rows]
    user_ids = [u.id for _, u in rows]
    lab_counts, med_counts, flagged = _counts_for(db, patient_ids)
    consent_status = _consent_status_for(db, user_ids)
    last_activity = _last_activity_for(db, patient_ids + user_ids)

    q = (search or "").strip().lower()
    enriched: list[dict] = []
    for profile, user in rows:
        age = age_from_dob(profile.dob)
        if age_group and _age_group(age) != age_group:
            continue
        if q:
            haystack = " ".join(
                filter(
                    None,
                    [profile.full_name, profile.phone, user.email, profile.id, user.id],
                )
            ).lower()
            if q not in haystack:
                continue
        enriched.append(
            _build_list_item(
                profile,
                user,
                lab_counts=lab_counts,
                med_counts=med_counts,
                flagged=flagged,
                consent_status=consent_status,
                last_activity=last_activity,
            )
        )

    reverse = sort.endswith("_desc")
    key_name = sort.removesuffix("_desc").removesuffix("_asc")
    sort_key_fns = {
        "created_at": lambda r: _naive(r["created_at"]),
        "full_name": lambda r: (r["full_name"] or "").lower(),
        "last_active": lambda r: _naive(r["last_activity_at"]),
    }
    sort_key_fn = sort_key_fns.get(key_name, sort_key_fns["created_at"])
    enriched.sort(key=sort_key_fn, reverse=reverse)

    total = len(enriched)
    page = enriched[skip : skip + limit]
    return page, total


def get_patient(db: Session, patient_id: str) -> tuple[PatientProfile, User] | None:
    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        return None
    user = db.get(User, profile.user_id)
    if user is None:
        return None
    return profile, user


def get_patient_list_item(db: Session, patient_id: str) -> dict | None:
    """Build a single list-item dict for one known patient by id.

    Unlike ``list_patients``, this looks the patient up directly by primary
    key and is NOT subject to ``_CANDIDATE_LIMIT`` — safe to call right after
    a mutation (e.g. status update) where the patient must always be found
    regardless of the candidate window's created_at ordering/size.
    """
    found = get_patient(db, patient_id)
    if found is None:
        return None
    profile, user = found
    lab_counts, med_counts, flagged = _counts_for(db, [profile.id])
    consent_status = _consent_status_for(db, [user.id])
    last_activity = _last_activity_for(db, [profile.id, user.id])
    return _build_list_item(
        profile,
        user,
        lab_counts=lab_counts,
        med_counts=med_counts,
        flagged=flagged,
        consent_status=consent_status,
        last_activity=last_activity,
    )


def get_patient_consultations(db: Session, patient_id: str, limit: int = 10) -> list[dict]:
    stmt = (
        select(Consultation, Doctor, Clinic)
        .join(Doctor, Consultation.doctor_id == Doctor.id)
        .outerjoin(Clinic, Doctor.clinic_id == Clinic.id)
        .where(Consultation.patient_id == patient_id, Consultation.deleted_at.is_(None))
        .order_by(Consultation.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "id": c.id,
            "doctor_id": d.id,
            "doctor_name": d.full_name,
            "clinic_name": clinic.name if clinic else None,
            "status": c.status,
            "created_at": c.created_at,
        }
        for c, d, clinic in rows
    ]


def get_patient_consent(db: Session, user_id: str) -> TermsConsent | None:
    stmt = (
        select(TermsConsent)
        .where(TermsConsent.user_id == user_id)
        .order_by(TermsConsent.accepted_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def get_patient_audit_log(
    db: Session, *, patient_id: str, user_id: str, limit: int = 20
) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.resource_id.in_([patient_id, user_id]))
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


def update_patient_status(
    db: Session, *, patient_id: str, is_active: bool, requester_id: str
) -> tuple[PatientProfile, User]:
    """Activate/deactivate the account behind *patient_id*.

    Raises:
        ValueError: patient not found.
        PermissionError: propagated from admin_users guards (self/SUPER_ADMIN).
    """
    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        raise ValueError(f"Patient {patient_id} not found")
    if is_active:
        user = admin_users.activate_user(db, user_id=profile.user_id)
    else:
        user = admin_users.deactivate_user(db, user_id=profile.user_id, requester_id=requester_id)
    return profile, user
