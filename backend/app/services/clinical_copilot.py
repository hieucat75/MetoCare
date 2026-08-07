"""Meto Clinical Copilot — doctor-facing AI decision-support service.

Doctor-only, decision-SUPPORT (never decision-making): summarizes a patient's
record, flags what needs attention, suggests history-taking questions, and
suggests a counseling direction — every claim cited to a deterministic source,
never a diagnosis/prescription, never a suppressed urgent signal.

Design:
- ``get_summary`` is PURE assembly — no LLM call. Every field traces back to
  ``clinical_insight`` (rules-first, already guardrail-checked) or a direct
  patient_id-keyed query.
- ``get_analysis`` computes ``priority`` (the RiskFlag level) DETERMINISTICALLY
  from ``clinical_insight`` findings; the LLM is used ONLY to phrase the
  narrative fields (``key_issues`` / ``contradictions_or_gaps`` /
  ``differentials_to_exclude``) — it can never change the computed level. Each
  narrative item is a ``CitedClaim``: it is either backed by ≥1 verified
  ``SourceRef`` (``basis="sourced"``) or explicitly marked
  ``basis="needs_confirmation"`` — the LLM can never assert an uncited claim as
  if it were sourced.
- ``get_questions`` / ``get_advice`` make one LLM call each, constrained to a
  strict JSON contract, with every returned string re-validated through
  ``guardrails.check_output`` before it is ever returned.
- ALL FOUR public functions share one deterministic completeness assessor
  (``_assess_completeness``) for ``missing_data`` / ``confidence`` /
  ``confidence_note_vi`` — never touched by the LLM.
- A provider outage never raises a raw exception to the route layer — it is
  translated to ``CopilotUnavailable`` after writing a `.failed` audit row.
- A malformed/non-JSON LLM response never crashes and never leaks raw model
  output. Two distinct outcomes:
    1. The TOP-LEVEL structure is unusable (non-JSON, non-dict, a required key
       missing entirely, or present with the wrong type) → ``CopilotMalformedOutput``
       (route translates to a controlled 422) + a `.malformed` audit row.
    2. The top-level structure parses fine but some individual nested items are
       bad → those items are silently dropped; the request still returns 200
       with a smaller, valid (possibly all-``needs_confirmation``) result.
- AuditLog rows for this feature carry ONLY ids (actor_id, resource_id) —
  never any patient content, per ``app.services.audit``'s append-only,
  no-sensitive-content contract.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.ai.exceptions import ProviderUnavailableError
from app.ai.providers.base import ChatMessage
from app.ai.registry import get_registry
from app.domain import consultation_consent_policy as consent_policy
from app.domain import insight_content as ic
from app.domain.guardrails import check_output
from app.domain.lab_interpreter import _ALIAS_INDEX
from app.domain.policies import DISCLAIMER_VI
from app.models.clinical import HealthMetric, LabResult, LabUploadBatch
from app.models.consultation import Consultation
from app.models.patient import PatientProfile
from app.schemas.clinical_copilot import (
    AbnormalFindingBrief,
    AdviceItem,
    CitedClaim,
    ClinicalAdviceOut,
    ClinicalAnalysisOut,
    ClinicalQuestionsOut,
    ClinicalSummaryOut,
    ConfidenceLevel,
    MedicationBrief,
    MissingDataCategory,
    MissingDataItem,
    RiskFlag,
    RiskLevel,
    SourceRef,
    SuggestedQuestion,
)
from app.services import audit
from app.services.clinical_insight import (
    HealthSummary,
    MetricInsight,
    build_health_summary,
    canonical_metric_key,
    list_insights,
)

logger = logging.getLogger(__name__)

UNAVAILABLE_MESSAGE_VI = "Meto phân tích hồ sơ hiện chưa khả dụng."

_MAX_MEDICATIONS = 10
_MAX_ITEMS = 8
_FALLBACK_LINE_VI = "Chưa thể tạo nội dung chi tiết lúc này. Vui lòng thử lại sau."

# "Needs refresh" window for chronic metabolic monitoring — deliberately distinct
# from app.ai.context.builder's `_LABS_LOOKBACK_DAYS` (90) / `_METRICS_LOOKBACK_DAYS`
# (30): those bound what gets FETCHED into an AI context window, this constant
# answers a different question — "is data we already found too old to trust
# without a refresh?" — so it is not reused/aligned with those.
_STALE_DATA_DAYS = 180

_LEVEL_LABEL_VI: dict[RiskLevel, str] = {
    "normal": "Bình thường",
    "monitor": "Cần theo dõi",
    "see_doctor_soon": "Cần đánh giá sớm",
    "urgent": "Có dấu hiệu cấp cứu",
}

_QUESTION_GROUPS = frozenset(
    {
        "current_symptoms",
        "onset_timing",
        "severity_progression",
        "aggravating_relieving",
        "relevant_history",
        "medication_adherence",
        "warning_signs",
        "lifestyle",
    }
)

_ADVICE_CATEGORIES = frozenset(
    {"explain_patient", "home_monitoring", "when_to_visit", "suggested_tests"}
)

_MISSING_DATA_LABELS_VI: dict[MissingDataCategory, str] = {
    "demographics": "Thiếu thông tin nhân khẩu học cơ bản của bệnh nhân.",
    "symptoms": "Chưa ghi nhận triệu chứng / lý do khám của buổi tư vấn này.",
    "allergies": "Chưa có thông tin về dị ứng (không đồng nghĩa với không dị ứng).",
    "medications": "Chưa có thông tin thuốc đang dùng.",
    "medical_history": "Chưa có thông tin bệnh nền / tiền sử bệnh.",
    "vitals_metrics": "Chưa có chỉ số sinh hiệu / đo lường nào được ghi nhận.",
    "labs": "Chưa có kết quả xét nghiệm nào được ghi nhận.",
    "consultation_context": "Chưa có bối cảnh buổi tư vấn (lý do khám).",
}

# Said instead of the labels above when the category was WITHHELD by the patient
# rather than simply unrecorded. "Chưa có thông tin thuốc" about a patient who
# declined to share their medication list is a false negative a doctor could
# prescribe against; this wording says the data may exist and was not shared.
_WITHHELD_DATA_LABELS_VI: dict[MissingDataCategory, str] = {
    "demographics": (
        "Bệnh nhân chưa chia sẻ thông tin hồ sơ cá nhân cho buổi tư vấn này."
    ),
    "allergies": (
        "Bệnh nhân chưa chia sẻ hồ sơ sức khỏe — KHÔNG đồng nghĩa với không có dị ứng."
    ),
    "medications": (
        "Bệnh nhân chưa chia sẻ danh sách thuốc — KHÔNG đồng nghĩa với không dùng thuốc."
    ),
    "medical_history": (
        "Bệnh nhân chưa chia sẻ hồ sơ sức khỏe — KHÔNG đồng nghĩa với không có bệnh nền."
    ),
    "vitals_metrics": (
        "Bệnh nhân chưa chia sẻ chỉ số sức khỏe — KHÔNG đồng nghĩa với không có dữ liệu."
    ),
    "labs": (
        "Bệnh nhân chưa chia sẻ kết quả xét nghiệm — KHÔNG đồng nghĩa với chưa xét nghiệm."
    ),
}

# Which missing-data categories each consent category is responsible for.
_CONSENT_CATEGORY_TO_MISSING: dict[str, tuple[MissingDataCategory, ...]] = {
    consent_policy.CATEGORY_PATIENT_PROFILE: ("demographics",),
    consent_policy.CATEGORY_HEALTH_RECORDS: (
        "allergies",
        "medical_history",
        "vitals_metrics",
    ),
    consent_policy.CATEGORY_MEDICATIONS: ("medications",),
    consent_policy.CATEGORY_LAB_RESULTS: ("labs",),
}


def _withheld_labels(withheld: frozenset[str]) -> dict[MissingDataCategory, str]:
    """Map withheld consent categories to their "not shared" wording."""
    labels: dict[MissingDataCategory, str] = {}
    for consent_category in withheld:
        for missing_category in _CONSENT_CATEGORY_TO_MISSING.get(consent_category, ()):
            label = _WITHHELD_DATA_LABELS_VI.get(missing_category)
            if label is not None:
                labels[missing_category] = label
    return labels


class CopilotUnavailable(Exception):
    """Raised when every LLM provider is unavailable for a copilot request."""


class CopilotMalformedOutput(Exception):
    """Provider answered but the structure couldn't be safely used."""


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _safe(text_: str) -> str:
    """Re-validate an LLM-composed string; replace with a neutral line if blocked.

    Mirrors ``app.services.clinical_insight._safe`` (defense in depth — the last
    line before any AI-composed text reaches a doctor).
    """
    if check_output(text_).allowed:
        return text_
    return "Bạn nên trao đổi trực tiếp với bác sĩ chuyên khoa để được tư vấn cụ thể."


def _parse_list(val: object) -> list[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        if val.startswith("gAAAAAB"):
            logger.warning(
                "clinical_copilot: field still looks encrypted — check FIELD_ENCRYPTION_KEY"
            )
            return []
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else [val] if val.strip() else []
        except Exception:
            return [val] if val.strip() else []
    return []


def _coerce_datetime(value: object) -> dt.datetime | None:
    """SQLite's driver returns TEXT for DateTime columns read via a raw ``text()``
    query (no ORM type deserialization) — normalize to a real ``datetime`` so
    every downstream ``.isoformat()`` call is safe, matching what the ORM would
    have given us."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _load_profile(db: Session, patient_id: str) -> PatientProfile | None:
    return db.query(PatientProfile).filter(PatientProfile.id == patient_id).first()


def _conditions_and_allergies(profile: PatientProfile | None) -> tuple[list[str], list[str]]:
    """Mirrors ``ContextBuilder._build_health_summary`` but keyed by an
    already-loaded profile (single query per request, shared with the
    completeness assessor / source map instead of re-querying)."""
    if profile is None:
        return [], []
    return _parse_list(profile.known_conditions), _parse_list(profile.allergies)


@dataclass(frozen=True)
class CopilotDataGate:
    """Which consent categories this request may read.

    ``allowed=None`` means "not governed by consultation consent" — the
    patient-page / clinic-scoped copilot path, which has its own authorisation
    and is unchanged by this feature. A consultation-scoped call always carries
    a real set, so the copilot can never see more than the patient granted for
    that consultation.
    """

    allowed: frozenset[str] | None = None

    def permits(self, category: str) -> bool:
        return self.allowed is None or category in self.allowed

    def withheld(self) -> frozenset[str]:
        """Categories this request is NOT allowed to read."""
        if self.allowed is None:
            return frozenset()
        return frozenset(consent_policy.CATEGORIES) - self.allowed


UNGATED = CopilotDataGate()


def _empty_health_summary() -> HealthSummary:
    """The summary for a request that may not read health records at all.

    Every field defaults to empty/low, so a withheld category yields "nothing to
    report" rather than a partially-populated summary a doctor might read as a
    complete one. The accompanying ``missing_data`` entry says the category was
    withheld, not that the patient has no records.
    """
    return HealthSummary(abnormal_count=0)


def _gated_profile(db: Session, patient_id: str, gate: CopilotDataGate) -> PatientProfile | None:
    """Demographics ride patient_profile; without it the copilot has no subject
    details and ``_assess_completeness`` correctly drops confidence."""
    if not gate.permits(consent_policy.CATEGORY_PATIENT_PROFILE):
        return None
    return _load_profile(db, patient_id)


def _gated_conditions_and_allergies(
    db: Session, patient_id: str, profile: PatientProfile | None, gate: CopilotDataGate
) -> tuple[list[str], list[str]]:
    """Conditions and allergies are clinical record content, not demographics —
    they ride health_records, independently of whether demographics were shared.

    The profile is re-loaded here when demographics were withheld but health
    records were granted, so one ungranted category never silently suppresses
    another.
    """
    if not gate.permits(consent_policy.CATEGORY_HEALTH_RECORDS):
        return [], []
    source = profile if profile is not None else _load_profile(db, patient_id)
    return _conditions_and_allergies(source)


def _medication_records(db: Session, patient_id: str) -> list[dict]:
    """(id, name, dose, frequency, created_at) — the single query backing both
    the display-facing ``MedicationBrief`` list and the source-map citations."""
    rows = db.execute(
        text(
            """
            SELECT id, name, dose, frequency, created_at, lifecycle_status
            FROM medications
            WHERE patient_id = :pid AND deleted_at IS NULL
              AND lifecycle_status IN ('active', 'paused')
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"pid": patient_id, "limit": _MAX_MEDICATIONS},
    ).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "dose": r[2],
            "frequency": r[3],
            "created_at": _coerce_datetime(r[4]),
            "lifecycle_status": r[5],
        }
        for r in rows
    ]


def _medication_briefs(records: list[dict]) -> list[MedicationBrief]:
    # ADR-11: paused medications stay visible but must be distinguishable
    # from actively-taken ones in the clinician-facing brief.
    return [
        MedicationBrief(
            name=r["name"] + (" (tạm ngưng)" if r.get("lifecycle_status") == "paused" else ""),
            dosage=r["dose"] or "",
            frequency=r["frequency"] or "",
        )
        for r in records
    ]


def _lab_rows(db: Session, patient_id: str) -> list[LabResult]:
    """Confirmed, non-deleted lab results for the patient, newest first. Backs
    the ``labs`` completeness signal, the staleness check, the (existing)
    data_quality_flag contradiction signal, and the lab SourceRef citations.

    Only rows a human confirmed (``verified_by_user`` or ``verified_by_doctor``)
    are included — an unverified OCR row is the machine's reading of a
    photograph, and citing one as the "as of" provenance behind a clinical
    finding tells a doctor the record says something no one has checked. This
    matches every other clinical read path (health_timeline, narrative,
    patient_insight, lab_intelligence), which this query had silently diverged
    from.
    """
    return list(
        db.execute(
            select(LabResult)
            .join(LabUploadBatch, LabUploadBatch.id == LabResult.batch_id, isouter=True)
            .where(
                LabResult.patient_id == patient_id,
                LabResult.deleted_at.is_(None),
                (LabResult.verified_by_user.is_(True))
                | (LabResult.verified_by_doctor.is_(True)),
            )
            .order_by(LabResult.test_date.desc().nullslast())
        )
        .scalars()
        .all()
    )


def _metric_rows(db: Session, patient_id: str) -> list[HealthMetric]:
    """All non-deleted health metrics for the patient, newest first. Backs the
    ``vitals_metrics`` completeness signal, the staleness check, and the metric
    SourceRef citations."""
    return list(
        db.execute(
            select(HealthMetric)
            .where(HealthMetric.patient_id == patient_id, HealthMetric.deleted_at.is_(None))
            .order_by(HealthMetric.measured_at.desc())
        )
        .scalars()
        .all()
    )


def _is_lab_metric_type(metric_type: str) -> bool:
    """True if ``metric_type`` resolves to a lab biomarker (vs a manually-logged
    vital like blood pressure/weight) — mirrors
    ``clinical_insight._lab_canonical``'s exact-alias-only resolution."""
    raw = (metric_type or "").strip().lower()
    if raw in _ALIAS_INDEX:
        return True
    aliased = ic.METRIC_TYPE_ALIASES.get(raw)
    return bool(aliased and aliased in _ALIAS_INDEX)


def _has_lab_data(db: Session, patient_id: str) -> bool:
    row = (
        db.query(LabResult)
        .join(LabUploadBatch, LabUploadBatch.id == LabResult.batch_id)
        .filter(
            LabUploadBatch.patient_id == patient_id,
            LabResult.deleted_at.is_(None),
            LabUploadBatch.deleted_at.is_(None),
        )
        .first()
    )
    return row is not None


def _has_metric_data(db: Session, patient_id: str) -> bool:
    row = (
        db.query(HealthMetric)
        .filter(HealthMetric.patient_id == patient_id, HealthMetric.deleted_at.is_(None))
        .first()
    )
    return row is not None


def _value_display(insight: MetricInsight) -> str:
    value = insight.original_value if insight.original_value is not None else insight.value
    unit = insight.original_unit if insight.original_unit is not None else insight.unit
    return f"{value} {unit}".strip() if unit else str(value)


def _compute_priority(findings: list[MetricInsight]) -> RiskFlag:
    """Deterministic RiskFlag.level — NEVER overridden by any LLM phrasing.
    ``missing_data`` AND ``sources`` start empty and are patched in by the
    caller (via ``model_copy``) once the shared completeness assessment / the
    source map have run. ``MetricInsight`` (this function's only input) carries
    no underlying row id — only ``_build_source_map`` resolves which concrete
    ``LabResult``/``HealthMetric`` row backs a given finding, so deriving
    ``sources`` here would either be a category-label stand-in (the bug being
    fixed) or a duplicate of that resolution that could drift out of sync.
    Keeping this function to ``findings`` alone preserves its deterministic,
    LLM-independent, side-effect-free contract."""
    if any(f.status == "critical" for f in findings):
        level: RiskLevel = "urgent"
    elif any(f.priority == "see_doctor" for f in findings):
        level = "see_doctor_soon"
    elif any(f.priority == "watch" for f in findings):
        level = "monitor"
    else:
        level = "normal"
    return RiskFlag(
        level=level,
        label_vi=_LEVEL_LABEL_VI[level],
        findings=[f.label for f in findings],
        missing_data=[],
        sources=[],
    )


def _record(
    db: Session,
    *,
    doctor_user_id: str,
    patient_id: str,
    action: str,
    outcome: str,
    severity: str,
) -> None:
    audit.record(
        db,
        actor_type="doctor",
        actor_id=doctor_user_id,
        action=action,
        resource_type="patient_profile",
        resource_id=patient_id,
        outcome=outcome,
        severity=severity,
    )
    db.commit()


# --------------------------------------------------------------------------- #
# Completeness / confidence — ONE shared, deterministic assessor
# --------------------------------------------------------------------------- #


def _is_stale_date(value: dt.date | dt.datetime | None) -> bool:
    if value is None:
        return False
    as_date = value.date() if isinstance(value, dt.datetime) else value
    cutoff = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=_STALE_DATA_DAYS)
    return as_date < cutoff


def _assess_completeness(
    *,
    conditions: list[str],
    allergies: list[str],
    medication_records: list[dict],
    chief_complaint: str | None,
    consultation_id: str | None,
    demographics_present: bool,
    has_lab_data: bool,
    has_metric_data: bool,
    has_stale: bool,
    has_contradiction: bool,
    withheld_categories: frozenset[str] | None = None,
) -> tuple[list[MissingDataItem], ConfidenceLevel, str | None]:
    """Pure, deterministic completeness/confidence assessment. NEVER touched by
    the LLM — every input is a plain fact already fetched/computed by the
    caller from the database.

    Applicability: ``symptoms`` and ``consultation_context`` only apply when a
    ``consultation_id`` was supplied (they describe THIS consultation's
    context, which doesn't exist outside one); the other six categories always
    apply.

    Presence: a category counts as present only when real, already-fetched data
    backs it — an empty ``allergies`` list is treated as UNKNOWN (never as
    "confirmed no allergies"), since `PatientProfile` has no such explicit flag.

    Confidence tiers (exact thresholds):
        completeness_ratio = present / applicable   (0.0 if nothing applies)

        completeness_ratio == 0.0          -> "low"
        completeness_ratio < 0.34          -> "low"
        has_contradiction                  -> "medium"  (never "high" when a
                                               data-quality flag exists)
        has_stale and ratio < 0.75         -> "medium"
        completeness_ratio >= 0.75
            and not has_stale              -> "high"
        otherwise                          -> "medium"
    """
    applicable: list[MissingDataCategory] = [
        "demographics",
        "allergies",
        "medications",
        "medical_history",
        "vitals_metrics",
        "labs",
    ]
    if consultation_id is not None:
        applicable += ["symptoms", "consultation_context"]

    has_chief_complaint = bool(chief_complaint and chief_complaint.strip())
    presence: dict[MissingDataCategory, bool] = {
        "demographics": demographics_present,
        "symptoms": has_chief_complaint,
        "allergies": bool(allergies),
        "medications": bool(medication_records),
        "medical_history": bool(conditions),
        "vitals_metrics": has_metric_data,
        "labs": has_lab_data,
        "consultation_context": has_chief_complaint,
    }

    # A category the patient withheld is NOT a category with no data. Saying
    # "chưa có thông tin thuốc" about a patient who simply did not share their
    # medication list invites a doctor to prescribe as if the list were empty,
    # which is the exact failure this consent feature must not introduce.
    withheld_labels = _withheld_labels(withheld_categories or frozenset())
    missing_data = [
        MissingDataItem(
            category=cat,
            label_vi=withheld_labels.get(cat) or _MISSING_DATA_LABELS_VI[cat],
        )
        for cat in applicable
        if not presence[cat]
    ]

    present_count = sum(1 for cat in applicable if presence[cat])
    completeness_ratio = present_count / len(applicable) if applicable else 0.0

    confidence: ConfidenceLevel
    if completeness_ratio == 0.0:
        confidence = "low"
    elif completeness_ratio < 0.34:
        confidence = "low"
    elif has_contradiction:
        confidence = "medium"
    elif has_stale and completeness_ratio < 0.75:
        confidence = "medium"
    elif completeness_ratio >= 0.75 and not has_stale:
        confidence = "high"
    else:
        confidence = "medium"

    confidence_note_vi: str | None
    if confidence == "low":
        confidence_note_vi = (
            "Phân tích dựa trên dữ liệu còn hạn chế hoặc chưa đầy đủ — cần bổ sung "
            "thêm thông tin trước khi đưa ra kết luận."
        )
    elif confidence == "medium":
        confidence_note_vi = "Một số dữ liệu có thể chưa đầy đủ hoặc chưa cập nhật gần đây."
    else:
        confidence_note_vi = None

    return missing_data, confidence, confidence_note_vi


def _completeness_signals(
    db: Session,
    *,
    patient_id: str,
    lab_rows: list[LabResult],
    metric_rows: list[HealthMetric],
) -> tuple[bool, bool, bool, bool]:
    """(has_lab_data, has_metric_data, has_stale, has_contradiction) — the four
    boolean signals ``_assess_completeness`` needs, derived from the same rows
    used to build the source map (no duplicate queries beyond what's already
    fetched for citations)."""
    has_lab = bool(lab_rows) or _has_lab_data(db, patient_id)
    has_metric = bool(metric_rows) or _has_metric_data(db, patient_id)

    has_contradiction = any((r.data_quality_flag or "").strip().lower() == "flag" for r in lab_rows)

    freshest_lab = lab_rows[0].test_date if lab_rows else None
    freshest_metric = metric_rows[0].measured_at if metric_rows else None
    has_stale = (has_lab and _is_stale_date(freshest_lab)) or (
        has_metric and _is_stale_date(freshest_metric)
    )
    return has_lab, has_metric, has_stale, has_contradiction


# --------------------------------------------------------------------------- #
# Source map — real ids + real dates, never invented
# --------------------------------------------------------------------------- #


def _lab_row_index(lab_rows: list[LabResult]) -> dict[str, LabResult]:
    """Freshest lab row per canonical/test name (``lab_rows`` is already
    newest-first)."""
    index: dict[str, LabResult] = {}
    for row in lab_rows:
        key = (row.canonical_name or row.test_name or "").strip().lower()
        if key and key not in index:
            index[key] = row
    return index


def _metric_row_index(metric_rows: list[HealthMetric]) -> dict[str, HealthMetric]:
    """Freshest metric row per CANONICAL metric key (``metric_rows`` is already
    newest-first, globally sorted by ``measured_at`` desc).

    Keyed by ``canonical_metric_key`` — the SAME alias-folding identity
    ``clinical_insight`` uses to build each ``MetricInsight`` — so a row stored
    under an alias raw type (e.g. ``metric_type="weight_kg"``) is found under
    the same key ``MetricInsight.metric_type`` uses (``"weight"``), instead of
    silently missing and falling back to a dateless, type-only citation.

    Because ``metric_rows`` is already sorted newest-first ACROSS ALL raw
    types, "first row seen for a canonical key" is already "freshest row
    across every aliased raw type for that key" — the same
    group-then-take-first-by-recency semantics ``clinical_insight._history``
    uses to pick the "current" reading, so the two never disagree about which
    row backs a given finding."""
    index: dict[str, HealthMetric] = {}
    for row in metric_rows:
        key = canonical_metric_key(row.metric_type)
        if key not in index:
            index[key] = row
    return index


def _resolve_metric_source(
    f: MetricInsight,
    *,
    lab_by_key: dict[str, LabResult],
    metric_by_type: dict[str, HealthMetric],
) -> tuple[str, SourceRef]:
    """The single source of truth for one finding's citation: ``(sid, SourceRef)``
    resolved from the SAME concrete row for id + date + label together. Shared by
    ``_build_source_map`` (the doctor-facing source catalog) and by
    ``get_analysis`` (to patch ``RiskFlag.sources``) so the two call sites can
    never disagree about which row backs a given finding, and a later reading of
    the same ``metric_type`` never resolves to (or overwrites) an earlier
    reading's citation id — each row gets its own id for as long as it exists."""
    if _is_lab_metric_type(f.metric_type):
        lab_row = lab_by_key.get(f.metric_type.strip().lower())
        if lab_row is not None:
            sid = f"lab:{lab_row.id}"
            date = lab_row.test_date.isoformat() if lab_row.test_date else None
        else:
            # No matching LabResult row found (e.g. metric promoted from a
            # source we can't trace back) — degrade to a dateless, type-scoped
            # citation rather than inventing or dropping it.
            sid = f"lab:{f.metric_type}"
            date = None
        return sid, SourceRef(id=sid, type="lab", label=f.label, date=date)

    metric_row = metric_by_type.get(f.metric_type)
    if metric_row is not None:
        sid = f"metric:{metric_row.id}"
        date = metric_row.measured_at.isoformat() if metric_row.measured_at else None
    else:
        # Same degrade-gracefully rationale as the lab branch above.
        sid = f"metric:{f.metric_type}"
        date = None
    return sid, SourceRef(id=sid, type="metric", label=f.label, date=date)


def _build_source_map(
    *,
    patient_id: str,
    profile: PatientProfile | None,
    conditions: list[str],
    allergies: list[str],
    medication_records: list[dict],
    findings: list[MetricInsight],
    lab_rows: list[LabResult],
    metric_rows: list[HealthMetric],
    consultation: Consultation | None,
) -> dict[str, SourceRef]:
    """Build the citation catalog: id -> SourceRef, with a REAL date resolved
    from the underlying record wherever one exists (never invented)."""
    source_map: dict[str, SourceRef] = {}

    profile_date = (
        profile.updated_at.isoformat() if profile is not None and profile.updated_at else None
    )
    if profile is not None:
        source_map[f"profile:{patient_id}"] = SourceRef(
            id=f"profile:{patient_id}", type="profile", label="Hồ sơ bệnh nhân", date=profile_date
        )

    # NOTE: condition/allergy ids are collection-item references into a single
    # encrypted JSON column on PatientProfile (`known_conditions`/`allergies`)
    # — NOT first-class DB rows with their own primary key. Unlike the
    # lab/metric/medication/consultation ids below (each backed by a real,
    # individually-addressable row), a `condition:<index>`/`allergy:<index>` id
    # is only stable for the lifetime of the CURRENT list ordering — it is NOT
    # guaranteed stable/immutable across a profile edit (e.g. reordering or
    # removing an earlier entry shifts every later index). This is a genuine
    # data-model limitation of how conditions/allergies are stored today, not a
    # bug fixed here.
    for i, c in enumerate(conditions):
        sid = f"condition:{i}"
        source_map[sid] = SourceRef(id=sid, type="condition", label=c, date=profile_date)
    for i, a in enumerate(allergies):
        sid = f"allergy:{i}"
        source_map[sid] = SourceRef(id=sid, type="allergy", label=a, date=profile_date)

    for rec in medication_records:
        sid = f"medication:{rec['id']}"
        created_at = rec.get("created_at")
        source_map[sid] = SourceRef(
            id=sid,
            type="medication",
            label=rec["name"],
            date=created_at.isoformat() if created_at else None,
        )

    lab_by_key = _lab_row_index(lab_rows)
    metric_by_type = _metric_row_index(metric_rows)

    for f in findings:
        sid, ref = _resolve_metric_source(f, lab_by_key=lab_by_key, metric_by_type=metric_by_type)
        source_map[sid] = ref

    if consultation is not None:
        sid = f"consultation:{consultation.id}"
        source_map[sid] = SourceRef(
            id=sid,
            type="consultation",
            label="Bối cảnh buổi tư vấn",
            date=consultation.created_at.isoformat() if consultation.created_at else None,
        )

    return source_map


def _source_catalog_text(source_map: dict[str, SourceRef]) -> str:
    if not source_map:
        return ""
    lines = [
        "Danh mục mã nguồn được phép trích dẫn (source_ids) — CHỈ được dùng "
        "id có trong danh sách này, KHÔNG được tự tạo id mới:"
    ]
    lines += [f"- {sid}: {ref.label}" for sid, ref in source_map.items()]
    return "\n".join(lines)


def _source_is_stale(source: SourceRef) -> bool:
    if source.date is None:
        return False
    try:
        return _is_stale_date(dt.date.fromisoformat(source.date[:10]))
    except ValueError:
        return False


def _build_cited_claims(raw_items: object, source_map: dict[str, SourceRef]) -> list[CitedClaim]:
    """Validate+resolve one LLM-returned list field into ``CitedClaim`` items.

    Per item (never fails the whole response — bad items are simply dropped):
    - must be a dict with a non-empty string ``text`` (else dropped);
    - ``source_ids`` (if present) must be a list of strings; only ids that
      exist in ``source_map`` are kept, unknown/invented ids are silently
      dropped;
    - >=1 valid source id survives -> basis="sourced", confidence="high"
      unless any resolved source is stale, then "medium";
    - 0 valid source ids survive -> basis="needs_confirmation", sources=[],
      confidence="low".
    """
    claims: list[CitedClaim] = []
    if not isinstance(raw_items, list):
        return claims
    for item in raw_items[:_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        raw_text = item.get("text")
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue
        raw_ids = item.get("source_ids")
        valid_ids = (
            [sid for sid in raw_ids if isinstance(sid, str) and sid in source_map]
            if isinstance(raw_ids, list)
            else []
        )
        basis: Literal["sourced", "needs_confirmation"]
        confidence: ConfidenceLevel
        if valid_ids:
            sources = [source_map[sid] for sid in valid_ids]
            basis = "sourced"
            confidence = "medium" if any(_source_is_stale(s) for s in sources) else "high"
        else:
            sources = []
            basis = "needs_confirmation"
            confidence = "low"
        claims.append(
            CitedClaim(text=_safe(raw_text), sources=sources, basis=basis, confidence=confidence)
        )
    return claims


# --------------------------------------------------------------------------- #
# LLM parsing / structural validation
# --------------------------------------------------------------------------- #


def _parse_llm_json(raw: str, required_list_keys: Iterable[str]) -> dict | None:
    """Best-effort parse of the LLM's forced-JSON output.

    Strips common markdown code-fence wrapping, then requires every key in
    ``required_list_keys`` to be present AND typed as a ``list`` at the top
    level. Returns None (never raises) on any TOP-LEVEL malformation — the
    caller treats None as a structural failure (``CopilotMalformedOutput``),
    distinct from individual bad items nested inside an otherwise-valid list
    (handled by ``_build_cited_claims`` / per-item filtering, which is NOT a
    failure).
    """
    text_ = (raw or "").strip()
    if text_.startswith("```"):
        text_ = text_.strip("`")
        if text_.lower().startswith("json"):
            text_ = text_[4:]
        text_ = text_.strip()
    try:
        parsed = json.loads(text_)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    if not all(key in parsed and isinstance(parsed[key], list) for key in required_list_keys):
        return None
    return parsed


async def _call_llm(
    *,
    system_prompt: str,
    user_content: str,
    task_type: str = "clinical_reasoning",
    max_tokens: int = 800,
) -> str:
    """Call the provider chain with fallback; raises ProviderUnavailableError
    if every provider in the chain fails (caller translates to CopilotUnavailable).
    Every provider in the chain shares this exact parsing/validation code path —
    no per-provider special-casing."""
    registry = get_registry()

    async def call_fn(provider):
        return await provider.chat(
            messages=[ChatMessage(role="user", content=user_content)],
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.2,
        )

    try:
        response, _provider_name, _fallback_used = await registry.call_with_fallback(
            task_type=task_type, call_fn=call_fn
        )
    except ProviderUnavailableError:
        raise
    except Exception as exc:
        # call_with_fallback bare-re-raises the last provider's own exception
        # (timeout, malformed response, rate limit, ...) instead of always
        # wrapping it — normalize here so callers only ever see
        # ProviderUnavailableError and never a raw provider exception.
        raise ProviderUnavailableError("all", str(exc)) from exc
    return response.content


def _findings_context_text(
    *,
    conditions: list[str],
    allergies: list[str],
    medications: list[MedicationBrief],
    findings: list[MetricInsight],
    chief_complaint: str | None,
    source_catalog: str = "",
) -> str:
    """Compact, factual bullet context for the LLM prompt. Contains ONLY
    already-vetted deterministic data — no free-text patient input."""
    lines: list[str] = []
    if chief_complaint:
        lines.append(f"Lý do khám: {chief_complaint}")
    if conditions:
        lines.append("Bệnh nền: " + ", ".join(conditions))
    if allergies:
        lines.append("Dị ứng: " + ", ".join(allergies))
    if medications:
        lines.append(
            "Thuốc đang dùng: "
            + ", ".join(f"{m.name} ({m.dosage} {m.frequency})".strip() for m in medications)
        )
    if findings:
        lines.append("Chỉ số bất thường:")
        for f in findings:
            lines.append(f"- {f.label}: {_value_display(f)} ({f.status}, {f.trend.label})")
    else:
        lines.append("Không có chỉ số bất thường nào được ghi nhận gần đây.")
    body = "\n".join(lines) if lines else "Không có dữ liệu lâm sàng đáng chú ý."
    if source_catalog:
        body = f"{body}\n\n{source_catalog}"
    return body


_JSON_ONLY_INSTRUCTION_VI = (
    "Chỉ trả lời bằng một object JSON hợp lệ đúng schema được yêu cầu, không thêm "
    "bất kỳ chữ nào khác ngoài JSON. Không đưa ra chẩn đoán cuối cùng, không kê đơn "
    "thuốc, không thay đổi liều thuốc. Dùng tiếng Việt, ngôn ngữ khả năng/gợi ý."
)


# --------------------------------------------------------------------------- #
# 1. Summary — pure assembly, no LLM
# --------------------------------------------------------------------------- #


def get_summary(
    db: Session,
    *,
    doctor_user_id: str,
    patient_id: str,
    consultation_id: str | None = None,
    chief_complaint: str | None = None,
    gate: CopilotDataGate = UNGATED,
) -> ClinicalSummaryOut:
    may_health = gate.permits(consent_policy.CATEGORY_HEALTH_RECORDS)
    profile = _gated_profile(db, patient_id, gate)
    conditions, allergies = _gated_conditions_and_allergies(db, patient_id, profile, gate)
    medication_records = (
        _medication_records(db, patient_id)
        if gate.permits(consent_policy.CATEGORY_MEDICATIONS)
        else []
    )
    medications = _medication_briefs(medication_records)
    findings = (
        list_insights(db, patient_id=patient_id, abnormal_only=True) if may_health else []
    )
    summary = (
        build_health_summary(db, patient_id=patient_id)
        if may_health
        else _empty_health_summary()
    )
    lab_rows = (
        _lab_rows(db, patient_id)
        if gate.permits(consent_policy.CATEGORY_LAB_RESULTS)
        else []
    )
    metric_rows = _metric_rows(db, patient_id) if may_health else []

    abnormal_findings = [
        AbnormalFindingBrief(
            metric_type=f.metric_type,
            label=f.label,
            status=f.status,
            value_display=_value_display(f),
            trend_label=f.trend.label,
            priority=f.priority,
        )
        for f in findings
    ]

    notable_changes: list[str] = []
    seen: set[str] = set()
    for entry in (*summary.improved, *summary.worsened):
        if entry not in seen:
            seen.add(entry)
            notable_changes.append(entry)

    source_map = _build_source_map(
        patient_id=patient_id,
        profile=profile,
        conditions=conditions,
        allergies=allergies,
        medication_records=medication_records,
        findings=findings,
        lab_rows=lab_rows,
        metric_rows=metric_rows,
        consultation=None,
    )
    sources = list(source_map.values())

    has_lab, has_metric, has_stale, has_contradiction = _completeness_signals(
        db, patient_id=patient_id, lab_rows=lab_rows, metric_rows=metric_rows
    )
    missing_data, confidence, confidence_note_vi = _assess_completeness(
        conditions=conditions,
        allergies=allergies,
        medication_records=medication_records,
        chief_complaint=chief_complaint,
        consultation_id=consultation_id,
        demographics_present=profile is not None,
        has_lab_data=has_lab,
        has_metric_data=has_metric,
        has_stale=has_stale,
        has_contradiction=has_contradiction,
        withheld_categories=gate.withheld(),
    )

    _record(
        db,
        doctor_user_id=doctor_user_id,
        patient_id=patient_id,
        action="ai_clinical_summary.generated",
        outcome="success",
        severity="info",
    )

    return ClinicalSummaryOut(
        as_of=dt.datetime.now(dt.UTC).isoformat(),
        conditions=conditions,
        allergies=allergies,
        medications=medications,
        abnormal_findings=abnormal_findings,
        notable_changes=notable_changes,
        sources=sources,
        confidence=confidence,
        missing_data=missing_data,
        confidence_note_vi=confidence_note_vi,
        disclaimer=DISCLAIMER_VI,
    )


# --------------------------------------------------------------------------- #
# 2. Analysis — deterministic priority + LLM-phrased, per-item cited reasoning
# --------------------------------------------------------------------------- #


async def get_analysis(
    db: Session,
    *,
    doctor_user_id: str,
    patient_id: str,
    consultation_id: str | None = None,
    chief_complaint: str | None = None,
    gate: CopilotDataGate = UNGATED,
) -> ClinicalAnalysisOut:
    def _fetch_context() -> tuple[
        RiskFlag, dict[str, SourceRef], list[MissingDataItem], ConfidenceLevel, str | None, str
    ]:
        """ALL blocking DB reads for this request, gathered synchronously in one
        threadpool hop (profile/conditions/allergies, medications, insight
        findings, consultation lookup, lab/metric rows, completeness signals,
        source-map + prompt-context assembly) — none of this may run on the
        event loop."""
        findings = (
            list_insights(db, patient_id=patient_id, abnormal_only=True)
            if gate.permits(consent_policy.CATEGORY_HEALTH_RECORDS)
            else []
        )
        priority = _compute_priority(findings)  # level/findings ALWAYS as-is.

        profile = _gated_profile(db, patient_id, gate)
        conditions, allergies = _gated_conditions_and_allergies(
            db, patient_id, profile, gate
        )
        medication_records = (
            _medication_records(db, patient_id)
            if gate.permits(consent_policy.CATEGORY_MEDICATIONS)
            else []
        )
        medications = _medication_briefs(medication_records)
        lab_rows = (
            _lab_rows(db, patient_id)
            if gate.permits(consent_policy.CATEGORY_LAB_RESULTS)
            else []
        )
        metric_rows = (
            _metric_rows(db, patient_id)
            if gate.permits(consent_policy.CATEGORY_HEALTH_RECORDS)
            else []
        )
        consultation = db.get(Consultation, consultation_id) if consultation_id else None
        if consultation is not None and consultation.patient_id != patient_id:
            # Defense-in-depth only: the route's `_authorize` gate is the sole
            # current caller and already raises 400 on a genuine mismatch
            # before this code ever runs. This guards a hypothetical future
            # caller that skips that check — never raise here, just drop the
            # untrusted consultation context.
            logger.warning(
                "clinical_copilot: consultation %s patient_id mismatch for patient %s "
                "— dropping consultation context",
                consultation_id,
                patient_id,
            )
            consultation = None

        source_map = _build_source_map(
            patient_id=patient_id,
            profile=profile,
            conditions=conditions,
            allergies=allergies,
            medication_records=medication_records,
            findings=findings,
            lab_rows=lab_rows,
            metric_rows=metric_rows,
            consultation=consultation,
        )

        # Patch RiskFlag.sources from the SAME source_map entries used for the
        # doctor-facing citation catalog — guarantees id/date/label all come
        # from the one concrete row per finding (see `_resolve_metric_source`).
        lab_by_key = _lab_row_index(lab_rows)
        metric_by_type = _metric_row_index(metric_rows)
        priority_sources: list[SourceRef] = []
        for f in findings:
            sid, _ref = _resolve_metric_source(
                f, lab_by_key=lab_by_key, metric_by_type=metric_by_type
            )
            priority_sources.append(source_map[sid])

        has_lab, has_metric, has_stale, has_contradiction = _completeness_signals(
            db, patient_id=patient_id, lab_rows=lab_rows, metric_rows=metric_rows
        )
        missing_data, confidence, confidence_note_vi = _assess_completeness(
            conditions=conditions,
            allergies=allergies,
            medication_records=medication_records,
            chief_complaint=chief_complaint,
            consultation_id=consultation_id,
            demographics_present=profile is not None,
            has_lab_data=has_lab,
            has_metric_data=has_metric,
            has_stale=has_stale,
            has_contradiction=has_contradiction,
            withheld_categories=gate.withheld(),
        )
        resolved_priority = priority.model_copy(
            update={"missing_data": missing_data, "sources": priority_sources}
        )

        context_text = _findings_context_text(
            conditions=conditions,
            allergies=allergies,
            medications=medications,
            findings=findings,
            chief_complaint=chief_complaint,
            source_catalog=_source_catalog_text(source_map),
        )
        return (
            resolved_priority,
            source_map,
            missing_data,
            confidence,
            confidence_note_vi,
            context_text,
        )

    (
        priority,
        source_map,
        missing_data,
        confidence,
        confidence_note_vi,
        context_text,
    ) = await run_in_threadpool(_fetch_context)

    system_prompt = (
        "Bạn là Meto Clinical Copilot, hỗ trợ BÁC SĨ đọc nhanh hồ sơ bệnh nhân — "
        "KHÔNG thay thế quyết định lâm sàng của bác sĩ. " + _JSON_ONLY_INSTRUCTION_VI + " "
        "Mỗi mục trong key_issues/contradictions_or_gaps/differentials_to_exclude "
        'PHẢI có dạng {"text": string, "source_ids": [id từ danh mục được cung cấp]}. '
        "Chỉ dùng source_ids có trong danh mục; nếu không có căn cứ rõ ràng, để "
        "source_ids là mảng rỗng thay vì tự bịa id. "
        'Schema: {"key_issues": [{"text": string, "source_ids": [string]}], '
        '"contradictions_or_gaps": [{"text": string, "source_ids": [string]}], '
        '"differentials_to_exclude": [{"text": string, "source_ids": [string]}]}.'
    )

    try:
        raw = await _call_llm(system_prompt=system_prompt, user_content=context_text)
    except ProviderUnavailableError as exc:
        logger.warning(
            "clinical_copilot analysis: provider unavailable for patient %s: %s",
            patient_id,
            exc,
        )
        await run_in_threadpool(
            _record,
            db,
            doctor_user_id=doctor_user_id,
            patient_id=patient_id,
            action="ai_clinical_analysis.failed",
            outcome="failed",
            severity="warning",
        )
        raise CopilotUnavailable(UNAVAILABLE_MESSAGE_VI) from exc

    parsed = _parse_llm_json(
        raw, ("key_issues", "contradictions_or_gaps", "differentials_to_exclude")
    )
    if parsed is None:
        await run_in_threadpool(
            _record,
            db,
            doctor_user_id=doctor_user_id,
            patient_id=patient_id,
            action="ai_clinical_analysis.malformed",
            outcome="failed",
            severity="warning",
        )
        raise CopilotMalformedOutput(UNAVAILABLE_MESSAGE_VI)

    key_issues = _build_cited_claims(parsed.get("key_issues"), source_map)
    contradictions = _build_cited_claims(parsed.get("contradictions_or_gaps"), source_map)
    differentials = _build_cited_claims(parsed.get("differentials_to_exclude"), source_map)

    await run_in_threadpool(
        _record,
        db,
        doctor_user_id=doctor_user_id,
        patient_id=patient_id,
        action="ai_clinical_analysis.generated",
        outcome="success",
        severity="info",
    )

    return ClinicalAnalysisOut(
        priority=priority,
        key_issues=key_issues,
        contradictions_or_gaps=contradictions,
        differentials_to_exclude=differentials,
        confidence=confidence,
        missing_data=missing_data,
        confidence_note_vi=confidence_note_vi,
        disclaimer=DISCLAIMER_VI,
    )


# --------------------------------------------------------------------------- #
# 3. Questions — LLM-suggested history-taking questions
# --------------------------------------------------------------------------- #


async def get_questions(
    db: Session,
    *,
    doctor_user_id: str,
    patient_id: str,
    consultation_id: str | None = None,
    chief_complaint: str | None = None,
    gate: CopilotDataGate = UNGATED,
) -> ClinicalQuestionsOut:
    def _fetch_context() -> tuple[list[MissingDataItem], ConfidenceLevel, str | None, str]:
        """ALL blocking DB reads for this request, gathered synchronously in one
        threadpool hop."""
        findings = (
            list_insights(db, patient_id=patient_id, abnormal_only=True)
            if gate.permits(consent_policy.CATEGORY_HEALTH_RECORDS)
            else []
        )
        profile = _gated_profile(db, patient_id, gate)
        conditions, allergies = _gated_conditions_and_allergies(
            db, patient_id, profile, gate
        )
        medication_records = (
            _medication_records(db, patient_id)
            if gate.permits(consent_policy.CATEGORY_MEDICATIONS)
            else []
        )
        medications = _medication_briefs(medication_records)
        lab_rows = (
            _lab_rows(db, patient_id)
            if gate.permits(consent_policy.CATEGORY_LAB_RESULTS)
            else []
        )
        metric_rows = (
            _metric_rows(db, patient_id)
            if gate.permits(consent_policy.CATEGORY_HEALTH_RECORDS)
            else []
        )

        has_lab, has_metric, has_stale, has_contradiction = _completeness_signals(
            db, patient_id=patient_id, lab_rows=lab_rows, metric_rows=metric_rows
        )
        missing_data, confidence, confidence_note_vi = _assess_completeness(
            conditions=conditions,
            allergies=allergies,
            medication_records=medication_records,
            chief_complaint=chief_complaint,
            consultation_id=consultation_id,
            demographics_present=profile is not None,
            has_lab_data=has_lab,
            has_metric_data=has_metric,
            has_stale=has_stale,
            has_contradiction=has_contradiction,
            withheld_categories=gate.withheld(),
        )

        context_text = _findings_context_text(
            conditions=conditions,
            allergies=allergies,
            medications=medications,
            findings=findings,
            chief_complaint=chief_complaint,
        )
        return missing_data, confidence, confidence_note_vi, context_text

    missing_data, confidence, confidence_note_vi, context_text = await run_in_threadpool(
        _fetch_context
    )

    system_prompt = (
        "Bạn là Meto Clinical Copilot, gợi ý câu hỏi khai thác bệnh sử cho BÁC SĨ hỏi "
        "bệnh nhân — bác sĩ quyết định hỏi gì. " + _JSON_ONLY_INSTRUCTION_VI + " "
        'Schema: {"questions": [{"group": one of '
        f"{sorted(_QUESTION_GROUPS)}, "
        '"question_vi": string, "reason_vi": string}]}.'
    )

    try:
        raw = await _call_llm(system_prompt=system_prompt, user_content=context_text)
    except ProviderUnavailableError as exc:
        logger.warning(
            "clinical_copilot questions: provider unavailable for patient %s: %s",
            patient_id,
            exc,
        )
        await run_in_threadpool(
            _record,
            db,
            doctor_user_id=doctor_user_id,
            patient_id=patient_id,
            action="ai_clinical_questions.failed",
            outcome="failed",
            severity="warning",
        )
        raise CopilotUnavailable(UNAVAILABLE_MESSAGE_VI) from exc

    parsed = _parse_llm_json(raw, ("questions",))
    if parsed is None:
        await run_in_threadpool(
            _record,
            db,
            doctor_user_id=doctor_user_id,
            patient_id=patient_id,
            action="ai_clinical_questions.malformed",
            outcome="failed",
            severity="warning",
        )
        raise CopilotMalformedOutput(UNAVAILABLE_MESSAGE_VI)

    questions: list[SuggestedQuestion] = []
    for item in parsed.get("questions", [])[:_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        group = item.get("group")
        question_vi = item.get("question_vi")
        reason_vi = item.get("reason_vi")
        # `isinstance` MUST run before the `frozenset` membership test — a
        # provider-returned list/dict for `group` is unhashable and would raise
        # `TypeError` from `not in _QUESTION_GROUPS` (short-circuit `or` means
        # only the type check needs to guard it here).
        if (
            not isinstance(group, str)
            or group not in _QUESTION_GROUPS
            or not isinstance(question_vi, str)
            or not question_vi.strip()
            or not isinstance(reason_vi, str)
            or not reason_vi.strip()
        ):
            continue
        questions.append(
            SuggestedQuestion(
                group=group,
                question_vi=_safe(question_vi),
                reason_vi=_safe(reason_vi),
            )
        )

    await run_in_threadpool(
        _record,
        db,
        doctor_user_id=doctor_user_id,
        patient_id=patient_id,
        action="ai_clinical_questions.generated",
        outcome="success",
        severity="info",
    )

    return ClinicalQuestionsOut(
        questions=questions,
        confidence=confidence,
        missing_data=missing_data,
        confidence_note_vi=confidence_note_vi,
        disclaimer=DISCLAIMER_VI,
    )


# --------------------------------------------------------------------------- #
# 4. Advice — LLM-suggested counseling direction
# --------------------------------------------------------------------------- #


async def get_advice(
    db: Session,
    *,
    doctor_user_id: str,
    patient_id: str,
    consultation_id: str | None = None,
    chief_complaint: str | None = None,
    gate: CopilotDataGate = UNGATED,
) -> ClinicalAdviceOut:
    def _fetch_context() -> tuple[list[MissingDataItem], ConfidenceLevel, str | None, str]:
        """ALL blocking DB reads for this request, gathered synchronously in one
        threadpool hop."""
        findings = (
            list_insights(db, patient_id=patient_id, abnormal_only=True)
            if gate.permits(consent_policy.CATEGORY_HEALTH_RECORDS)
            else []
        )
        profile = _gated_profile(db, patient_id, gate)
        conditions, allergies = _gated_conditions_and_allergies(
            db, patient_id, profile, gate
        )
        medication_records = (
            _medication_records(db, patient_id)
            if gate.permits(consent_policy.CATEGORY_MEDICATIONS)
            else []
        )
        medications = _medication_briefs(medication_records)
        lab_rows = (
            _lab_rows(db, patient_id)
            if gate.permits(consent_policy.CATEGORY_LAB_RESULTS)
            else []
        )
        metric_rows = (
            _metric_rows(db, patient_id)
            if gate.permits(consent_policy.CATEGORY_HEALTH_RECORDS)
            else []
        )

        has_lab, has_metric, has_stale, has_contradiction = _completeness_signals(
            db, patient_id=patient_id, lab_rows=lab_rows, metric_rows=metric_rows
        )
        missing_data, confidence, confidence_note_vi = _assess_completeness(
            conditions=conditions,
            allergies=allergies,
            medication_records=medication_records,
            chief_complaint=chief_complaint,
            consultation_id=consultation_id,
            demographics_present=profile is not None,
            has_lab_data=has_lab,
            has_metric_data=has_metric,
            has_stale=has_stale,
            has_contradiction=has_contradiction,
            withheld_categories=gate.withheld(),
        )

        context_text = _findings_context_text(
            conditions=conditions,
            allergies=allergies,
            medications=medications,
            findings=findings,
            chief_complaint=chief_complaint,
        )
        return missing_data, confidence, confidence_note_vi, context_text

    missing_data, confidence, confidence_note_vi, context_text = await run_in_threadpool(
        _fetch_context
    )

    system_prompt = (
        "Bạn là Meto Clinical Copilot, gợi ý hướng tư vấn cho BÁC SĨ dùng khi giải "
        "thích cho bệnh nhân — không đưa ra chẩn đoán cuối cùng, không kê đơn thuốc. "
        + _JSON_ONLY_INSTRUCTION_VI
        + ' Schema: {"items": [{"category": one of '
        f"{sorted(_ADVICE_CATEGORIES)}, "
        '"text_vi": string}]}. Mỗi mục suggested_tests chỉ mang tính tham khảo, '
        "không phải chỉ định bắt buộc."
    )

    try:
        raw = await _call_llm(system_prompt=system_prompt, user_content=context_text)
    except ProviderUnavailableError as exc:
        logger.warning(
            "clinical_copilot advice: provider unavailable for patient %s: %s",
            patient_id,
            exc,
        )
        await run_in_threadpool(
            _record,
            db,
            doctor_user_id=doctor_user_id,
            patient_id=patient_id,
            action="ai_clinical_advice.failed",
            outcome="failed",
            severity="warning",
        )
        raise CopilotUnavailable(UNAVAILABLE_MESSAGE_VI) from exc

    parsed = _parse_llm_json(raw, ("items",))
    if parsed is None:
        await run_in_threadpool(
            _record,
            db,
            doctor_user_id=doctor_user_id,
            patient_id=patient_id,
            action="ai_clinical_advice.malformed",
            outcome="failed",
            severity="warning",
        )
        raise CopilotMalformedOutput(UNAVAILABLE_MESSAGE_VI)

    items: list[AdviceItem] = []
    for item in parsed.get("items", [])[:_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        category = item.get("category")
        text_vi = item.get("text_vi")
        # Same isinstance-before-membership-test ordering as `get_questions` —
        # `category not in _ADVICE_CATEGORIES` would raise `TypeError` on an
        # unhashable provider value (list/dict) without the type check first.
        if (
            not isinstance(category, str)
            or category not in _ADVICE_CATEGORIES
            or not isinstance(text_vi, str)
            or not text_vi.strip()
        ):
            continue
        items.append(AdviceItem(category=category, text_vi=_safe(text_vi)))

    await run_in_threadpool(
        _record,
        db,
        doctor_user_id=doctor_user_id,
        patient_id=patient_id,
        action="ai_clinical_advice.generated",
        outcome="success",
        severity="info",
    )

    return ClinicalAdviceOut(
        items=items,
        confidence=confidence,
        missing_data=missing_data,
        confidence_note_vi=confidence_note_vi,
        disclaimer=DISCLAIMER_VI,
    )
