"""Idempotent pilot-journey seed for the 4 Android pilot journeys.

Provisions exactly the prerequisites the mobile pilot needs — one email patient,
one verified marketplace doctor, and the confirmed/needs-review data each journey
drives — then is safe to re-run and to reset.

JOURNEYS PROVISIONED
--------------------
A. Document OCR review      → a MedicalDocument in ``needs_review`` with 2
   ExtractionCandidates (1 medication, 1 lab) the tester confirms in-app; a
   placeholder fixture image is written to ``.pilot-secrets/fixtures/`` so the
   review→confirm→canonical→timeline flow runs without a live camera.
B. Medication reminders     → an active confirmed Medication + a fixed_daily
   MedicationSchedule + a guaranteed DUE dose occurrence (reminders screen shows
   it immediately).
C. Meto on confirmed data   → MetoConsent with ``ai_processing`` + ``health_records``
   GRANTED (current policy version); ``medications``/``documents`` left ungranted
   so grant/revoke can be exercised. Plus verified HealthMetric + LabResult rows
   so confirmed-data answers have content.
D. Doctor marketplace       → a VERIFIED, active Doctor (User role=DOCTOR) with a
   consultation fee + future availability slots so browse→book→mock-pay works.

IDEMPOTENCY
-----------
Every concern is a get-or-create keyed on a stable natural key (email, medication
name, consent category, document sha256, extraction_run_id, candidate dedupe_key,
availability slot start). Re-running produces no duplicate rows. The single
"guaranteed-due" dose and future availability slots use a delete-then-recreate
(replace) pattern so re-running keeps them fresh without accumulating.

SAFETY
------
* Refuses to run when MCP_ENV/ENV=production unless ALLOW_DEMO_SEED=true.
* All data is synthetic — NO real PHI. NO admin account is created.
* Credentials come only from env (PILOT_PATIENT_EMAIL / PILOT_PATIENT_PASSWORD,
  PILOT_DOCTOR_EMAIL / PILOT_DOCTOR_PASSWORD) or the gitignored
  ``backend/.pilot-secrets/`` — never committed, never printed.

USAGE
-----
    python scripts/seed_pilot_journeys.py            # seed (idempotent)
    python scripts/seed_pilot_journeys.py --reset    # remove pilot patient+doctor
"""

from __future__ import annotations

import datetime as dt
import os
import secrets
import string
import struct
import sys
import zlib
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.consent_policy import (  # noqa: E402
    CATEGORY_AI_PROCESSING,
    CATEGORY_DOCUMENTS,
    CATEGORY_HEALTH_RECORDS,
    CONSENT_POLICY_VERSION,
)
from app.core.clock import utcnow  # noqa: E402
from app.core.database import SessionLocal, create_all  # noqa: E402
from app.core.password import validate_password_policy  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.availability import DoctorAvailability  # noqa: E402
from app.models.care import Doctor  # noqa: E402
from app.models.clinical import (  # noqa: E402
    HealthMetric,
    LabResult,
    Medication,
    MedicationAdherence,
    MedicationAuditLog,
    MedicationStatement,
)
from app.models.consultation import (  # noqa: E402
    Consultation,
    ConsultationAccessGrant,
    ConsultationNote,
    ConsultationPayment,
    ConsultationReview,
    DoctorVerificationStatus,
)
from app.models.medical_document import (  # noqa: E402
    CAND_STATUS_NEEDS_REVIEW,
    CANDIDATE_LAB_RESULT,
    CANDIDATE_MEDICATION,
    DOC_STATUS_NEEDS_REVIEW,
    OBJECT_STATE_ACCEPTED,
    DocumentExtraction,
    ExtractionCandidate,
    MedicalDocument,
)
from app.models.medication_schedule import (  # noqa: E402
    DOSE_PENDING,
    SCHED_STATUS_ACTIVE,
    SCHEDULE_FIXED_DAILY,
    DoseOccurrence,
    MedicationSchedule,
)
from app.models.meto import MetoConsent  # noqa: E402
from app.models.patient import PatientProfile  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services import auth  # noqa: E402
from app.services import medication as medication_svc  # noqa: E402
from app.services import medication_schedule as schedule_svc  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration (all synthetic, .test domain — never a real mailbox)
# ---------------------------------------------------------------------------
DEFAULT_PATIENT_EMAIL = "pilot.patient@metocare.test"
DEFAULT_DOCTOR_EMAIL = "pilot.doctor@metocare.test"
PATIENT_TZ = "Asia/Ho_Chi_Minh"

SECRETS_DIR = Path(__file__).resolve().parents[1] / ".pilot-secrets"
FIXTURES_DIR = SECRETS_DIR / "fixtures"
PATIENT_CREDS = SECRETS_DIR / "pilot_patient.creds"
DOCTOR_CREDS = SECRETS_DIR / "pilot_doctor.creds"
FIXTURE_IMAGE = FIXTURES_DIR / "prescription_fixture.png"

# Stable natural keys used for get-or-create + reset scoping.
PILOT_MED_NAME = "Metformin"
PILOT_METRIC_SOURCE = "seed_pilot"
PILOT_DOC_SHA256 = sha256(b"metocare-pilot-prescription-fixture").hexdigest()
PILOT_EXTRACTION_RUN_ID = "pilot-fixture-extraction-0001"
PILOT_DUE_MARKER = "PILOT_DUE_NOW"  # local_render marker for the guaranteed dose


# ---------------------------------------------------------------------------
# Guards & credential helpers
# ---------------------------------------------------------------------------
def _check_not_production() -> None:
    """Refuse to run against production unless ALLOW_DEMO_SEED=true."""
    env = (os.environ.get("MCP_ENV") or os.environ.get("ENV") or "").strip().lower()
    allow = os.environ.get("ALLOW_DEMO_SEED", "").strip().lower()
    if env == "production" and allow != "true":
        raise RuntimeError(
            "SAFETY: seed_pilot_journeys.py refused to run against production.\n"
            "Set ALLOW_DEMO_SEED=true only if you truly intend to seed a "
            "production-like environment with synthetic pilot data."
        )


def _generate_password() -> str:
    """Generate a strong password (>=12 chars, guaranteed letter + digit)."""
    alphabet = string.ascii_letters + string.digits
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(16))
        if any(c.isalpha() for c in candidate) and any(c.isdigit() for c in candidate):
            return candidate


def _write_creds(path: Path, email: str, password: str) -> None:
    """Write ``email\\npassword`` to a gitignored creds file (0600)."""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{email}\n{password}\n", encoding="utf-8")
    path.chmod(0o600)


def _resolve_credentials(
    *, email_env: str, password_env: str, default_email: str, creds_path: Path
) -> tuple[str, str | None]:
    """Return (email, password_or_none).

    Password is taken from env when set (always known → creds re-written), else
    generated ONLY on first creation. On a re-run without env vars we cannot know
    an already-created account's password, so we return None and keep the existing
    creds file untouched.
    """
    email = (os.environ.get(email_env) or default_email).strip().lower()
    password = os.environ.get(password_env)
    return email, (password.strip() if password else None)


def _make_placeholder_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Build a minimal valid solid-color PNG with no external deps.

    Gives the tester a real (if plain) image to pick from device storage for the
    Journey-A OCR flow — the extraction candidates are pre-seeded, so pixel
    content is irrelevant.
    """

    def _chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    r, g, b = rgb
    raw = b"".join(b"\x00" + bytes([r, g, b]) * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# Journey shell: patient + doctor accounts
# ---------------------------------------------------------------------------
def _get_or_create_patient(db, email: str, password: str | None) -> tuple[User, bool]:
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        return existing, False
    if password is None:
        password = _generate_password()
        _write_creds(PATIENT_CREDS, email, password)
    else:
        _write_creds(PATIENT_CREDS, email, password)
    # register() commits internally and creates the PatientProfile.
    user = auth.register(
        db,
        email=email,
        password=password,
        full_name="Bệnh nhân Thử nghiệm",
        role=UserRole.PATIENT,
    )
    return user, True


def _patient_profile(db, user: User) -> PatientProfile:
    return db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    ).scalar_one()


def _get_or_create_doctor(db, email: str, password: str | None) -> tuple[User, Doctor, bool]:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None:
        doctor = db.execute(
            select(Doctor).where(Doctor.user_id == user.id)
        ).scalar_one_or_none()
        return user, doctor, False

    if password is None:
        password = _generate_password()
    _write_creds(DOCTOR_CREDS, email, password)
    validate_password_policy(password)
    # Created directly via models (no admin account, no admin-only service path).
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name="BS. Thử nghiệm",
        role=UserRole.DOCTOR,
        is_active=True,
        mfa_enabled=False,
    )
    db.add(user)
    db.flush()
    doctor = Doctor(
        user_id=user.id,
        full_name="BS. Thử nghiệm",
        specialty="Nội tiết",
        bio="Bác sĩ nội tiết cho môi trường thử nghiệm pilot.",
        years_experience=10,
        languages="vi,en",
        hospital_name="Phòng khám Thử nghiệm",
        consultation_methods="chat",
    )
    db.add(doctor)
    db.flush()
    return user, doctor, True


def _ensure_doctor_marketplace_ready(db, doctor: Doctor) -> None:
    """Journey D prereqs: VERIFIED + active + a consultation fee (price snapshot)."""
    doctor.verification_status = DoctorVerificationStatus.VERIFIED
    doctor.is_verified = True
    doctor.is_active = True
    if not doctor.consultation_fee:
        doctor.consultation_fee = 150000.0  # VND — snapshotted onto each consultation
    if not doctor.specialty:
        doctor.specialty = "Nội tiết"
    if not doctor.consultation_methods:
        doctor.consultation_methods = "chat"
    db.add(doctor)
    db.flush()


def _ensure_availability(db, doctor: Doctor, *, days: int = 5) -> int:
    """Replace future un-booked slots with a fresh set (one 09:00–09:30 slot/day).

    DoctorAvailability.doctor_id references users.id (not doctors.id). Booked slots
    are preserved; only future un-booked slots are refreshed so re-running keeps
    the schedule current without piling up rows.
    """
    if not doctor.user_id:
        return 0
    now_naive = utcnow()  # DoctorAvailability stores naive UTC
    db.execute(
        delete(DoctorAvailability).where(
            DoctorAvailability.doctor_id == doctor.user_id,
            DoctorAvailability.is_booked.is_(False),
            DoctorAvailability.slot_start >= now_naive,
        )
    )
    created = 0
    base = now_naive.date()
    for offset in range(1, days + 1):
        start = dt.datetime.combine(base + dt.timedelta(days=offset), dt.time(9, 0))
        db.add(
            DoctorAvailability(
                doctor_id=doctor.user_id,
                slot_start=start,
                slot_end=start + dt.timedelta(minutes=30),
                is_booked=False,
            )
        )
        created += 1
    db.flush()
    return created


# ---------------------------------------------------------------------------
# Journey B: confirmed medication + schedule + guaranteed-due dose
# ---------------------------------------------------------------------------
def _get_or_create_medication(db, patient_id: str) -> Medication:
    # Resilient to pre-existing duplicates from earlier seed runs: take the
    # oldest matching row rather than asserting exactly one, so a re-run never
    # aborts on MultipleResultsFound.
    existing = db.execute(
        select(Medication)
        .where(
            Medication.patient_id == patient_id,
            Medication.name == PILOT_MED_NAME,
            Medication.deleted_at.is_(None),
        )
        .order_by(Medication.created_at)
    ).scalars().first()
    if existing is not None:
        return existing
    return medication_svc.add_medication(
        db,
        patient_id=patient_id,
        data={
            "name": PILOT_MED_NAME,
            "dose": "500mg",
            "frequency": "2 lần/ngày (sáng và tối)",
            "note": "Dữ liệu pilot — uống sau ăn.",
        },
        actor_role="seed_script",
        source_type="patient_manual",
        commit=False,
    )


def _get_or_create_schedule(db, *, patient_id: str, medication_id: str) -> MedicationSchedule:
    existing = db.execute(
        select(MedicationSchedule)
        .where(
            MedicationSchedule.medication_id == medication_id,
            MedicationSchedule.patient_id == patient_id,
            MedicationSchedule.status == SCHED_STATUS_ACTIVE,
            MedicationSchedule.superseded_by.is_(None),
        )
        .order_by(MedicationSchedule.created_at)
    ).scalars().first()
    if existing is not None:
        return existing
    return schedule_svc.create_schedule(
        db,
        patient_id=patient_id,
        medication_id=medication_id,
        schedule_type=SCHEDULE_FIXED_DAILY,
        local_dose_times=["08:00", "20:00"],
        patient_timezone=PATIENT_TZ,
        source="manual",
    )


def _ensure_due_dose(db, schedule: MedicationSchedule) -> None:
    """Guarantee exactly one fresh DUE dose (replace pattern, marker local_render).

    ``materialize_due`` only creates doses from ~now forward, and any real dose
    turns MISSED 4h after its time — so for a reliable demo we also keep one dose
    scheduled a few minutes in the past, refreshed on every seed run.
    """
    db.execute(
        delete(DoseOccurrence).where(
            DoseOccurrence.schedule_id == schedule.id,
            DoseOccurrence.local_render == PILOT_DUE_MARKER,
        )
    )
    scheduled = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
    key = sha256(f"{schedule.id}|{PILOT_DUE_MARKER}".encode()).hexdigest()
    db.add(
        DoseOccurrence(
            schedule_id=schedule.id,
            patient_id=schedule.patient_id,
            scheduled_utc=scheduled,
            local_render=PILOT_DUE_MARKER,
            state=DOSE_PENDING,
            idempotency_key=key,
            source_schedule_version=schedule.version,
        )
    )
    db.flush()


# ---------------------------------------------------------------------------
# Journey C: consent + confirmed clinical data
# ---------------------------------------------------------------------------
def _grant_consent(db, user_id: str, category: str) -> None:
    """Upsert a GRANTED consent row at the current policy version (idempotent)."""
    row = db.execute(
        select(MetoConsent).where(
            MetoConsent.user_id == user_id,
            MetoConsent.context_type == category,
        )
    ).scalar_one_or_none()
    now = utcnow()
    if row is None:
        db.add(
            MetoConsent(
                user_id=user_id,
                context_type=category,
                granted=True,
                granted_at=now,
                revoked_at=None,
                policy_version=CONSENT_POLICY_VERSION,
            )
        )
    else:
        row.granted = True
        row.granted_at = row.granted_at or now
        row.revoked_at = None
        row.policy_version = CONSENT_POLICY_VERSION
    db.flush()


def _seed_confirmed_clinical(db, patient_id: str) -> tuple[int, int]:
    """A couple of verified HealthMetric + LabResult rows for confirmed-data Meto."""
    metrics = 0
    have_metric = db.execute(
        select(HealthMetric.id).where(
            HealthMetric.patient_id == patient_id,
            HealthMetric.source == PILOT_METRIC_SOURCE,
        ).limit(1)
    ).scalar_one_or_none()
    if have_metric is None:
        now = utcnow()
        metric_rows = [
            ("fasting_glucose", "mg/dL", 118.0, 70.0, 99.0, "high", 3),
            ("hba1c", "%", 6.4, 0.0, 5.7, "high", 3),
            ("blood_pressure_systolic", "mmHg", 128.0, 90.0, 130.0, "normal", 1),
        ]
        for mtype, unit, value, nmin, nmax, mstatus, days_ago in metric_rows:
            db.add(
                HealthMetric(
                    patient_id=patient_id,
                    metric_type=mtype,
                    value=value,
                    unit=unit,
                    measured_at=now - dt.timedelta(days=days_ago),
                    source=PILOT_METRIC_SOURCE,
                    normal_range_min=nmin,
                    normal_range_max=nmax,
                    status=mstatus,
                )
            )
            metrics += 1

    labs = 0
    lab_rows = [
        ("Glucose đói (FBG)", "fasting_glucose", 118.0, "mg/dL", "70-99", "high"),
        ("HbA1c", "hba1c", 6.4, "%", "<5.7", "high"),
    ]
    test_date = utcnow().date() - dt.timedelta(days=7)
    for test_name, canonical, value, unit, ref, lstatus in lab_rows:
        exists = db.execute(
            select(LabResult.id).where(
                LabResult.patient_id == patient_id,
                LabResult.test_name == test_name,
            ).limit(1)
        ).scalar_one_or_none()
        if exists is not None:
            continue
        db.add(
            LabResult(
                patient_id=patient_id,
                test_name=test_name,
                canonical_name=canonical,
                value=value,
                unit=unit,
                reference_range=ref,
                status=lstatus,
                test_date=test_date,
                ocr_confidence=1.0,
                verified_by_user=True,
                verified_by_doctor=False,
            )
        )
        labs += 1
    db.flush()
    return metrics, labs


# ---------------------------------------------------------------------------
# Journey A: needs-review OCR document + candidates + fixture image
# ---------------------------------------------------------------------------
def _get_or_create_ocr_fixture(db, patient_id: str) -> tuple[MedicalDocument, int]:
    """A needs_review MedicalDocument with a medication + lab ExtractionCandidate.

    Canonical targets on in-app confirm:
      * medication candidate → new canonical Medication (statement-first,
        source_type=ocr_confirmed) via MedicationPromoter.
      * lab candidate → canonical LabResult (+ HealthMetric trend) via LabPromoter.
    """
    doc = db.execute(
        select(MedicalDocument).where(
            MedicalDocument.patient_id == patient_id,
            MedicalDocument.sha256 == PILOT_DOC_SHA256,
            MedicalDocument.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if doc is None:
        doc = MedicalDocument(
            patient_id=patient_id,
            sha256=PILOT_DOC_SHA256,
            quarantine_key=f"pilot/quarantine/{PILOT_DOC_SHA256}.png",
            accepted_key=f"pilot/accepted/{PILOT_DOC_SHA256}.png",
            mime="image/png",
            size_bytes=len(_make_placeholder_png(1, 1, (255, 255, 255))),
            doc_type="prescription",
            classification_confidence=0.95,
            page_count=1,
            source="mobile_upload",
            status=DOC_STATUS_NEEDS_REVIEW,
            object_state=OBJECT_STATE_ACCEPTED,
            scan_status="clean",
        )
        db.add(doc)
        db.flush()

    extraction = db.execute(
        select(DocumentExtraction).where(
            DocumentExtraction.document_id == doc.id,
            DocumentExtraction.extraction_run_id == PILOT_EXTRACTION_RUN_ID,
        )
    ).scalar_one_or_none()
    if extraction is None:
        extraction = DocumentExtraction(
            document_id=doc.id,
            schema_version="mdi-1",
            provider="mock",
            model="pilot-seed",
            extraction_run_id=PILOT_EXTRACTION_RUN_ID,
            review_state="pending",
        )
        db.add(extraction)
        db.flush()

    candidates = [
        (
            CANDIDATE_MEDICATION,
            0,
            "med:amlodipine",
            {
                "name": "Amlodipine",
                "strength": "5mg",
                "form": "viên",
                "frequency": "1 lần/ngày",
                "instructions": "Uống buổi sáng",
                "route": "uống",
            },
        ),
        (
            CANDIDATE_LAB_RESULT,
            1,
            "lab:ldl_cholesterol",
            {
                "test_name": "LDL Cholesterol",
                "canonical": "ldl_cholesterol",
                "value": 148.0,
                "unit": "mg/dL",
                "reference_range": "<100",
            },
        ),
    ]
    created = 0
    for ctype, ordinal, dedupe_key, fields in candidates:
        exists = db.execute(
            select(ExtractionCandidate.id).where(
                ExtractionCandidate.extraction_id == extraction.id,
                ExtractionCandidate.dedupe_key == dedupe_key,
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue
        db.add(
            ExtractionCandidate(
                extraction_id=extraction.id,
                document_id=doc.id,
                patient_id=patient_id,
                candidate_type=ctype,
                ordinal=ordinal,
                fields_json=fields,
                dedupe_key=dedupe_key,
                status=CAND_STATUS_NEEDS_REVIEW,
            )
        )
        created += 1
    db.flush()

    # Write the pickable fixture image (idempotent overwrite).
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURE_IMAGE.write_bytes(_make_placeholder_png(600, 400, (240, 244, 248)))
    return doc, created


# ---------------------------------------------------------------------------
# Seed orchestration
# ---------------------------------------------------------------------------
def seed(db) -> dict:
    _check_not_production()
    summary: dict = {}

    patient_email, patient_pw = _resolve_credentials(
        email_env="PILOT_PATIENT_EMAIL",
        password_env="PILOT_PATIENT_PASSWORD",
        default_email=DEFAULT_PATIENT_EMAIL,
        creds_path=PATIENT_CREDS,
    )
    doctor_email, doctor_pw = _resolve_credentials(
        email_env="PILOT_DOCTOR_EMAIL",
        password_env="PILOT_DOCTOR_PASSWORD",
        default_email=DEFAULT_DOCTOR_EMAIL,
        creds_path=DOCTOR_CREDS,
    )

    # --- Patient shell (register() commits itself) ---
    patient, p_created = _get_or_create_patient(db, patient_email, patient_pw)
    profile = _patient_profile(db, patient)
    summary["patient_email"] = patient_email
    summary["patient_created"] = p_created

    # --- Journey C: consent ---
    _grant_consent(db, patient.id, CATEGORY_AI_PROCESSING)
    _grant_consent(db, patient.id, CATEGORY_HEALTH_RECORDS)
    # PRIV-F1 made the whole medical-document pipeline fail-closed on the
    # `documents` category, so without this grant the seeded patient cannot run
    # Journey A at all (every upload/review call 403s). Granting it here keeps
    # the QA journeys runnable; a real patient still grants it themselves.
    _grant_consent(db, patient.id, CATEGORY_DOCUMENTS)
    summary["consent_granted"] = [
        CATEGORY_AI_PROCESSING,
        CATEGORY_HEALTH_RECORDS,
        CATEGORY_DOCUMENTS,
    ]

    # --- Journey C: confirmed clinical data ---
    metrics, labs = _seed_confirmed_clinical(db, profile.id)
    summary["metrics_added"] = metrics
    summary["labs_added"] = labs

    # --- Journey B: medication + schedule + due dose ---
    med = _get_or_create_medication(db, profile.id)
    schedule = _get_or_create_schedule(db, patient_id=profile.id, medication_id=med.id)
    schedule_svc.materialize_due(db, schedule)  # real future doses (sanctioned path)
    _ensure_due_dose(db, schedule)  # guaranteed fresh DUE dose for the demo
    summary["medication"] = med.name
    summary["schedule_id"] = schedule.id

    # --- Journey A: needs-review OCR fixture ---
    doc, cand_created = _get_or_create_ocr_fixture(db, profile.id)
    summary["ocr_document_id"] = doc.id
    summary["ocr_candidates_added"] = cand_created

    db.commit()

    # --- Journey D: doctor (own transaction after patient commit) ---
    doctor_user, doctor, d_created = _get_or_create_doctor(db, doctor_email, doctor_pw)
    _ensure_doctor_marketplace_ready(db, doctor)
    slots = _ensure_availability(db, doctor)
    db.commit()
    summary["doctor_email"] = doctor_email
    summary["doctor_id"] = doctor.id
    summary["doctor_created"] = d_created
    summary["availability_slots"] = slots
    summary["consultation_fee"] = doctor.consultation_fee

    return summary


# ---------------------------------------------------------------------------
# Reset — self-scoped removal of the pilot patient + doctor + their data
# ---------------------------------------------------------------------------
def _delete_patient_scoped(db, patient_user: User) -> None:
    profile = db.execute(
        select(PatientProfile).where(PatientProfile.user_id == patient_user.id)
    ).scalar_one_or_none()
    if profile is not None:
        pid = profile.id
        doc_ids = list(
            db.execute(
                select(MedicalDocument.id).where(MedicalDocument.patient_id == pid)
            ).scalars()
        )
        cons_ids = list(
            db.execute(
                select(Consultation.id).where(Consultation.patient_id == pid)
            ).scalars()
        )
        db.execute(delete(DoseOccurrence).where(DoseOccurrence.patient_id == pid))
        db.execute(delete(MedicationSchedule).where(MedicationSchedule.patient_id == pid))
        db.execute(delete(MedicationAdherence).where(MedicationAdherence.patient_id == pid))
        db.execute(delete(MedicationAuditLog).where(MedicationAuditLog.patient_id == pid))
        db.execute(delete(MedicationStatement).where(MedicationStatement.patient_id == pid))
        db.execute(delete(Medication).where(Medication.patient_id == pid))
        db.execute(delete(ExtractionCandidate).where(ExtractionCandidate.patient_id == pid))
        if doc_ids:
            db.execute(
                delete(DocumentExtraction).where(DocumentExtraction.document_id.in_(doc_ids))
            )
        db.execute(delete(MedicalDocument).where(MedicalDocument.patient_id == pid))
        db.execute(delete(HealthMetric).where(HealthMetric.patient_id == pid))
        db.execute(delete(LabResult).where(LabResult.patient_id == pid))
        _delete_consultations(db, cons_ids)
        db.execute(delete(Consultation).where(Consultation.patient_id == pid))
        db.execute(delete(PatientProfile).where(PatientProfile.id == pid))
    db.execute(delete(MetoConsent).where(MetoConsent.user_id == patient_user.id))
    db.execute(delete(User).where(User.id == patient_user.id))


def _delete_consultations(db, cons_ids: list[str]) -> None:
    if not cons_ids:
        return
    db.execute(
        delete(ConsultationPayment).where(ConsultationPayment.consultation_id.in_(cons_ids))
    )
    db.execute(
        delete(ConsultationAccessGrant).where(
            ConsultationAccessGrant.consultation_id.in_(cons_ids)
        )
    )
    db.execute(delete(ConsultationNote).where(ConsultationNote.consultation_id.in_(cons_ids)))
    db.execute(
        delete(ConsultationReview).where(ConsultationReview.consultation_id.in_(cons_ids))
    )


def _delete_doctor_scoped(db, doctor_user: User) -> None:
    doctor = db.execute(
        select(Doctor).where(Doctor.user_id == doctor_user.id)
    ).scalar_one_or_none()
    if doctor is not None:
        cons_ids = list(
            db.execute(
                select(Consultation.id).where(Consultation.doctor_id == doctor.id)
            ).scalars()
        )
        _delete_consultations(db, cons_ids)
        db.execute(delete(Consultation).where(Consultation.doctor_id == doctor.id))
        db.execute(delete(Doctor).where(Doctor.id == doctor.id))
    db.execute(delete(DoctorAvailability).where(DoctorAvailability.doctor_id == doctor_user.id))
    db.execute(delete(User).where(User.id == doctor_user.id))


def reset(db) -> dict:
    _check_not_production()
    result = {"patient_removed": False, "doctor_removed": False}

    patient_email = (os.environ.get("PILOT_PATIENT_EMAIL") or DEFAULT_PATIENT_EMAIL).lower()
    doctor_email = (os.environ.get("PILOT_DOCTOR_EMAIL") or DEFAULT_DOCTOR_EMAIL).lower()

    patient_user = db.execute(
        select(User).where(User.email == patient_email, User.role == UserRole.PATIENT)
    ).scalar_one_or_none()
    if patient_user is not None:
        _delete_patient_scoped(db, patient_user)
        result["patient_removed"] = True

    doctor_user = db.execute(
        select(User).where(User.email == doctor_email, User.role == UserRole.DOCTOR)
    ).scalar_one_or_none()
    if doctor_user is not None:
        _delete_doctor_scoped(db, doctor_user)
        result["doctor_removed"] = True

    db.commit()
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_seed(summary: dict) -> None:
    print("\n── Pilot Journeys Seed Complete ─────────────────────────")
    print(f"  Patient   : {summary['patient_email']} "
          f"({'created' if summary['patient_created'] else 'existing'})")
    print(f"  Doctor    : {summary['doctor_email']} "
          f"({'created' if summary['doctor_created'] else 'existing'})")
    print("  Journey A : OCR doc "
          f"{summary['ocr_document_id']} (+{summary['ocr_candidates_added']} candidates)")
    print(f"  Journey B : {summary['medication']} schedule={summary['schedule_id']} "
          "(1 guaranteed DUE dose)")
    print(f"  Journey C : consent {summary['consent_granted']}; "
          f"+{summary['metrics_added']} metrics, +{summary['labs_added']} labs")
    print(f"  Journey D : verified doctor fee={summary['consultation_fee']} VND, "
          f"{summary['availability_slots']} slots")
    print("  Passwords : written to backend/.pilot-secrets/ (never printed)")
    print("─────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    create_all()
    is_reset = "--reset" in sys.argv[1:]
    with SessionLocal() as session:
        if is_reset:
            out = reset(session)
            print(f"\nPilot reset: patient_removed={out['patient_removed']} "
                  f"doctor_removed={out['doctor_removed']}\n")
        else:
            _print_seed(seed(session))
