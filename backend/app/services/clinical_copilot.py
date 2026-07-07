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
  ``differentials_to_exclude``) — it can never change the computed level.
- ``get_questions`` / ``get_advice`` make one LLM call each, constrained to a
  strict JSON contract, with every returned string re-validated through
  ``guardrails.check_output`` before it is ever returned.
- A provider outage never raises a raw exception to the route layer — it is
  translated to ``CopilotUnavailable`` after writing a `.failed` audit row.
- A malformed/non-JSON LLM response never crashes and never leaks raw model
  output — it degrades to a neutral, safe fallback and the request still
  succeeds (only a genuine provider outage is a hard failure).
- AuditLog rows for this feature carry ONLY ids (actor_id, resource_id) —
  never any patient content, per ``app.services.audit``'s append-only,
  no-sensitive-content contract.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.exceptions import ProviderUnavailableError
from app.ai.providers.base import ChatMessage
from app.ai.registry import get_registry
from app.domain.guardrails import check_output
from app.domain.policies import DISCLAIMER_VI
from app.models.clinical import HealthMetric, LabResult, LabUploadBatch
from app.models.patient import PatientProfile
from app.schemas.clinical_copilot import (
    AbnormalFindingBrief,
    AdviceItem,
    ClinicalAdviceOut,
    ClinicalAnalysisOut,
    ClinicalQuestionsOut,
    ClinicalSummaryOut,
    ConfidenceLevel,
    MedicationBrief,
    RiskFlag,
    RiskLevel,
    SourceRef,
    SuggestedQuestion,
)
from app.services import audit
from app.services.clinical_insight import (
    MetricInsight,
    build_health_summary,
    list_insights,
)

logger = logging.getLogger(__name__)

UNAVAILABLE_MESSAGE_VI = "Meto phân tích hồ sơ hiện chưa khả dụng."

_MAX_MEDICATIONS = 10
_MAX_ITEMS = 8
_FALLBACK_LINE_VI = "Chưa thể tạo nội dung chi tiết lúc này. Vui lòng thử lại sau."

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


class CopilotUnavailable(Exception):
    """Raised when every LLM provider is unavailable for a copilot request."""


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


def _conditions_and_allergies(db: Session, patient_id: str) -> tuple[list[str], list[str]]:
    """Mirrors ``ContextBuilder._build_health_summary`` but keyed by patient_id
    directly (no user_id subselect needed — ORM auto-decrypts EncryptedString)."""
    profile = db.query(PatientProfile).filter(PatientProfile.id == patient_id).first()
    if profile is None:
        return [], []
    return _parse_list(profile.known_conditions), _parse_list(profile.allergies)


def _medications(db: Session, patient_id: str) -> list[MedicationBrief]:
    """Mirrors ``ContextBuilder._build_medications`` — patient_id-keyed directly."""
    rows = db.execute(
        text(
            """
            SELECT name, dose, frequency
            FROM medications
            WHERE patient_id = :pid AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"pid": patient_id, "limit": _MAX_MEDICATIONS},
    ).fetchall()
    return [MedicationBrief(name=r[0], dosage=r[1] or "", frequency=r[2] or "") for r in rows]


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
    """Deterministic RiskFlag.level — NEVER overridden by any LLM phrasing."""
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
        sources=[SourceRef(type="metric", label=f.label) for f in findings],
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


def _parse_llm_json(raw: str, required_keys: Iterable[str]) -> dict | None:
    """Best-effort parse of the LLM's forced-JSON output.

    Strips common markdown code-fence wrapping, then requires every key in
    ``required_keys`` to be present. Returns None (never raises) on any
    malformation — the caller degrades to a safe fallback instead of crashing
    or passing raw garbage through.
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
    if not all(key in parsed for key in required_keys):
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
    if every provider in the chain fails (caller translates to CopilotUnavailable)."""
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
    return "\n".join(lines) if lines else "Không có dữ liệu lâm sàng đáng chú ý."


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
) -> ClinicalSummaryOut:
    conditions, allergies = _conditions_and_allergies(db, patient_id)
    medications = _medications(db, patient_id)
    findings = list_insights(db, patient_id=patient_id, abnormal_only=True)
    summary = build_health_summary(db, patient_id=patient_id)

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

    sources: list[SourceRef] = [SourceRef(type="metric", label=f.label) for f in findings]
    sources += [SourceRef(type="medication", label=m.name) for m in medications]
    sources += [SourceRef(type="condition", label=c) for c in conditions]
    sources += [SourceRef(type="allergy", label=a) for a in allergies]

    blocks_present = [
        bool(conditions or allergies),
        bool(medications),
        _has_lab_data(db, patient_id),
        _has_metric_data(db, patient_id),
    ]
    present_count = sum(1 for b in blocks_present if b)
    confidence: ConfidenceLevel
    if present_count == len(blocks_present):
        confidence = "high"
    elif present_count == 0:
        confidence = "low"
    else:
        confidence = "medium"

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
        disclaimer=DISCLAIMER_VI,
    )


# --------------------------------------------------------------------------- #
# 2. Analysis — deterministic priority + LLM-phrased reasoning
# --------------------------------------------------------------------------- #


async def get_analysis(
    db: Session,
    *,
    doctor_user_id: str,
    patient_id: str,
    consultation_id: str | None = None,
    chief_complaint: str | None = None,
) -> ClinicalAnalysisOut:
    findings = list_insights(db, patient_id=patient_id, abnormal_only=True)
    priority = _compute_priority(findings)  # ALWAYS returned as-is — never LLM-derived.

    conditions, allergies = _conditions_and_allergies(db, patient_id)
    medications = _medications(db, patient_id)
    context_text = _findings_context_text(
        conditions=conditions,
        allergies=allergies,
        medications=medications,
        findings=findings,
        chief_complaint=chief_complaint,
    )
    system_prompt = (
        "Bạn là Meto Clinical Copilot, hỗ trợ BÁC SĨ đọc nhanh hồ sơ bệnh nhân — "
        "KHÔNG thay thế quyết định lâm sàng của bác sĩ. " + _JSON_ONLY_INSTRUCTION_VI + " "
        'Schema: {"key_issues": [string], "contradictions_or_gaps": [string], '
        '"differentials_to_exclude": [string]}.'
    )

    try:
        raw = await _call_llm(system_prompt=system_prompt, user_content=context_text)
    except ProviderUnavailableError as exc:
        logger.warning(
            "clinical_copilot analysis: provider unavailable for patient %s: %s",
            patient_id,
            exc,
        )
        _record(
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
        key_issues = [_FALLBACK_LINE_VI]
        contradictions: list[str] = []
        differentials: list[str] = []
    else:
        key_issues = [_safe(str(s)) for s in parsed.get("key_issues", [])][:_MAX_ITEMS]
        contradictions = [
            _safe(str(s)) for s in parsed.get("contradictions_or_gaps", [])
        ][:_MAX_ITEMS]
        differentials = [
            _safe(str(s)) for s in parsed.get("differentials_to_exclude", [])
        ][:_MAX_ITEMS]

    _record(
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
        confidence="high" if findings else "medium",
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
) -> ClinicalQuestionsOut:
    findings = list_insights(db, patient_id=patient_id, abnormal_only=True)
    conditions, allergies = _conditions_and_allergies(db, patient_id)
    medications = _medications(db, patient_id)
    context_text = _findings_context_text(
        conditions=conditions,
        allergies=allergies,
        medications=medications,
        findings=findings,
        chief_complaint=chief_complaint,
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
        _record(
            db,
            doctor_user_id=doctor_user_id,
            patient_id=patient_id,
            action="ai_clinical_questions.failed",
            outcome="failed",
            severity="warning",
        )
        raise CopilotUnavailable(UNAVAILABLE_MESSAGE_VI) from exc

    parsed = _parse_llm_json(raw, ("questions",))
    questions: list[SuggestedQuestion] = []
    if parsed is not None:
        for item in parsed.get("questions", [])[:_MAX_ITEMS]:
            if not isinstance(item, dict):
                continue
            group = item.get("group")
            question_vi = item.get("question_vi")
            reason_vi = item.get("reason_vi")
            if group not in _QUESTION_GROUPS or not question_vi or not reason_vi:
                continue
            questions.append(
                SuggestedQuestion(
                    group=group,
                    question_vi=_safe(str(question_vi)),
                    reason_vi=_safe(str(reason_vi)),
                )
            )

    _record(
        db,
        doctor_user_id=doctor_user_id,
        patient_id=patient_id,
        action="ai_clinical_questions.generated",
        outcome="success",
        severity="info",
    )

    return ClinicalQuestionsOut(
        questions=questions,
        confidence="high" if questions else "low",
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
) -> ClinicalAdviceOut:
    findings = list_insights(db, patient_id=patient_id, abnormal_only=True)
    conditions, allergies = _conditions_and_allergies(db, patient_id)
    medications = _medications(db, patient_id)
    context_text = _findings_context_text(
        conditions=conditions,
        allergies=allergies,
        medications=medications,
        findings=findings,
        chief_complaint=chief_complaint,
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
        _record(
            db,
            doctor_user_id=doctor_user_id,
            patient_id=patient_id,
            action="ai_clinical_advice.failed",
            outcome="failed",
            severity="warning",
        )
        raise CopilotUnavailable(UNAVAILABLE_MESSAGE_VI) from exc

    parsed = _parse_llm_json(raw, ("items",))
    items: list[AdviceItem] = []
    if parsed is not None:
        for item in parsed.get("items", [])[:_MAX_ITEMS]:
            if not isinstance(item, dict):
                continue
            category = item.get("category")
            text_vi = item.get("text_vi")
            if category not in _ADVICE_CATEGORIES or not text_vi:
                continue
            items.append(AdviceItem(category=category, text_vi=_safe(str(text_vi))))

    _record(
        db,
        doctor_user_id=doctor_user_id,
        patient_id=patient_id,
        action="ai_clinical_advice.generated",
        outcome="success",
        severity="info",
    )

    return ClinicalAdviceOut(
        items=items,
        confidence="high" if items else "low",
        disclaimer=DISCLAIMER_VI,
    )
