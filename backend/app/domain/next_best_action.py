"""Engine 15 — Next Best Action Engine.

Generates the single highest-value next action + max 2 secondary actions.
Never overwhelms the user. Prioritizes by: clinical impact × feasibility × urgency.

Action types:
  measure_next    — add a specific measurement
  lifestyle_today — lifestyle change to start now
  discuss_doctor  — bring to doctor
  repeat_lab      — repeat a specific lab test
  complete_profile — fill in missing profile data
  maintain_current — current approach is working

Design: ActionRule registry. Rules scored and ranked. Top 3 selected.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.domain.patient_context import PatientContext
from app.domain.preventive_risk import _LEVEL_SEVERITY, PreventiveRiskDomain

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SAFETY_NOTE_ACTION = (
    "Thông tin này mang tính giáo dục sức khỏe. "
    "Không thay thế tư vấn y khoa cá nhân từ bác sĩ."
)

# Tie-break order: higher = preferred when score is equal
_TYPE_PRIORITY: dict[str, int] = {
    "discuss_doctor": 6,
    "repeat_lab": 5,
    "measure_next": 4,
    "lifestyle_today": 3,
    "complete_profile": 2,
    "maintain_current": 1,
}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class NextBestAction:
    action_id: str
    action_type: str        # "measure_next"|"lifestyle_today"|"discuss_doctor"|"repeat_lab"|"complete_profile"|"maintain_current"  # noqa: E501
    title_vi: str
    why_vi: str
    expected_benefit_vi: str
    effort_level: str       # "low"|"medium"|"high"
    timeframe_vi: str       # "Hôm nay"|"Tuần này"|"Tháng này"|"Lần tái khám"
    confidence: str         # "high"|"medium"|"low"
    evidence_level: str     # "established"|"moderate"|"emerging"
    related_markers: list[str] = field(default_factory=list)
    safety_note_vi: str = _SAFETY_NOTE_ACTION


@dataclass
class NextBestActionResult:
    primary: NextBestAction
    secondary: list[NextBestAction]   # max 2
    ranking_explanation_vi: str       # 1 sentence: why primary was chosen


# ---------------------------------------------------------------------------
# ActionRule
# ---------------------------------------------------------------------------


@dataclass
class ActionRule:
    action_id: str
    condition: Callable[[dict, dict, PatientContext, list[PreventiveRiskDomain]], bool]
    score: Callable[[dict, dict, PatientContext, list[PreventiveRiskDomain]], int]
    build: Callable[[dict, dict, PatientContext, list[PreventiveRiskDomain]], NextBestAction]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _status(findings: dict, canonical: str) -> str:
    f = findings.get(canonical, {})
    if isinstance(f, dict):
        return f.get("status", "")
    return getattr(f, "status", "")


def _derived_val(derived: dict, canonical: str) -> float | None:
    v = derived.get(canonical)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return getattr(v, "value", None)


def _domain_level(domains: list[PreventiveRiskDomain], domain_id: str) -> str:
    for d in domains:
        if d.domain_id == domain_id:
            return d.level
    return "low_concern"


def _domain_severity(domains: list[PreventiveRiskDomain], domain_id: str) -> int:
    return _LEVEL_SEVERITY.get(_domain_level(domains, domain_id), 0)


def _level_gte(level: str, threshold: str) -> bool:
    """Return True if level severity >= threshold severity."""
    return _LEVEL_SEVERITY.get(level, 0) >= _LEVEL_SEVERITY.get(threshold, 0)


# ---------------------------------------------------------------------------
# Action Rule Implementations
# ---------------------------------------------------------------------------


def _build_action_registry() -> list[ActionRule]:
    rules: list[ActionRule] = []

    # 1. measure_bp
    def _bp_condition(findings, derived, ctx, domains):
        has_bp_signal = (
            (ctx.age is not None and ctx.age >= 40)
            or ctx.has_hypertension
            or ctx.cv_risk_category in ("high", "very_high")
        )
        bp_not_in_findings = "blood_pressure" not in findings and "bp_systolic" not in findings
        return has_bp_signal and bp_not_in_findings

    def _bp_score(findings, derived, ctx, domains):
        if ctx.cv_risk_category in ("high", "very_high"):
            return 70
        return 50

    def _bp_build(findings, derived, ctx, domains):
        return NextBestAction(
            action_id="measure_bp",
            action_type="measure_next",
            title_vi="Đo huyết áp tại nhà trong 7 ngày",
            why_vi="Huyết áp là yếu tố nguy cơ tim mạch quan trọng nhưng chưa có trong hồ sơ hiện tại.",  # noqa: E501
            expected_benefit_vi="Dữ liệu huyết áp giúp AI đánh giá nguy cơ tim mạch chính xác hơn và cá nhân hóa đề xuất.",  # noqa: E501
            effort_level="low",
            timeframe_vi="Tuần này",
            confidence="high",
            evidence_level="established",
            related_markers=["blood_pressure"],
        )

    rules.append(ActionRule("measure_bp", _bp_condition, _bp_score, _bp_build))

    # 2. measure_waist
    def _waist_condition(findings, derived, ctx, domains):
        return (
            ctx.waist_cm is None
            and (ctx.is_overweight() or ctx.has_diabetes or ctx.has_metabolic_risk())
        )

    def _waist_score(findings, derived, ctx, domains):
        return 65

    def _waist_build(findings, derived, ctx, domains):
        return NextBestAction(
            action_id="measure_waist",
            action_type="measure_next",
            title_vi="Đo vòng eo",
            why_vi="Vòng eo giúp đánh giá mỡ nội tạng — yếu tố nguy cơ kháng insulin quan trọng hơn cân nặng.",  # noqa: E501
            expected_benefit_vi="Vòng eo cho phép AI tính hội chứng chuyển hóa và đánh giá kháng insulin chính xác hơn.",  # noqa: E501
            effort_level="low",
            timeframe_vi="Hôm nay",
            confidence="high",
            evidence_level="established",
            related_markers=["waist_cm"],
        )

    rules.append(ActionRule("measure_waist", _waist_condition, _waist_score, _waist_build))

    # 3. get_hba1c
    def _hba1c_condition(findings, derived, ctx, domains):
        diabetes_level = _domain_level(domains, "diabetes_progression")
        return (
            _level_gte(diabetes_level, "needs_monitoring")
            and "hba1c" not in findings
        )

    def _hba1c_score(findings, derived, ctx, domains):
        level = _domain_level(domains, "diabetes_progression")
        if level == "discuss_with_doctor":
            return 80
        return 60

    def _hba1c_build(findings, derived, ctx, domains):
        return NextBestAction(
            action_id="get_hba1c",
            action_type="repeat_lab",
            title_vi="Làm thêm HbA1c",
            why_vi="HbA1c cho biết đường huyết trung bình 3 tháng — cần thiết để đánh giá nguy cơ tiểu đường chính xác hơn.",  # noqa: E501
            expected_benefit_vi="HbA1c giúp phân biệt tiền tiểu đường và tiểu đường, đồng thời phản ánh kiểm soát đường huyết dài hạn.",  # noqa: E501
            effort_level="low",
            timeframe_vi="Lần tái khám",
            confidence="high",
            evidence_level="established",
            related_markers=["hba1c", "fasting_glucose"],
        )

    rules.append(ActionRule("get_hba1c", _hba1c_condition, _hba1c_score, _hba1c_build))

    # 4. get_apob
    def _apob_condition(findings, derived, ctx, domains):
        cardio_level = _domain_level(domains, "cardiometabolic")
        return (
            _level_gte(cardio_level, "discuss_with_doctor")
            and "apob" not in findings
        )

    def _apob_score(findings, derived, ctx, domains):
        return 75

    def _apob_build(findings, derived, ctx, domains):
        return NextBestAction(
            action_id="get_apob",
            action_type="repeat_lab",
            title_vi="Trao đổi với bác sĩ về xét nghiệm ApoB",
            why_vi="ApoB đo trực tiếp số lượng hạt lipoprotein — chính xác hơn LDL khi TG cao hoặc đang dùng statin.",  # noqa: E501
            expected_benefit_vi="ApoB cho bức tranh nguy cơ tim mạch đầy đủ hơn LDL đơn lẻ, đặc biệt hữu ích khi có rối loạn lipid phức tạp.",  # noqa: E501
            effort_level="low",
            timeframe_vi="Lần tái khám",
            confidence="medium",
            evidence_level="moderate",
            related_markers=["apob", "ldl"],
        )

    rules.append(ActionRule("get_apob", _apob_condition, _apob_score, _apob_build))

    # 5. discuss_lipid_management
    def _lipid_discuss_condition(findings, derived, ctx, domains):
        cardio_level = _domain_level(domains, "cardiometabolic")
        return (
            _level_gte(cardio_level, "discuss_with_doctor")
            and not ctx.on_medication("statin")
        )

    def _lipid_discuss_score(findings, derived, ctx, domains):
        cardio_level = _domain_level(domains, "cardiometabolic")
        if cardio_level == "high_preventive_priority":
            return 85
        return 65

    def _lipid_discuss_build(findings, derived, ctx, domains):
        return NextBestAction(
            action_id="discuss_lipid_management",
            action_type="discuss_doctor",
            title_vi="Trao đổi với bác sĩ về kiểm soát mỡ máu",
            why_vi="Kết quả lipid hiện tại + bối cảnh sức khỏe cho thấy đây là thời điểm tốt để thảo luận chiến lược dài hạn.",  # noqa: E501
            expected_benefit_vi="Xây dựng kế hoạch kiểm soát lipid cá nhân hóa — bao gồm thay đổi lối sống và, nếu cần, liệu pháp thuốc.",  # noqa: E501
            effort_level="low",
            timeframe_vi="Lần tái khám",
            confidence="high",
            evidence_level="established",
            related_markers=["ldl", "total_cholesterol", "hdl", "triglyceride"],
        )

    rules.append(ActionRule("discuss_lipid_management", _lipid_discuss_condition, _lipid_discuss_score, _lipid_discuss_build))  # noqa: E501

    # 6. lifestyle_diet_fat
    def _diet_fat_condition(findings, derived, ctx, domains):
        cardio_level = _domain_level(domains, "cardiometabolic")
        fatty_level = _domain_level(domains, "fatty_liver_metabolic")
        ldl_status = _status(findings, "ldl")
        tg_status = _status(findings, "triglyceride")
        has_lipid_signal = (
            ldl_status in ("borderline", "high", "critical")
            or tg_status in ("borderline", "high", "critical")
            or _level_gte(cardio_level, "needs_monitoring")
            or _level_gte(fatty_level, "needs_monitoring")
        )
        return has_lipid_signal

    def _diet_fat_score(findings, derived, ctx, domains):
        return 55

    def _diet_fat_build(findings, derived, ctx, domains):
        return NextBestAction(
            action_id="lifestyle_diet_fat",
            action_type="lifestyle_today",
            title_vi="Giảm chất béo bão hòa và đường tinh luyện trong bữa ăn",
            why_vi="Chất béo bão hòa làm tăng LDL; đường tinh luyện làm tăng TG. Thay đổi này có tác động rõ trong 4–6 tuần.",  # noqa: E501
            expected_benefit_vi="Giảm LDL 5–15% và TG 10–20% sau 4–6 tuần nếu duy trì.",
            effort_level="medium",
            timeframe_vi="Hôm nay",
            confidence="high",
            evidence_level="established",
            related_markers=["ldl", "triglyceride", "total_cholesterol"],
        )

    rules.append(ActionRule("lifestyle_diet_fat", _diet_fat_condition, _diet_fat_score, _diet_fat_build))  # noqa: E501

    # 7. lifestyle_exercise
    def _exercise_condition(findings, derived, ctx, domains):
        return (
            (ctx.is_overweight() or ctx.has_metabolic_risk())
            and ctx.exercise_level in ("none", "light", "unknown")
        )

    def _exercise_score(findings, derived, ctx, domains):
        return 60

    def _exercise_build(findings, derived, ctx, domains):
        return NextBestAction(
            action_id="lifestyle_exercise",
            action_type="lifestyle_today",
            title_vi="Bắt đầu 30 phút đi bộ mỗi ngày",
            why_vi="Vận động aerobic cải thiện đồng thời HDL, TG, kháng insulin và huyết áp — tác động đa mục tiêu.",  # noqa: E501
            expected_benefit_vi="Sau 8–12 tuần: HDL tăng 5–10%, TG giảm 10–20%, cải thiện độ nhạy insulin và kiểm soát huyết áp.",  # noqa: E501
            effort_level="medium",
            timeframe_vi="Hôm nay",
            confidence="high",
            evidence_level="established",
            related_markers=["hdl", "triglyceride", "fasting_glucose"],
        )

    rules.append(ActionRule("lifestyle_exercise", _exercise_condition, _exercise_score, _exercise_build))  # noqa: E501

    # 8. complete_profile_waist
    def _profile_waist_condition(findings, derived, ctx, domains):
        return ctx.waist_cm is None and ctx.context_completeness < 0.7

    def _profile_waist_score(findings, derived, ctx, domains):
        return 45

    def _profile_waist_build(findings, derived, ctx, domains):
        return NextBestAction(
            action_id="complete_profile_waist",
            action_type="complete_profile",
            title_vi="Bổ sung vòng eo vào hồ sơ sức khỏe",
            why_vi="Vòng eo giúp AI đánh giá kháng insulin và hội chứng chuyển hóa chính xác hơn.",
            expected_benefit_vi="Thêm vòng eo giúp cải thiện độ chính xác đánh giá hội chứng chuyển hóa và nguy cơ tim mạch.",  # noqa: E501
            effort_level="low",
            timeframe_vi="Hôm nay",
            confidence="high",
            evidence_level="established",
            related_markers=["waist_cm"],
        )

    rules.append(ActionRule("complete_profile_waist", _profile_waist_condition, _profile_waist_score, _profile_waist_build))  # noqa: E501

    # 9. discuss_ckd_monitoring
    def _ckd_discuss_condition(findings, derived, ctx, domains):
        ckd_level = _domain_level(domains, "ckd_monitoring")
        return _level_gte(ckd_level, "needs_monitoring")

    def _ckd_discuss_score(findings, derived, ctx, domains):
        ckd_level = _domain_level(domains, "ckd_monitoring")
        if ckd_level == "discuss_with_doctor":
            return 75
        return 55

    def _ckd_discuss_build(findings, derived, ctx, domains):
        return NextBestAction(
            action_id="discuss_ckd_monitoring",
            action_type="discuss_doctor",
            title_vi="Kiểm tra creatinine và microalbumin niệu định kỳ",
            why_vi="Theo dõi chức năng thận sớm giúp làm chậm tiến triển và bảo vệ thận dài hạn.",
            expected_benefit_vi="Phát hiện sớm suy giảm chức năng thận để can thiệp kịp thời — trì hoãn tiến triển CKD lên đến nhiều năm.",  # noqa: E501
            effort_level="low",
            timeframe_vi="Lần tái khám",
            confidence="high",
            evidence_level="established",
            related_markers=["creatinine", "egfr_ckd_epi"],
        )

    rules.append(ActionRule("discuss_ckd_monitoring", _ckd_discuss_condition, _ckd_discuss_score, _ckd_discuss_build))  # noqa: E501

    # 10. maintain_current (fallback)
    def _maintain_condition(findings, derived, ctx, domains):
        all_low = all(d.level == "low_concern" for d in domains)
        return all_low and ctx.context_completeness >= 0.6

    def _maintain_score(findings, derived, ctx, domains):
        return 30

    def _maintain_build(findings, derived, ctx, domains):
        return NextBestAction(
            action_id="maintain_current",
            action_type="maintain_current",
            title_vi="Tiếp tục duy trì thói quen hiện tại",
            why_vi="Các chỉ số hiện tại trong giới hạn tốt. Duy trì chế độ ăn uống và vận động hiện tại.",  # noqa: E501
            expected_benefit_vi="Duy trì thói quen lành mạnh giúp bảo vệ sức khỏe tim mạch và chuyển hóa lâu dài.",  # noqa: E501
            effort_level="low",
            timeframe_vi="Hôm nay",
            confidence="medium",
            evidence_level="established",
            related_markers=[],
        )

    rules.append(ActionRule("maintain_current", _maintain_condition, _maintain_score, _maintain_build))  # noqa: E501

    return rules


_ACTION_REGISTRY: list[ActionRule] = _build_action_registry()

# ---------------------------------------------------------------------------
# Fallback action (always available)
# ---------------------------------------------------------------------------

_FALLBACK_ACTION = NextBestAction(
    action_id="maintain_current",
    action_type="maintain_current",
    title_vi="Tiếp tục duy trì thói quen hiện tại",
    why_vi="Không có hành động ưu tiên cao hơn cần thiết lúc này. Duy trì lối sống lành mạnh là điều tốt nhất.",  # noqa: E501
    expected_benefit_vi="Duy trì thói quen lành mạnh giúp bảo vệ sức khỏe lâu dài.",
    effort_level="low",
    timeframe_vi="Hôm nay",
    confidence="medium",
    evidence_level="established",
    related_markers=[],
)


# ---------------------------------------------------------------------------
# Engine Class
# ---------------------------------------------------------------------------


class NextBestActionEngine:
    """Engine 15 — Next Best Action Engine."""

    def generate(
        self,
        findings: dict,
        derived: dict,
        ctx: PatientContext,
        risk_domains: list[PreventiveRiskDomain],
        urgent_alerts: list,
    ) -> NextBestActionResult:
        """Score all eligible actions, sort descending, pick top 3.

        primary = rank 1; secondary = rank 2–3.
        If no action fires, return maintain_current as primary.
        """
        # Score all eligible actions
        scored: list[tuple[int, int, NextBestAction]] = []
        for rule in _ACTION_REGISTRY:
            try:
                if rule.condition(findings, derived, ctx, risk_domains):
                    score = rule.score(findings, derived, ctx, risk_domains)
                    action = rule.build(findings, derived, ctx, risk_domains)
                    type_priority = _TYPE_PRIORITY.get(action.action_type, 0)
                    scored.append((score, type_priority, action))
            except Exception:
                # Individual rule failure must not crash the engine
                continue

        if not scored:
            return NextBestActionResult(
                primary=_FALLBACK_ACTION,
                secondary=[],
                ranking_explanation_vi="Không có hành động ưu tiên cụ thể — các chỉ số hiện tại ổn định.",  # noqa: E501
            )

        # Sort: primary by score desc, secondary by type_priority desc (tie-break)
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        # Deduplicate by action_id
        seen_ids: set[str] = set()
        top: list[NextBestAction] = []
        for _score, _type_prio, action in scored:
            if action.action_id in seen_ids:
                continue
            seen_ids.add(action.action_id)
            top.append(action)
            if len(top) >= 3:
                break

        primary = top[0]
        secondary = top[1:3]

        explanation = self._ranking_explanation(primary, scored[0][0] if scored else 0)

        return NextBestActionResult(
            primary=primary,
            secondary=secondary,
            ranking_explanation_vi=explanation,
        )

    @staticmethod
    def _ranking_explanation(primary: NextBestAction, score: int) -> str:
        type_labels = {
            "discuss_doctor": "hành động lâm sàng quan trọng nhất",
            "repeat_lab": "xét nghiệm bổ sung có giá trị cao nhất",
            "measure_next": "phép đo tiếp theo có tác động cao nhất",
            "lifestyle_today": "thay đổi lối sống có tác động cao nhất",
            "complete_profile": "bổ sung hồ sơ có giá trị nhất",
            "maintain_current": "hành động phù hợp nhất hiện tại",
        }
        label = type_labels.get(primary.action_type, "hành động có giá trị cao nhất")
        return f'"{primary.title_vi}" được chọn là {label} dựa trên tác động lâm sàng và tính khả thi.'  # noqa: E501
