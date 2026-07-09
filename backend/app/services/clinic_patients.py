"""Clinic patient management service (Clinic SaaS C1 M06).

Builds the entire consumer surface for `ClinicPatientRelationship` (schema
already existed from C0, unwired until now). `PatientProfile` stays the
single global identity — this module never adds a clinic dimension to it,
only reads/writes the clinic-scoped relationship + shell-account creation for
walk-in patients (M06_IMPLEMENTATION_PLAN.md §1-2).

Phone-exact-match dedup (BR-M06-02 priority-1 check) queries `User.phone`
directly in SQL — it is a plaintext, unique, normalized (+84…) column, unlike
`PatientProfile`'s Fernet-encrypted fields (which cannot be filtered/sorted
in SQL; the roster free-text search below reuses `admin_patients.py`'s
candidate-query + in-Python-decrypt-filter-paginate pattern for those).
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.phone import normalize_vn_phone
from app.core.security import hash_password
from app.models.clinic import ClinicPatientRelationship, ClinicPatientRelationshipStatus
from app.models.patient import PatientProfile
from app.models.user import User, UserRole
from app.services import audit

# Safety cap on the in-memory decrypt+filter+sort pass, same discipline as
# admin_patients.py's _CANDIDATE_LIMIT (BR-M06-06: roster must always
# paginate, never return the full dataset).
_ROSTER_CANDIDATE_LIMIT = 5000
_VALID_STATUSES = frozenset(
    {
        ClinicPatientRelationshipStatus.ACTIVE,
        ClinicPatientRelationshipStatus.INACTIVE,
        ClinicPatientRelationshipStatus.MERGED,
    }
)


class ClinicPatientError(ValueError):
    """Domain error for invalid patient-linking state. Routes translate this
    to a controlled 400 — never a raw 500, same pattern as `ClinicServiceError`."""


class ClinicPatientDuplicateError(ClinicPatientError):
    """Raised when a create-new-patient call finds a phone-exact-match
    candidate and the caller did not supply `override_dedup_reason`
    (AC-M06-02). Carries the candidate so the route can surface it (409)."""

    def __init__(self, candidate: dict) -> None:
        super().__init__("Đã tìm thấy hồ sơ nghi trùng theo số điện thoại.")
        self.candidate = candidate


def _profile_fields(profile: PatientProfile, user: User) -> dict:
    return {
        "full_name": profile.full_name or user.full_name,
        "dob": profile.dob,
        "gender": profile.gender,
        "address": profile.address,
        "phone": profile.phone or user.phone,
    }


def find_by_phone(db: Session, phone_normalized: str) -> tuple[PatientProfile, User] | None:
    row = db.execute(
        select(PatientProfile, User)
        .join(User, PatientProfile.user_id == User.id)
        .where(User.phone == phone_normalized)
    ).first()
    return (row[0], row[1]) if row else None


def _own_clinic_relationship(
    db: Session, *, clinic_id: str, patient_id: str
) -> ClinicPatientRelationship | None:
    return db.execute(
        select(ClinicPatientRelationship).where(
            ClinicPatientRelationship.clinic_id == clinic_id,
            ClinicPatientRelationship.patient_id == patient_id,
        )
    ).scalar_one_or_none()


def search_candidate(db: Session, *, clinic_id: str, phone: str) -> dict | None:
    """Exact-phone-match dedup helper (BR-M06-02 priority-1 check). No
    partial/fuzzy search exposed here — deliberately, to avoid becoming a
    patient-enumeration oracle (M06 plan §5)."""
    normalized = normalize_vn_phone(phone)
    if normalized is None:
        raise ClinicPatientError("Số điện thoại không hợp lệ.")
    found = find_by_phone(db, normalized)
    if found is None:
        return None
    profile, user = found
    already_linked = (
        _own_clinic_relationship(db, clinic_id=clinic_id, patient_id=profile.id) is not None
    )
    fields = _profile_fields(profile, user)
    return {
        "patient_id": profile.id,
        "full_name": fields["full_name"],
        "dob": fields["dob"],
        "phone": fields["phone"],
        "already_linked": already_linked,
    }


def _generate_patient_code(db: Session, *, clinic_id: str) -> str:
    total = db.execute(
        select(ClinicPatientRelationship).where(ClinicPatientRelationship.clinic_id == clinic_id)
    ).scalars()
    count = len(list(total))
    return f"BN-{count + 1:05d}"


def _insert_relationship(
    db: Session,
    *,
    clinic_id: str,
    patient_id: str,
    actor_id: str,
    patient_code: str | None,
    audit_action: str,
) -> ClinicPatientRelationship:
    """Single insert attempt — the DB's unique constraints
    (`uq_clinic_patient_rel_clinic_code` / `_clinic_patient`) are the real
    concurrency guarantee (same class of "check-then-insert race" as M05's
    `create_service`). A retry-after-rollback loop is deliberately NOT used
    here: `create_patient` may have already flushed a new `User` +
    `PatientProfile` earlier in this same transaction, and `db.rollback()`
    would discard those too, not just this insert — so any IntegrityError
    here is terminal for the whole request. The caller (route) must catch
    the resulting `ClinicPatientError` and respond WITHOUT calling
    `db.commit()`, exactly like every other Clinic SaaS write path."""
    code = patient_code or _generate_patient_code(db, clinic_id=clinic_id)
    relationship = ClinicPatientRelationship(
        patient_id=patient_id,
        clinic_id=clinic_id,
        patient_code=code,
        status=ClinicPatientRelationshipStatus.ACTIVE,
    )
    db.add(relationship)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ClinicPatientError(
            "Không thể liên kết bệnh nhân — mã bệnh nhân bị trùng hoặc bệnh nhân đã được"
            " liên kết với phòng khám này (xung đột đồng thời)."
        ) from exc
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action=audit_action,
        resource_type="clinic_patient_relationship",
        resource_id=relationship.id,
        clinic_id=clinic_id,
    )
    return relationship


def link_patient(
    db: Session,
    *,
    clinic_id: str,
    actor_id: str,
    patient_id: str,
    phone: str,
    patient_code: str | None = None,
) -> ClinicPatientRelationship:
    """Link requires the caller to also supply the patient's phone (the same
    exact-match value `search_candidate` returned) — a bare `patient_id`
    alone is never sufficient proof of legitimate contact. Codex review
    finding (P0): without this, any clinic with write access to `/link`
    could link — and thereby gain full administrative PHI visibility
    (name/dob/address/phone) on — any patient whose UUID they learned from
    anywhere (a leaked id, another system's URL, cross-clinic staff access),
    entirely bypassing the phone-based dedup/consent design this milestone
    is built around."""
    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        raise ClinicPatientError("Không tìm thấy bệnh nhân.")
    normalized_phone = normalize_vn_phone(phone)
    if normalized_phone is None:
        raise ClinicPatientError("Số điện thoại không hợp lệ.")
    user = db.get(User, profile.user_id)
    if user is None:
        raise ClinicPatientError("Không tìm thấy bệnh nhân.")
    # Match either User.phone (the common case — login identity) or
    # PatientProfile.phone (the shared-number override-create path, where
    # User.phone is deliberately left unset — see create_patient).
    if normalized_phone not in (user.phone, profile.phone):
        raise ClinicPatientError("Số điện thoại không khớp với hồ sơ bệnh nhân này.")
    return _insert_relationship(
        db,
        clinic_id=clinic_id,
        patient_id=patient_id,
        actor_id=actor_id,
        patient_code=patient_code,
        audit_action="clinic_patient_link",
    )


def create_patient(
    db: Session,
    *,
    clinic_id: str,
    actor_id: str,
    full_name: str,
    phone: str,
    dob: str,
    gender: str,
    address: str | None = None,
    patient_code: str | None = None,
    override_dedup_reason: str | None = None,
) -> ClinicPatientRelationship:
    normalized_phone = normalize_vn_phone(phone)
    if normalized_phone is None:
        raise ClinicPatientError("Số điện thoại không hợp lệ.")

    existing = find_by_phone(db, normalized_phone)
    if existing is not None and not (override_dedup_reason or "").strip():
        profile, user = existing
        fields = _profile_fields(profile, user)
        raise ClinicPatientDuplicateError(
            {
                "patient_id": profile.id,
                "full_name": fields["full_name"],
                "dob": fields["dob"],
                "phone": fields["phone"],
                "already_linked": (
                    _own_clinic_relationship(db, clinic_id=clinic_id, patient_id=profile.id)
                    is not None
                ),
            }
        )

    # Shell account: a walk-in patient created administratively has no
    # MetoCare login yet (AC-M06-01's <60s / 4-minimal-field flow has no
    # password field). The random password is never returned or logged —
    # activation-by-invite (US-M06-06) is a separate, out-of-scope milestone.
    #
    # `User.phone` is genuinely unique (one login identity per phone number);
    # `existing is not None` here only happens via the override path (BRD
    # §6.8 "hai bệnh nhân dùng chung SĐT" — e.g. spouses sharing one number).
    # Two distinct people can share a contact number but cannot share a login
    # identity, so the new shell User gets no phone in that case — the
    # number is still recorded on `PatientProfile.phone` (display/contact
    # only, not unique) via `_profile_fields`'s `profile.phone or user.phone`
    # fallback convention.
    user = User(
        phone=None if existing is not None else normalized_phone,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        full_name=full_name,
        role=UserRole.PATIENT,
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ClinicPatientError("Số điện thoại đã được đăng ký (xung đột đồng thời).") from exc

    profile = PatientProfile(
        user_id=user.id,
        full_name=full_name,
        dob=dob,
        gender=gender,
        address=address,
        phone=normalized_phone if existing is not None else None,
    )
    db.add(profile)
    db.flush()

    return _insert_relationship(
        db,
        clinic_id=clinic_id,
        patient_id=profile.id,
        actor_id=actor_id,
        patient_code=patient_code,
        audit_action="clinic_patient_create",
    )


def get_own_clinic_relationship(
    db: Session, *, clinic_id: str, patient_id: str
) -> ClinicPatientRelationship | None:
    return _own_clinic_relationship(db, clinic_id=clinic_id, patient_id=patient_id)


def get_profile_fields(db: Session, *, patient_id: str) -> dict | None:
    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        return None
    user = db.get(User, profile.user_id)
    if user is None:
        return None
    return _profile_fields(profile, user)


def _candidate_query(*, clinic_id: str):
    return (
        select(ClinicPatientRelationship, PatientProfile, User)
        .join(PatientProfile, ClinicPatientRelationship.patient_id == PatientProfile.id)
        .join(User, PatientProfile.user_id == User.id)
        .where(ClinicPatientRelationship.clinic_id == clinic_id)
        .order_by(ClinicPatientRelationship.created_at.desc())
        .limit(_ROSTER_CANDIDATE_LIMIT)
    )


def get_roster(
    db: Session, *, clinic_id: str, search: str | None = None, skip: int = 0, limit: int = 50
) -> tuple[list[dict], int]:
    rows = list(db.execute(_candidate_query(clinic_id=clinic_id)).all())

    q = (search or "").strip().lower()
    enriched: list[dict] = []
    for relationship, profile, user in rows:
        fields = _profile_fields(profile, user)
        if q:
            haystack = " ".join(
                filter(None, [fields["full_name"], fields["phone"], relationship.patient_code])
            ).lower()
            if q not in haystack:
                continue
        enriched.append(
            {
                "id": relationship.id,
                "patient_id": profile.id,
                "clinic_id": clinic_id,
                "patient_code": relationship.patient_code,
                "status": relationship.status,
                "internal_notes": relationship.internal_notes,
                "first_seen_at": relationship.first_seen_at,
                "created_at": relationship.created_at,
                "updated_at": relationship.updated_at,
                **fields,
            }
        )

    total = len(enriched)
    page = enriched[skip : skip + limit]
    return page, total


def update_relationship(
    db: Session,
    *,
    relationship: ClinicPatientRelationship,
    actor_id: str,
    status: str | None = None,
    internal_notes: str | None = None,
) -> ClinicPatientRelationship:
    old_status = relationship.status
    changed_status = status is not None and status != old_status
    if status is not None:
        if status not in _VALID_STATUSES:
            raise ClinicPatientError(f"Trạng thái không hợp lệ: {status}.")
        relationship.status = status
    if internal_notes is not None:
        relationship.internal_notes = internal_notes
    db.flush()
    audit.record(
        db,
        actor_type="user",
        actor_id=actor_id,
        action="clinic_patient_update",
        resource_type="clinic_patient_relationship",
        resource_id=relationship.id,
        clinic_id=relationship.clinic_id,
        details=(
            {"old_status": old_status, "new_status": relationship.status}
            if changed_status
            else None
        ),
    )
    return relationship
