"""Patient summary service — aggregates pre-visit data for the doctor portal (T22).

Assembles a consolidated view of a patient's recent clinical data in one
query-efficient pass.  No HTTP concerns; RBAC and consent checks are performed
by the caller (route) before invoking ``build_summary``.

Data aggregated:
  - Latest 5 health metrics (vitals) + directional trend
  - Last 3 lab documents (status metadata only, no PHI content)
  - Most recent metabolic/risk score + trend
  - Active medications (not soft-deleted)
  - Last 5 symptom logs
  - Last 3 nutrition logs
  - Next 2 upcoming booking appointments with this doctor
  - Active care plans (count + titles)
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.domain import consultation_consent_policy as policy
from app.models.appointment import BookingAppointment  # noqa: F401 — for type clarity
from app.models.appointment import BookingAppointment as _BookingAppt
from app.models.care import CarePlan
from app.models.clinical import (
    HealthMetric,
    LabDocument,
    Medication,
    RiskScore,
    SymptomLog,
)
from app.models.nutrition import NutritionLog
from app.schemas.patient import (
    MetabolicScoreSummary,
    PatientSummaryOut,
    VitalsSummary,
)
from app.utils.number_format import format_lab_display, format_lab_value

# Re-export output schemas used by the schemas layer
__all__ = ["build_summary"]

# HealthMetric.source value written by the lab→metric promoter
# (``app.services.lab._promote_row``). Only rows carrying it are lab-derived.
_LAB_SOURCE = "lab_result"

# Explicit "this caller is not governed by consultation consent" marker. Spelled
# out at the call site so an unfiltered full-record read is always a visible,
# deliberate choice rather than an omitted argument.
UNRESTRICTED: frozenset[str] | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_vitals(
    db: Session,
    patient_id: str,
    *,
    allow_self_reported: bool = True,
    allow_lab: bool = True,
) -> VitalsSummary:
    """Return the 5 most-recent permitted HealthMetric rows + a directional trend.

    ``source == 'lab_result'`` marks a metric promoted from a lab report, which
    belongs to the lab_results consent category; everything else (self-reported,
    device, manual entry) belongs to health_records. Filtering happens in SQL so
    an ungranted provenance is never loaded, and the "5 most recent" window is
    computed over the permitted rows only — otherwise a patient who shared just
    one category would see the other category's rows silently eat their slots
    and get an emptier summary than they consented to.
    """
    if not allow_self_reported and not allow_lab:
        return VitalsSummary(latest=[], trend="insufficient_data")

    stmt = select(HealthMetric).where(
        HealthMetric.patient_id == patient_id,
        HealthMetric.deleted_at.is_(None),
    )
    if allow_lab and not allow_self_reported:
        stmt = stmt.where(HealthMetric.source == _LAB_SOURCE)
    elif allow_self_reported and not allow_lab:
        # NULL source is legacy/self-entered data, so it must survive this
        # branch — `!=` alone would drop it, since NULL != 'lab_result' is NULL.
        stmt = stmt.where(
            (HealthMetric.source.is_(None)) | (HealthMetric.source != _LAB_SOURCE)
        )

    rows = list(
        db.execute(stmt.order_by(HealthMetric.measured_at.desc()).limit(5)).scalars()
    )

    # A trend computed over a censored subset is not a trend, it is a claim the
    # data does not support. If the patient shared only one provenance, the
    # excluded readings could point the other way — a confident "improving" over
    # five home glucose readings, while the withheld lab HbA1c is worsening, is
    # exactly the false reassurance this must not manufacture. Report the rows,
    # refuse the direction.
    is_partial = not (allow_self_reported and allow_lab)
    trend = "insufficient_data" if is_partial else _compute_vitals_trend(rows)
    latest = [_vital_row(r) for r in rows]
    return VitalsSummary(latest=latest, trend=trend)


def _resolve_metric_semantics(r: HealthMetric) -> dict | None:
    """Fresh clinical semantics for one doctor-summary vital row.

    Mirrors `MetricOut._populate_clinical_message`'s calling pattern: ALWAYS
    resolves fresh from `r.value`/`r.unit` via `lab_semantics.resolve_lab_semantics`
    rather than trusting `r.status`, which can silently disagree with what the
    same value would classify as today (issues #153/#154). `reclassify` only
    walks lab_results, so a promoted HealthMetric could otherwise keep a stale
    severity forever — this is the DOCTOR-facing consult summary, so it must
    not assert a severity the patient screens already refuse to make.

    `HealthMetric` has no `normalized_value_si`/`normalized_unit_si` columns —
    `value`/`unit` ARE the canonical pair (same call shape `MetricOut` uses).

    Returns `None` when `resolve_lab_semantics` itself returns `None`
    (metric_type outside the canonical registry — e.g. non-lab vitals like
    blood pressure); the caller keeps the existing raw-status fallback then.
    """
    from app.domain.lab_semantics import resolve_lab_semantics

    try:
        semantics = resolve_lab_semantics(
            r.metric_type,
            r.value,
            r.unit,
            # Same confirmed source-report provenance MetricOut resolves —
            # see HealthMetric.source_reference_text. Without this, the
            # doctor summary always fell back to CANONICAL_FALLBACK even
            # when the patient screens correctly showed SOURCE_REPORT for
            # the identical row.
            printed_reference_text=r.source_reference_text,
            printed_reference_unit=r.original_unit,
        )
    except Exception:  # noqa: BLE001 — summary building must never raise; fail CLOSED
        return {
            "status": "unknown",
            "severity": "unknown",
            "needs_review": True,
            "clinical_message": None,
            "display_name": None,
            "reference_display": None,
            "reference_source": None,
        }

    if semantics is None:
        return None

    return {
        "status": semantics.status,
        "severity": semantics.severity,
        "needs_review": semantics.needs_review,
        "clinical_message": semantics.clinical_message,
        "display_name": semantics.display_name,
        "reference_display": semantics.reference_display,
        "reference_source": semantics.reference_source,
    }


def _vital_row(r: HealthMetric) -> dict:
    """Serialize a vital for the doctor summary showing the ORIGINAL value+unit.

    P0 clinical-integrity: doctors must see the value in the unit as recorded
    (e.g. 88 µmol/L), never the canonical/SI-converted number. Falls back to
    value/unit when original_* is NULL (legacy rows).
    """
    orig_value = r.original_value if r.original_value is not None else r.value
    orig_unit = r.original_unit if r.original_unit is not None else r.unit
    semantics = _resolve_metric_semantics(r)
    row: dict = {
        "id": r.id,
        "metric_type": r.metric_type,
        "value": format_lab_value(orig_value, orig_unit),
        "unit": orig_unit,
        "display": format_lab_display(orig_value, orig_unit),
        "measured_at": r.measured_at.isoformat() if r.measured_at else None,
        # Fresh-resolved status (never the possibly-stale stored column) for
        # canonical lab-biomarker metric_types; falls back to the stored
        # column only for non-lab vitals resolve_lab_semantics doesn't cover.
        "status": (semantics["status"] if semantics else r.status),
        # Provenance is clinically load-bearing: a lab-drawn value and a
        # home-device reading of the same analyte carry different weight, and
        # after category filtering the doctor cannot otherwise tell which they
        # are looking at.
        "source": r.source,
    }
    if semantics is not None:
        row["severity"] = semantics["severity"]
        row["needs_review"] = semantics["needs_review"]
        if semantics["clinical_message"]:
            row["clinical_message"] = semantics["clinical_message"]
        if semantics["display_name"]:
            row["display_name"] = semantics["display_name"]
        if semantics["reference_display"]:
            row["reference_display"] = semantics["reference_display"]
        if semantics["reference_source"]:
            row["reference_source"] = semantics["reference_source"]
    return row


def _compute_vitals_trend(rows: list[HealthMetric]) -> str:
    """Simple trend: compare the mean value of the most-recent 2 vs next 2.

    Returns one of: improving | stable | worsening | insufficient_data.
    """
    if len(rows) < 2:
        return "insufficient_data"

    # Use the first metric type as a proxy (they may differ, so flag insufficient)
    types = {r.metric_type for r in rows}
    if len(types) > 1:
        # Multiple metric types — cannot compare values directly
        return "insufficient_data"

    last = rows[0].value
    previous = rows[1].value
    if previous == 0:
        return "insufficient_data"

    delta_pct = (last - previous) / abs(previous) * 100
    if delta_pct > 5:
        return "worsening"
    if delta_pct < -5:
        return "improving"
    return "stable"


def _fetch_lab_documents(db: Session, patient_id: str) -> list[dict]:
    """Return the 3 most-recent LabDocument rows (status metadata only)."""
    rows = list(
        db.execute(
            select(LabDocument)
            .where(LabDocument.patient_id == patient_id)
            .order_by(LabDocument.created_at.desc())
            .limit(3)
        ).scalars()
    )
    return [
        {
            "id": r.id,
            "ocr_status": r.ocr_status,
            "status": r.status,
            "lab_name": r.lab_name,
            "file_type": r.file_type,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _fetch_confirmed_medical_documents(db: Session, patient_id: str) -> list[dict]:
    """Return the 5 most-recent CONFIRMED medical documents (metadata only).

    Only ``confirmed``/``partially_confirmed`` documents appear, because the
    patient-facing label for this category promises "tài liệu y tế đã được bạn
    xác nhận". A document still in review is a machine's unverified reading, and
    the candidate values behind it are never touched here — this returns type,
    status and dates, nothing extracted.
    """
    from app.models.medical_document import (
        DOC_STATUS_CONFIRMED,
        DOC_STATUS_PARTIALLY_CONFIRMED,
        MedicalDocument,
    )

    rows = list(
        db.execute(
            select(MedicalDocument)
            .where(
                MedicalDocument.patient_id == patient_id,
                MedicalDocument.deleted_at.is_(None),
                MedicalDocument.status.in_(
                    (DOC_STATUS_CONFIRMED, DOC_STATUS_PARTIALLY_CONFIRMED)
                ),
            )
            .order_by(MedicalDocument.created_at.desc())
            .limit(5)
        ).scalars()
    )
    return [
        {
            "id": r.id,
            "doc_type": r.doc_type,
            "status": r.status,
            "page_count": r.page_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _fetch_metabolic_score(db: Session, patient_id: str) -> MetabolicScoreSummary:
    """Return the latest RiskScore + trend from the two most-recent rows."""
    rows = list(
        db.execute(
            select(RiskScore)
            .where(RiskScore.patient_id == patient_id)
            .order_by(RiskScore.created_at.desc())
            .limit(2)
        ).scalars()
    )
    if not rows:
        return MetabolicScoreSummary()

    latest_row = rows[0]
    trend = "insufficient_data"
    if len(rows) >= 2:
        delta = latest_row.metabolic_score - rows[1].metabolic_score
        if delta > 5:
            trend = "worsening"
        elif delta < -5:
            trend = "improving"
        else:
            trend = "stable"

    return MetabolicScoreSummary(
        latest_score=float(latest_row.metabolic_score),
        trend=trend,
        recorded_at=latest_row.created_at,
    )


def _fetch_medications(db: Session, patient_id: str) -> list[dict]:
    """Return medications for the "Medications (Active)" summary section.

    Strictly ``lifecycle_status='active'`` — the section title promises
    currently-taken drugs, so paused/on_hold/completed/discontinued records
    must not appear here (ADR-11 display rules).
    """
    rows = list(
        db.execute(
            select(Medication)
            .where(
                Medication.patient_id == patient_id,
                Medication.deleted_at.is_(None),
                Medication.lifecycle_status == "active",
            )
            .order_by(Medication.created_at.asc())
        ).scalars()
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "dose": r.dose,
            "note": r.note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _fetch_symptoms(db: Session, patient_id: str) -> list[dict]:
    """Return the 5 most-recent SymptomLog rows."""
    rows = list(
        db.execute(
            select(SymptomLog)
            .where(SymptomLog.patient_id == patient_id)
            .order_by(SymptomLog.reported_at.desc())
            .limit(5)
        ).scalars()
    )
    return [
        {
            "id": r.id,
            "description": r.description,
            "severity": r.severity,
            "reported_at": r.reported_at.isoformat() if r.reported_at else None,
        }
        for r in rows
    ]


def _fetch_nutrition(db: Session, patient_id: str) -> list[dict]:
    """Return the 3 most-recent NutritionLog rows."""
    rows = list(
        db.execute(
            select(NutritionLog)
            .where(NutritionLog.patient_id == patient_id)
            .order_by(NutritionLog.logged_at.desc())
            .limit(3)
        ).scalars()
    )
    return [
        {
            "id": r.id,
            "description": r.description,
            "meal_type": r.meal_type,
            "calories_kcal": r.calories_kcal,
            "logged_at": r.logged_at.isoformat() if r.logged_at else None,
        }
        for r in rows
    ]


def _fetch_upcoming_appointments(
    db: Session,
    patient_id: str,
    doctor_id: str | None,
    now: dt.datetime,
) -> list[dict]:
    """Return the next 2 upcoming booking appointments for this patient.

    If *doctor_id* is provided, filter to that doctor's appointments only.
    Only `pending` and `confirmed` statuses are considered upcoming.
    """
    from app.models.availability import DoctorAvailability

    stmt = (
        select(_BookingAppt, DoctorAvailability.slot_start)
        .join(
            DoctorAvailability,
            _BookingAppt.availability_id == DoctorAvailability.id,
        )
        .where(
            _BookingAppt.patient_id == patient_id,
            _BookingAppt.status.in_(["pending", "confirmed"]),
            DoctorAvailability.slot_start >= now,
        )
        .order_by(DoctorAvailability.slot_start.asc())
        .limit(2)
    )
    if doctor_id is not None:
        stmt = stmt.where(_BookingAppt.doctor_id == doctor_id)

    rows = db.execute(stmt).all()
    result = []
    for appt, slot_start in rows:
        result.append(
            {
                "id": appt.id,
                "doctor_id": appt.doctor_id,
                "status": appt.status,
                "notes": appt.notes,
                "slot_start": slot_start.isoformat() if slot_start else None,
                "created_at": appt.created_at.isoformat() if appt.created_at else None,
            }
        )
    return result


def _fetch_active_care_plans(db: Session, patient_id: str) -> list[dict]:
    """Return titles of active (non-deleted, status=ACTIVE) care plans."""
    rows = list(
        db.execute(
            select(CarePlan)
            .where(
                CarePlan.patient_id == patient_id,
                CarePlan.status == "ACTIVE",
                CarePlan.deleted_at.is_(None),
            )
            .order_by(CarePlan.created_at.desc())
        ).scalars()
    )
    return [{"id": r.id, "title": r.title, "version": r.version} for r in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_summary(
    db: Session,
    *,
    patient_id: str,
    doctor_id: str | None = None,
    allowed_categories: frozenset[str] | None = None,
) -> PatientSummaryOut:
    """Build and return a ``PatientSummaryOut`` for *patient_id*.

    Aggregates in a single function call (no chunking / streaming).
    The caller is responsible for RBAC / consent checks before invoking this.

    Args:
        db:          Active SQLAlchemy session.
        patient_id:  The ``PatientProfile.id`` to summarise.
        doctor_id:   Optional — when provided, scopes upcoming appointments to
                     this doctor only (used for the doctor-facing portal view).
        allowed_categories:
                     Consultation-consent categories the patient granted. An
                     ungranted section is never queried — the data is not read
                     from the database at all, rather than read and then
                     dropped. Pass ``UNRESTRICTED`` (never ``None`` by accident)
                     for callers not governed by consultation consent — the
                     doctor-portal and admin surfaces, which have their own
                     authorisation rules. The sentinel is explicit precisely
                     because the permissive value is the dangerous one: a future
                     caller that forgets this argument should be visible in
                     review, not silently handed the whole record.

    Returns:
        A fully-populated ``PatientSummaryOut`` pydantic model.
    """
    now = utcnow()

    def granted(category: str) -> bool:
        return allowed_categories is None or category in allowed_categories

    may_health = granted(policy.CATEGORY_HEALTH_RECORDS)
    may_labs = granted(policy.CATEGORY_LAB_RESULTS)

    # Vitals are split by provenance: a metric promoted from a lab report is
    # lab data and rides the lab_results grant, while a self-reported or device
    # reading rides health_records. Granting one must not leak the other.
    vitals = _fetch_vitals(db, patient_id, allow_self_reported=may_health, allow_lab=may_labs)
    # Lab reports ride lab_results — they ARE labs, and the doctor-facing card
    # they populate is titled "Kết quả xét nghiệm". Gating them on
    # medical_documents inverted both the patient's label and the doctor's.
    # Documents are deliberately NOT filtered by ocr_status: a doctor needs to
    # know a lab is pending, and hiding it would be the more dangerous default.
    lab_documents = _fetch_lab_documents(db, patient_id) if may_labs else []
    medical_documents = (
        _fetch_confirmed_medical_documents(db, patient_id)
        if granted(policy.CATEGORY_MEDICAL_DOCUMENTS)
        else []
    )
    metabolic_score = (
        _fetch_metabolic_score(db, patient_id) if may_health else MetabolicScoreSummary()
    )
    medications = (
        _fetch_medications(db, patient_id) if granted(policy.CATEGORY_MEDICATIONS) else []
    )
    symptoms = _fetch_symptoms(db, patient_id) if may_health else []
    nutrition = _fetch_nutrition(db, patient_id) if may_health else []
    upcoming_appointments = (
        _fetch_upcoming_appointments(db, patient_id=patient_id, doctor_id=doctor_id, now=now)
        if granted(policy.CATEGORY_PATIENT_PROFILE)
        else []
    )
    active_care_plans = _fetch_active_care_plans(db, patient_id) if may_health else []

    shared = (
        sorted(allowed_categories & policy.CATEGORY_SET)
        if allowed_categories is not None
        else []
    )
    withheld = (
        sorted(policy.CATEGORY_SET - allowed_categories)
        if allowed_categories is not None
        else []
    )

    return PatientSummaryOut(
        patient_id=patient_id,
        generated_at=now,
        vitals=vitals,
        lab_documents=lab_documents,
        medical_documents=medical_documents,
        metabolic_score=metabolic_score,
        medications=medications,
        symptoms=symptoms,
        nutrition=nutrition,
        upcoming_appointments=upcoming_appointments,
        active_care_plans=active_care_plans,
        shared_categories=shared,
        withheld_categories=withheld,
    )
