"""Patient Insight Layer — Phase E.

Converts clinical findings, patterns, trends, and derived metrics into
human-readable insight cards for Vietnamese patients (ages 45–70).

Design constraints:
- Rule-based only. No LLM dependency. Fully deterministic.
- Never overwhelming: max 5 insight cards, max 3 top priorities.
- Never diagnose, never prescribe.
- Doctor in the loop for any advice beyond monitoring.
- ocr_confidence is never used clinically.
- Only processes records with verified_by_user=True OR verified_by_doctor=True
  (enforcement happens upstream in the API layer; this module trusts its inputs).
- ai_draft_contract: None — reserved for Phase 2 LLM integration.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from .clinical_patterns import PatternDetection
from .clinical_rules import ClinicalFinding
from .derived_metrics import DerivedMetricResult
from .insight_detail_content import get_insight_detail
from .longitudinal import BiomarkerTrend

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class InsightCard:
    card_id: str  # e.g. "ldl_elevated"
    title_vi: str  # "LDL vẫn cao hơn mục tiêu"
    explanation_vi: str  # 1–2 sentences, plain language
    importance: str  # "high" | "medium" | "low"
    supporting_biomarkers: list[str]  # canonical names
    trend: str  # "improving" | "stable" | "worsening" | "insufficient_data"
    recommended_action: str  # "continue_monitoring" | "repeat_lab" | "discuss_with_doctor" | "lifestyle_reminder"  # noqa: E501
    action_text_vi: str  # Human-readable action text
    # --- Rich detail fields (populated for detail page) ---
    severity_label: str = ""          # "nhẹ" | "cần chú ý" | "quan trọng" | "cần hành động"
    rationale_vi: str = ""            # Why system flagged this — 2-4 sentences
    involved_markers: list[str] = field(default_factory=list)    # direct markers (canonical)
    derived_markers: list[str] = field(default_factory=list)     # derived metric canonicals
    risk_explanation_vi: str = ""     # Health risk explanation
    daily_actions: list[str] = field(default_factory=list)       # 3-5 concrete daily actions
    doctor_questions: list[str] = field(default_factory=list)    # Questions to ask doctor
    red_flags: list[str] = field(default_factory=list)           # When to see doctor urgently
    not_to_do: list[str] = field(default_factory=list)           # "Không nên tự làm"
    # v2 fields
    biomarker_explainer_vi: str = ""         # Section 3: "What is this biomarker?"
    reasoning_steps: list[str] = field(default_factory=list)   # Section 4: AI reasoning chain
    related_insights: list[str] = field(default_factory=list)  # Section 14: related card_ids
    urgency_label: str = ""                  # "routine" | "1_month" | "soon" | "immediately"
    urgency_vi: str = ""                     # Vietnamese label for urgency
    evidence_level: str = ""                 # "strong" | "moderate" | "emerging"
    evidence_label_vi: str = ""              # Vietnamese label for evidence
    derived_indicators: list[dict] = field(default_factory=list)  # Section 6: computed indicators
    patterns_vi: list[str] = field(default_factory=list)          # Section 7: pattern descriptions


@dataclass
class ActionCard:
    action_id: str  # e.g. "repeat_lipid_panel"
    title_vi: str
    detail_vi: str
    interval_days: int | None  # e.g. 90 for "repeat in 3 months"
    action_type: str  # "monitor" | "repeat_lab" | "doctor_visit" | "lifestyle"


@dataclass
class TimelineSummaryItem:
    canonical: str
    display_name_vi: str
    trend: str  # "improving" | "stable" | "worsening" | "insufficient_data"
    trend_text_vi: str  # Plain Vietnamese: "Đang cải thiện", "Ổn định", etc.
    change_pct: float | None


@dataclass
class UrgentAlert:
    alert_id: str
    title_vi: str
    detail_vi: str
    biomarkers: list[str]
    action_vi: str  # Always "Cần gặp bác sĩ sớm" or similar — never diagnose


@dataclass
class PositiveReinforcement:
    message_vi: str  # "Đường huyết đã cải thiện so với lần trước."
    biomarkers: list[str]


@dataclass
class PatientInsightReport:
    patient_id: str
    generated_at: str  # ISO8601

    # Executive Summary
    overall_status: str  # "good" | "attention" | "action_required" | "urgent"
    overall_status_text_vi: str
    top_priorities: list[str]  # list of card_id strings, max 3

    # Sections
    insights: list[InsightCard]
    action_cards: list[ActionCard]
    timeline: list[TimelineSummaryItem]
    positive_reinforcement: list[PositiveReinforcement]
    urgent_alerts: list[UrgentAlert]

    # AI draft hook (reserved for Phase 2 LLM)
    ai_draft_contract: None

    # Safety
    disclaimer_vi: str  # Required: "Đây là thông tin tham khảo..."


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DISCLAIMER = (
    "Đây là thông tin tham khảo từ kết quả xét nghiệm đã được xác nhận. "
    "Không phải chẩn đoán y khoa. "
    "Luôn tham khảo ý kiến bác sĩ trước khi thay đổi chế độ điều trị."
)

_TREND_TEXT_VI: dict[str, str] = {
    "improving": "Đang cải thiện",
    "stable": "Ổn định",
    "worsening": "Đang xấu đi",
    "insufficient_data": "Chưa đủ dữ liệu",
}

_IMPORTANCE_ORDER = {"high": 0, "medium": 1, "low": 2}

# Map severity → insight importance
_SEVERITY_TO_IMPORTANCE = {
    "critical": "high",
    "warning": "high",
    "watch": "medium",
    "info": "low",
}

# Map severity → recommended_action
_SEVERITY_TO_ACTION = {
    "critical": "discuss_with_doctor",
    "warning": "discuss_with_doctor",
    "watch": "repeat_lab",
    "info": "continue_monitoring",
}

_SEVERITY_TO_ACTION_TEXT_VI = {
    "critical": "Cần gặp bác sĩ sớm để được đánh giá.",  # noqa: E501
    "warning": "Trao đổi với bác sĩ trong lần khám tới.",
    "watch": "Nên xét nghiệm lại theo lịch định kỳ.",
    "info": "Tiếp tục theo dõi theo lịch thông thường.",
}

# Per-biomarker friendly display names (Vietnamese)
_DISPLAY_VI: dict[str, str] = {
    "fasting_glucose": "Đường huyết lúc đói",
    "hba1c": "HbA1c",
    "ldl": "LDL Cholesterol",
    "hdl": "HDL Cholesterol",
    "triglyceride": "Triglyceride",
    "total_cholesterol": "Cholesterol toàn phần",
    "creatinine": "Creatinine",
    "egfr": "Mức lọc cầu thận (eGFR)",
    "egfr_ckd_epi": "Mức lọc cầu thận (eGFR CKD-EPI)",
    "alt": "Men gan ALT",
    "ast": "Men gan AST",
    "tsh": "TSH tuyến giáp",
    "sodium": "Natri máu",
    "potassium": "Kali máu",
    "hemoglobin": "Hemoglobin",
    "uric_acid": "Axit uric",
    "non_hdl_cholesterol": "Cholesterol không HDL",
    "ldl_friedewald": "LDL (Friedewald)",
    "tyg_index": "Chỉ số TyG",
    "fib4_score": "Chỉ số FIB-4",
    "metabolic_syndrome": "Hội chứng chuyển hóa",
}


def _display_vi(canonical: str) -> str:
    return _DISPLAY_VI.get(canonical, canonical)


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------


def _build_urgent_alerts(findings: list[ClinicalFinding]) -> list[UrgentAlert]:
    """Generate UrgentAlert for every finding with severity == 'critical'."""
    alerts: list[UrgentAlert] = []
    for f in findings:
        if f.severity == "critical":
            alerts.append(
                UrgentAlert(
                    alert_id=f"alert_{f.canonical}",
                    title_vi=f"Chỉ số {_display_vi(f.canonical)} cần chú ý ngay",  # noqa: E501
                    detail_vi=f.patient_explanation_vi,
                    biomarkers=[f.canonical],
                    action_vi="Cần gặp bác sĩ sớm để được đánh giá và xử lý kịp thời.",
                )
            )
    return alerts


def _derive_overall_status(
    findings: list[ClinicalFinding],
    patterns: list[PatternDetection],
) -> tuple[str, str]:
    """Return (overall_status, overall_status_text_vi)."""
    if any(f.severity == "critical" for f in findings):
        return "urgent", "Cần gặp bác sĩ sớm — có chỉ số ở mức nguy hiểm."
    if any(p.severity == "warning" for p in patterns):
        return "action_required", "Cần hành động — có mẫu hình đáng lo ngại."
    if any(f.severity in {"warning", "watch"} for f in findings):
        return "attention", "Cần chú ý — một số chỉ số cần theo dõi thêm."
    if not findings:
        return "good", "Các chỉ số đang trong giới hạn bình thường."
    if all(f.severity == "info" for f in findings):
        return "good", "Các chỉ số đang trong giới hạn bình thường."
    return "attention", "Cần chú ý — một số chỉ số cần theo dõi thêm."


def _trend_for(canonical: str, trends: list[BiomarkerTrend]) -> str:
    """Look up trend for a given canonical name."""
    for t in trends:
        if t.canonical == canonical:
            return t.trend
    return "insufficient_data"


def _build_insight_cards(
    findings: list[ClinicalFinding],
    patterns: list[PatternDetection],
    trends: list[BiomarkerTrend],
    derived: dict[str, DerivedMetricResult],
) -> list[InsightCard]:
    """Build InsightCards from findings, patterns, and derived metrics.

    Rules:
    - Skip 'normal'/'info' biomarker findings (no card needed).
    - Derived metric findings with abnormal status generate cards.
    - Pattern detections generate one card per pattern.
    - Sorted by importance (high → medium → low), then deduplicated by card_id.
    - Maximum 5 cards returned.
    """
    cards: list[InsightCard] = []
    seen_ids: set[str] = set()

    # Cards from biomarker findings
    for f in findings:
        if f.status == "normal" and f.severity == "info":
            continue

        card_id = f"insight_{f.canonical}_{f.status}"
        if card_id in seen_ids:
            continue
        seen_ids.add(card_id)

        importance = _SEVERITY_TO_IMPORTANCE.get(f.severity, "low")
        action = _SEVERITY_TO_ACTION.get(f.severity, "continue_monitoring")
        action_text = _SEVERITY_TO_ACTION_TEXT_VI.get(f.severity, "Tiếp tục theo dõi.")

        trend = _trend_for(f.canonical, trends)

        cards.append(
            InsightCard(
                card_id=card_id,
                title_vi=_title_for_finding(f),
                explanation_vi=f.patient_explanation_vi,
                importance=importance,
                supporting_biomarkers=[f.canonical],
                trend=trend,
                recommended_action=action,
                action_text_vi=action_text,
            )
        )

    # Cards from patterns
    for p in patterns:
        card_id = f"pattern_{p.pattern_id}"
        if card_id in seen_ids:
            continue
        seen_ids.add(card_id)

        importance = _SEVERITY_TO_IMPORTANCE.get(p.severity, "medium")
        action = _SEVERITY_TO_ACTION.get(p.severity, "repeat_lab")
        action_text = _SEVERITY_TO_ACTION_TEXT_VI.get(p.severity, "Theo dõi thêm.")

        # Determine collective trend from supporting biomarkers
        trend = _collective_trend(p.supporting_findings, trends)

        cards.append(
            InsightCard(
                card_id=card_id,
                title_vi=p.display_name_vi,
                explanation_vi=p.description_vi,
                importance=importance,
                supporting_biomarkers=p.supporting_findings,
                trend=trend,
                recommended_action=action,
                action_text_vi=action_text,
            )
        )

    # Cards from derived metrics with abnormal status
    for canonical, dr in derived.items():
        if dr.status not in {"abnormal", "borderline"}:
            continue
        card_id = f"derived_{canonical}"
        if card_id in seen_ids:
            continue
        seen_ids.add(card_id)

        importance = "high" if dr.status == "abnormal" else "medium"
        action = "discuss_with_doctor" if dr.status == "abnormal" else "repeat_lab"
        action_text = (
            _SEVERITY_TO_ACTION_TEXT_VI["warning"]
            if dr.status == "abnormal"
            else _SEVERITY_TO_ACTION_TEXT_VI["watch"]
        )
        trend = _trend_for(canonical, trends)

        cards.append(
            InsightCard(
                card_id=card_id,
                title_vi=dr.display_name_vi,
                explanation_vi=dr.note_vi or f"{dr.display_name_vi} đang ở mức cần chú ý.",  # noqa: E501
                importance=importance,
                supporting_biomarkers=dr.inputs_used,
                trend=trend,
                recommended_action=action,
                action_text_vi=action_text,
            )
        )

    # Enrich cards with deep detail content
    for card in cards:
        _detail = get_insight_detail(card.card_id)
        if _detail:
            card.severity_label = _detail["severity_label"]
            card.rationale_vi = _detail["rationale_vi"]
            card.risk_explanation_vi = _detail["risk_explanation_vi"]
            card.daily_actions = _detail["daily_actions"]
            card.doctor_questions = _detail["doctor_questions"]
            card.red_flags = _detail["red_flags"]
            card.not_to_do = _detail["not_to_do"]
            card.derived_markers = _detail["derived_markers"]
            card.involved_markers = _detail.get("involved_markers", card.supporting_biomarkers)
            # v2 fields
            card.biomarker_explainer_vi = _detail.get("biomarker_explainer_vi", "")
            card.reasoning_steps = _detail.get("reasoning_steps", [])
            card.related_insights = _detail.get("related_insights", [])
            card.urgency_label = _detail.get("urgency_label", "routine")
            card.urgency_vi = _detail.get("urgency_vi", "")
            card.evidence_level = _detail.get("evidence_level", "")
            card.evidence_label_vi = _detail.get("evidence_label_vi", "")

    # Populate derived_indicators for relevant cards
    _DERIVED_DISPLAY: dict[str, tuple[str, str, str, str, str]] = {
        "tg_hdl_ratio": (
            "TG/HDL", "TG (mmol/L) / HDL (mmol/L)", "<1.0",
            "Tầm soát kháng insulin", "moderate",
        ),
        "ldl_hdl_ratio": (
            "LDL/HDL", "LDL (mg/dL) / HDL (mg/dL)", "<2.0",
            "Nguy cơ xơ vữa", "strong",
        ),
        "tc_hdl_ratio": (
            "TC/HDL", "TC (mg/dL) / HDL (mg/dL)", "<4.0",
            "Nguy cơ tim mạch tổng thể", "strong",
        ),
        "non_hdl_cholesterol": (
            "Non-HDL-C", "TC − HDL (mmol/L)", "<3.37 mmol/L",
            "Gánh nặng lipoprotein sinh xơ vữa", "strong",
        ),
        "ldl_friedewald": (
            "LDL Friedewald", "TC − HDL − TG/5 (mg/dL)", "<130 mg/dL",
            "LDL ước tính; không dùng khi TG≥400", "strong",
        ),
        "tyg_index": (
            "TyG Index", "ln(TG × Glu / 2)", "<9.0",
            "Tầm soát kháng insulin gián tiếp", "moderate",
        ),
        "egfr_ckd_epi": (
            "eGFR", "CKD-EPI 2021", "≥60 mL/min/1.73m²",
            "Chức năng lọc thận", "strong",
        ),
        "fib4_score": (
            "FIB-4", "(Tuổi × AST) / (Tiểu cầu × √ALT)", "<1.30",
            "Xơ hóa gan giai đoạn sớm", "moderate",
        ),
    }
    for card in cards:
        relevant = card.derived_markers or []
        card.derived_indicators = []
        for canon in relevant:
            dr = derived.get(canon)
            display = _DERIVED_DISPLAY.get(canon)
            if dr and display and dr.value is not None:
                card.derived_indicators.append({
                    "canonical": canon,
                    "display_name": display[0],
                    "formula": display[1],
                    "patient_value": dr.value,
                    "normal_range": display[2],
                    "clinical_meaning_vi": display[3],
                    "evidence_level": display[4],
                    "status": dr.status,
                    "unit": dr.unit,
                })

    # Sort by importance, then truncate to 5
    cards.sort(key=lambda c: _IMPORTANCE_ORDER.get(c.importance, 99))
    return cards[:5]


def _title_for_finding(f: ClinicalFinding) -> str:
    """Generate a human-readable Vietnamese title for a ClinicalFinding."""
    name = _display_vi(f.canonical)
    status_map = {
        "critical": f"{name} ở mức nguy hiểm",
        "high": f"{name} đang cao hơn mức bình thường",
        "low": f"{name} đang thấp hơn mức bình thường",
        "borderline": f"{name} đang ở vùng cần chú ý",
        "abnormal": f"{name} có chỉ số bất thường",
        "normal": f"{name} trong giới hạn bình thường",
    }
    return status_map.get(f.status, f"{name} cần theo dõi")


def _collective_trend(biomarkers: list[str], trends: list[BiomarkerTrend]) -> str:
    """Determine collective trend across a list of biomarker names."""
    found = [_trend_for(b, trends) for b in biomarkers]
    found = [t for t in found if t != "insufficient_data"]
    if not found:
        return "insufficient_data"
    if "worsening" in found:
        return "worsening"
    if all(t == "improving" for t in found):
        return "improving"
    return "stable"


def _build_action_cards(
    findings: list[ClinicalFinding],
    patterns: list[PatternDetection],
) -> list[ActionCard]:
    """Generate ActionCards based on finding categories."""
    cards: list[ActionCard] = []
    seen: set[str] = set()

    # Critical → immediate doctor visit
    if any(f.severity == "critical" for f in findings):
        cards.append(
            ActionCard(
                action_id="doctor_visit_urgent",
                title_vi="Gặp bác sĩ sớm",
                detail_vi="Có chỉ số xét nghiệm ở mức nguy hiểm. Cần bác sĩ đánh giá ngay.",  # noqa: E501
                interval_days=0,
                action_type="doctor_visit",
            )
        )
        seen.add("doctor_visit_urgent")

    # Categorize findings by organ/system
    lipid_names = {
        "ldl",
        "hdl",
        "triglyceride",
        "total_cholesterol",
        "non_hdl_cholesterol",
        "ldl_friedewald",
    }  # noqa: E501
    glucose_names = {"fasting_glucose", "hba1c", "tyg_index"}
    kidney_names = {"creatinine", "egfr", "egfr_ckd_epi"}
    liver_names = {"alt", "ast", "fib4_score"}

    has_abnormal_lipid = any(
        f.canonical in lipid_names and f.severity in {"warning", "watch", "critical"}
        for f in findings
    )
    has_abnormal_glucose = any(
        f.canonical in glucose_names and f.severity in {"warning", "watch", "critical"}
        for f in findings
    )
    has_abnormal_kidney = any(
        f.canonical in kidney_names and f.severity in {"warning", "watch", "critical"}
        for f in findings
    )
    has_abnormal_liver = any(
        f.canonical in liver_names and f.severity in {"warning", "watch", "critical"}
        for f in findings
    )

    # Pattern-based triggers
    if any(
        p.pattern_id in {"dyslipidemia", "insulin_resistance", "metabolic_syndrome"}
        for p in patterns
    ):  # noqa: E501
        has_abnormal_lipid = True

    if has_abnormal_lipid and "repeat_lipid_panel" not in seen:
        cards.append(
            ActionCard(
                action_id="repeat_lipid_panel",
                title_vi="Xét nghiệm lipid định kỳ",
                detail_vi="Kiểm tra lại bộ mỡ máu (LDL, HDL, Triglyceride) sau 3 tháng.",
                interval_days=90,
                action_type="repeat_lab",
            )
        )
        seen.add("repeat_lipid_panel")

    if has_abnormal_glucose and "repeat_glucose" not in seen:
        cards.append(
            ActionCard(
                action_id="repeat_glucose",
                title_vi="Xét nghiệm đường huyết lại",
                detail_vi="Kiểm tra lại đường huyết lúc đói và HbA1c sau 1 tháng.",
                interval_days=30,
                action_type="repeat_lab",
            )
        )
        seen.add("repeat_glucose")

    if has_abnormal_kidney and "repeat_kidney" not in seen:
        cards.append(
            ActionCard(
                action_id="repeat_kidney",
                title_vi="Theo dõi chức năng thận",
                detail_vi="Kiểm tra lại creatinine và eGFR sau 3 tháng để theo dõi chức năng thận.",  # noqa: E501
                interval_days=90,
                action_type="repeat_lab",
            )
        )
        seen.add("repeat_kidney")

    if has_abnormal_liver and "repeat_liver" not in seen:
        cards.append(
            ActionCard(
                action_id="repeat_liver",
                title_vi="Theo dõi men gan",
                detail_vi="Kiểm tra lại ALT/AST sau 1–3 tháng để theo dõi chức năng gan.",
                interval_days=60,
                action_type="repeat_lab",
            )
        )
        seen.add("repeat_liver")

    # If nothing abnormal → general monitoring reminder
    if not cards:
        cards.append(
            ActionCard(
                action_id="continue_monitoring",
                title_vi="Tiếp tục theo dõi sức khỏe",
                detail_vi="Các chỉ số hiện đang ổn định. Duy trì xét nghiệm định kỳ 6 tháng/lần.",
                interval_days=180,
                action_type="monitor",
            )
        )

    return cards


def _build_timeline(trends: list[BiomarkerTrend]) -> list[TimelineSummaryItem]:
    """Convert BiomarkerTrend objects to TimelineSummaryItem."""
    items: list[TimelineSummaryItem] = []
    for t in trends:
        items.append(
            TimelineSummaryItem(
                canonical=t.canonical,
                display_name_vi=t.display_name_vi or _display_vi(t.canonical),
                trend=t.trend,
                trend_text_vi=_TREND_TEXT_VI.get(t.trend, "Không rõ xu hướng"),
                change_pct=t.change_pct,
            )
        )
    return items


def _build_positive_reinforcement(trends: list[BiomarkerTrend]) -> list[PositiveReinforcement]:
    """Generate positive reinforcement messages for improving trends."""
    items: list[PositiveReinforcement] = []
    for t in trends:
        if t.trend == "improving":
            name = t.display_name_vi or _display_vi(t.canonical)
            items.append(
                PositiveReinforcement(
                    message_vi=f"{name} đã cải thiện so với lần đo trước. Hãy duy trì lối sống lành mạnh!",  # noqa: E501
                    biomarkers=[t.canonical],
                )
            )
    return items


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------


def generate_patient_insight(
    patient_id: str,
    findings: list[ClinicalFinding],
    patterns: list[PatternDetection],
    trends: list[BiomarkerTrend],
    derived: dict[str, DerivedMetricResult],
) -> PatientInsightReport:
    """Generate a PatientInsightReport from clinical outputs.

    Parameters
    ----------
    patient_id:
        The patient's ID string.
    findings:
        List of ClinicalFinding objects from clinical_rules.py.
    patterns:
        List of PatternDetection objects from clinical_patterns.py.
    trends:
        List of BiomarkerTrend objects from longitudinal.py.
    derived:
        Dict mapping canonical name → DerivedMetricResult from derived_metrics.py.

    Returns
    -------
    PatientInsightReport
        Fully populated insight report. Never raises on empty inputs.
    """
    generated_at = datetime.datetime.now(datetime.UTC).isoformat()

    # 1. Urgent alerts
    urgent_alerts = _build_urgent_alerts(findings)

    # 2. Overall status
    overall_status, overall_status_text_vi = _derive_overall_status(findings, patterns)

    # 3. Insight cards (max 5, sorted by importance)
    insights = _build_insight_cards(findings, patterns, trends, derived)

    # 4. Action cards
    action_cards = _build_action_cards(findings, patterns)

    # 5. Timeline
    timeline = _build_timeline(trends)

    # 6. Positive reinforcement
    positive_reinforcement = _build_positive_reinforcement(trends)

    # 7. Top priorities (card_ids of top 3 InsightCards by importance)
    top_priorities = [c.card_id for c in insights[:3]]

    return PatientInsightReport(
        patient_id=patient_id,
        generated_at=generated_at,
        overall_status=overall_status,
        overall_status_text_vi=overall_status_text_vi,
        top_priorities=top_priorities,
        insights=insights,
        action_cards=action_cards,
        timeline=timeline,
        positive_reinforcement=positive_reinforcement,
        urgent_alerts=urgent_alerts,
        ai_draft_contract=None,
        disclaimer_vi=_DISCLAIMER,
    )
