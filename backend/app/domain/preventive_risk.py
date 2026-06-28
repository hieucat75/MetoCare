"""Engine 14 — Preventive Risk Engine.

Estimates preventive risk domains from available lab findings + patient context.
Output is NOT disease prediction. Classifies:
  low_concern / needs_monitoring / discuss_with_doctor / high_preventive_priority

Each domain exposes:
  - contributing_factors: list[str]  — what triggered this level
  - missing_data: list[str]          — what would improve assessment
  - confidence: "high"|"medium"|"low"
  - evidence_level: "established"|"moderate"|"emerging"
  - safety_note_vi: str              — always present, conservative wording

Design: RiskDomainRule registry. Add new domains without touching engine class.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.domain.patient_context import PatientContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SAFETY_NOTE = (
    "Đây là đánh giá hỗ trợ giáo dục sức khỏe, không phải chẩn đoán y khoa. "
    "Mọi quyết định điều trị cần được bác sĩ xác nhận."
)

_LEVEL_VI: dict[str, str] = {
    "low_concern": "Không đáng lo ngại",
    "needs_monitoring": "Cần theo dõi",
    "discuss_with_doctor": "Nên trao đổi với bác sĩ",
    "high_preventive_priority": "Ưu tiên phòng ngừa cao",
}

_LEVEL_SEVERITY: dict[str, int] = {
    "high_preventive_priority": 3,
    "discuss_with_doctor": 2,
    "needs_monitoring": 1,
    "low_concern": 0,
}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PreventiveRiskDomain:
    domain_id: str          # "cardiometabolic" | "diabetes_progression" | "ckd_monitoring" |
                            # "fatty_liver_metabolic" | "cv_prevention_opportunity"
    display_name_vi: str
    level: str              # "low_concern"|"needs_monitoring"|"discuss_with_doctor"|"high_preventive_priority"  # noqa: E501
    level_vi: str           # Vietnamese label
    description_vi: str     # 1–2 sentences, conservative
    contributing_factors: list[str]   # canonicals or context flags that contributed
    missing_data: list[str]           # what would improve confidence
    confidence: str         # "high"|"medium"|"low"
    evidence_level: str     # "established"|"moderate"|"emerging"
    safety_note_vi: str     # always: "Đây là đánh giá hỗ trợ..."


# ---------------------------------------------------------------------------
# RiskDomainRule
# ---------------------------------------------------------------------------


@dataclass
class RiskDomainRule:
    domain_id: str
    display_name_vi: str
    evidence_level: str
    assess: Callable[[dict, dict, PatientContext, Any], PreventiveRiskDomain]


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


def _family_history_contains(profile: Any, keywords: list[str]) -> bool:
    if profile is None:
        return False
    fh = getattr(profile, "family_history", None) or ""
    fh_lower = fh.lower()
    return any(kw in fh_lower for kw in keywords)


def _level_vi(level: str) -> str:
    return _LEVEL_VI.get(level, level)


# ---------------------------------------------------------------------------
# Domain Rule Implementations
# ---------------------------------------------------------------------------


def _assess_cardiometabolic(
    findings: dict,
    derived: dict,
    ctx: PatientContext,
    profile: Any,
) -> PreventiveRiskDomain:
    """Domain 1: cardiometabolic risk."""
    factors: list[str] = []

    # Signal: LDL high/critical
    ldl_status = _status(findings, "ldl")
    if ldl_status in ("high", "critical"):
        factors.append("ldl_elevated")

    # Signal: TC/HDL ratio > 5
    tc_hdl = _derived_val(derived, "tc_hdl_ratio")
    if tc_hdl is not None and tc_hdl > 5.0:
        factors.append("tc_hdl_ratio_high")

    # Signal: LDL/HDL ratio > 3.5
    ldl_hdl = _derived_val(derived, "ldl_hdl_ratio")
    if ldl_hdl is not None and ldl_hdl > 3.5:
        factors.append("ldl_hdl_ratio_high")

    # Signal: CVD history
    if ctx.has_cvd_history:
        factors.append("has_cvd_history")

    # Signal: hypertension
    if ctx.has_hypertension:
        factors.append("has_hypertension")

    # Signal: CV risk high/very_high
    if ctx.cv_risk_category in ("high", "very_high"):
        factors.append(f"cv_risk_{ctx.cv_risk_category}")

    # Signal: smoker
    if ctx.is_smoker:
        factors.append("is_smoker")

    n = len(factors)
    if n >= 3 or ctx.has_cvd_history:
        level = "high_preventive_priority"
        desc = (
            "Nhiều yếu tố nguy cơ tim mạch đang hiện diện. "
            "Đây là ưu tiên phòng ngừa quan trọng — nên trao đổi với bác sĩ về chiến lược kiểm soát toàn diện."  # noqa: E501
        )
        confidence = "high"
    elif n == 2:
        level = "discuss_with_doctor"
        desc = (
            "Có hai yếu tố nguy cơ tim mạch đáng chú ý. "
            "Nên trao đổi với bác sĩ về kế hoạch theo dõi và can thiệp sớm."
        )
        confidence = "medium"
    elif n == 1:
        level = "needs_monitoring"
        desc = (
            "Có một tín hiệu nguy cơ tim mạch cần theo dõi. "
            "Duy trì lối sống lành mạnh và kiểm tra lại định kỳ."
        )
        confidence = "low"
    else:
        level = "low_concern"
        desc = "Không phát hiện tín hiệu nguy cơ tim mạch đáng lo ngại trong lần đánh giá này."
        confidence = "medium"

    missing = ["ApoB", "Lp(a)", "Huyết áp", "Tiền sử gia đình"]

    return PreventiveRiskDomain(
        domain_id="cardiometabolic",
        display_name_vi="Nguy cơ Tim mạch & Chuyển hóa",
        level=level,
        level_vi=_level_vi(level),
        description_vi=desc,
        contributing_factors=factors,
        missing_data=missing,
        confidence=confidence,
        evidence_level="established",
        safety_note_vi=_SAFETY_NOTE,
    )


def _assess_diabetes_progression(
    findings: dict,
    derived: dict,
    ctx: PatientContext,
    profile: Any,
) -> PreventiveRiskDomain:
    """Domain 2: diabetes progression risk."""
    factors: list[str] = []

    # Signal: fasting_glucose borderline/high/critical
    glc = _status(findings, "fasting_glucose")
    if glc in ("borderline", "high", "critical"):
        factors.append(f"fasting_glucose_{glc}")

    # Signal: hba1c borderline/high
    hba1c = _status(findings, "hba1c")
    if hba1c in ("borderline", "high"):
        factors.append(f"hba1c_{hba1c}")

    # Signal: TG/HDL > 3.0
    tg_hdl = _derived_val(derived, "tg_hdl_ratio")
    if tg_hdl is not None and tg_hdl > 3.0:
        factors.append("tg_hdl_ratio_high")

    # Signal: TyG index > 9.0
    tyg = _derived_val(derived, "tyg_index")
    if tyg is not None and tyg > 9.0:
        factors.append("tyg_index_high")

    # Signal: has_diabetes
    if ctx.has_diabetes:
        factors.append("has_diabetes")

    # Signal: overweight
    if ctx.is_overweight():
        factors.append("is_overweight")

    # Signal: family history of diabetes
    if _family_history_contains(profile, ["tiểu đường", "diabetes", "đái tháo đường"]):
        factors.append("family_history_diabetes")

    # Determine level
    already_diabetic = ctx.has_diabetes
    glucose_high = glc in ("high", "critical")
    hba1c_high = hba1c in ("high",)

    if already_diabetic and (glucose_high or hba1c_high):
        level = "discuss_with_doctor"
        desc = (
            "Đường huyết hoặc HbA1c đang ở mức cao trong bối cảnh đã có tiểu đường. "
            "Nên trao đổi với bác sĩ về việc điều chỉnh kế hoạch kiểm soát đường huyết."
        )
        confidence = "high"
    elif not already_diabetic and len(factors) >= 3:
        level = "discuss_with_doctor"
        desc = (
            "Có nhiều tín hiệu gợi ý nguy cơ tiến triển đường huyết. "
            "Nên trao đổi với bác sĩ về tầm soát tiền tiểu đường và can thiệp lối sống sớm."
        )
        confidence = "high"
    elif len(factors) >= 2:
        level = "needs_monitoring"
        desc = (
            "Có một số tín hiệu đáng theo dõi liên quan đến chuyển hóa đường. "
            "Theo dõi định kỳ và duy trì lối sống lành mạnh."
        )
        confidence = "medium"
    elif len(factors) == 1:
        level = "needs_monitoring"
        desc = (
            "Có một tín hiệu nhỏ liên quan đến chuyển hóa đường. "
            "Tiếp tục theo dõi — một tín hiệu đơn lẻ chưa đủ để kết luận."
        )
        confidence = "low"
    else:
        level = "low_concern"
        desc = "Không phát hiện tín hiệu nguy cơ tiểu đường đáng lo ngại trong lần đánh giá này."
        confidence = "medium"

    missing_data = ["Vòng eo"]
    if "hba1c" not in findings:
        missing_data.insert(0, "HbA1c")
    missing_data.append("Insulin lúc đói (HOMA-IR)")

    return PreventiveRiskDomain(
        domain_id="diabetes_progression",
        display_name_vi="Nguy cơ Tiểu đường / Tiền tiểu đường",
        level=level,
        level_vi=_level_vi(level),
        description_vi=desc,
        contributing_factors=factors,
        missing_data=missing_data,
        confidence=confidence,
        evidence_level="established",
        safety_note_vi=_SAFETY_NOTE,
    )


def _assess_ckd_monitoring(
    findings: dict,
    derived: dict,
    ctx: PatientContext,
    profile: Any,
) -> PreventiveRiskDomain:
    """Domain 3: CKD monitoring."""
    factors: list[str] = []

    creat_status = _status(findings, "creatinine")
    egfr = _derived_val(derived, "egfr_ckd_epi")

    if creat_status == "critical":
        factors.append("creatinine_critical")
    elif creat_status == "high":
        factors.append("creatinine_high")

    if egfr is not None:
        if egfr < 45:
            factors.append("egfr_below_45")
        elif egfr < 60:
            factors.append("egfr_below_60")

    if ctx.has_ckd:
        factors.append("has_ckd")

    if ctx.has_diabetes:
        factors.append("has_diabetes_risk")

    if ctx.has_hypertension:
        factors.append("has_hypertension_risk")

    # Determine level
    if creat_status == "critical" or (egfr is not None and egfr < 45):
        level = "high_preventive_priority"
        desc = (
            "Creatinine hoặc eGFR ở mức đáng lo ngại — có thể gợi ý suy giảm chức năng thận đáng kể. "  # noqa: E501
            "Đây là ưu tiên theo dõi cao — nên gặp bác sĩ sớm."
        )
        confidence = "high"
    elif creat_status == "high" or (egfr is not None and egfr < 60):
        level = "discuss_with_doctor"
        desc = (
            "Creatinine tăng hoặc eGFR giảm — nên trao đổi với bác sĩ về kế hoạch theo dõi chức năng thận. "  # noqa: E501
            "Phát hiện sớm giúp làm chậm tiến triển."
        )
        confidence = "high" if creat_status == "high" else "medium"
    elif ctx.has_ckd:
        level = "needs_monitoring"
        desc = (
            "Tiền sử bệnh thận mạn — cần theo dõi chức năng thận định kỳ ngay cả khi xét nghiệm hiện tại chưa có kết quả thận. "  # noqa: E501
        )
        confidence = "medium"
    elif ctx.has_diabetes or ctx.has_hypertension:
        level = "needs_monitoring"
        desc = (
            "Tiểu đường và tăng huyết áp là hai nguyên nhân hàng đầu của bệnh thận mạn. "
            "Nên tầm soát chức năng thận định kỳ — creatinine và microalbumin niệu."
        )
        confidence = "medium"
    else:
        level = "low_concern"
        desc = "Không phát hiện tín hiệu lo ngại về chức năng thận trong lần đánh giá này."
        confidence = "medium"

    return PreventiveRiskDomain(
        domain_id="ckd_monitoring",
        display_name_vi="Theo dõi chức năng Thận",
        level=level,
        level_vi=_level_vi(level),
        description_vi=desc,
        contributing_factors=factors,
        missing_data=["eGFR (CKD-EPI)", "Microalbumin niệu", "Tổng phân tích nước tiểu"],
        confidence=confidence,
        evidence_level="established",
        safety_note_vi=_SAFETY_NOTE,
    )


def _assess_fatty_liver_metabolic(
    findings: dict,
    derived: dict,
    ctx: PatientContext,
    profile: Any,
) -> PreventiveRiskDomain:
    """Domain 4: fatty liver / metabolic."""
    factors: list[str] = []

    alt_status = _status(findings, "alt")
    ast_status = _status(findings, "ast")
    tg_status = _status(findings, "triglyceride")

    if alt_status == "critical":
        factors.append("alt_critical")
    elif alt_status == "high":
        factors.append("alt_high")

    if ast_status == "critical":
        factors.append("ast_critical")
    elif ast_status == "high":
        factors.append("ast_high")

    if tg_status in ("high", "critical"):
        factors.append("tg_high")

    if ctx.is_overweight():
        factors.append("is_overweight")

    if ctx.has_fatty_liver:
        factors.append("has_fatty_liver")

    # Determine level
    if alt_status == "critical" or (alt_status == "high" and ast_status == "high" and tg_status in ("high", "critical")):  # noqa: E501
        level = "discuss_with_doctor"
        desc = (
            "Men gan tăng cao kết hợp với các tín hiệu chuyển hóa — có thể gợi ý gan nhiễm mỡ chuyển hóa. "  # noqa: E501
            "Nên trao đổi với bác sĩ để đánh giá toàn diện hơn."
        )
        confidence = "high"
    elif alt_status == "high" and (tg_status in ("high", "critical") or ctx.is_overweight() or ctx.has_fatty_liver):  # noqa: E501
        level = "needs_monitoring"
        desc = (
            "ALT tăng kết hợp với một yếu tố chuyển hóa khác — cần theo dõi định kỳ. "
            "Thay đổi lối sống có thể giúp cải thiện đáng kể."
        )
        confidence = "medium"
    elif ctx.has_fatty_liver:
        level = "needs_monitoring"
        desc = (
            "Tiền sử gan nhiễm mỡ — cần theo dõi men gan và các chỉ số chuyển hóa định kỳ "
            "ngay cả khi xét nghiệm hiện tại chưa có kết quả bất thường."
        )
        confidence = "medium"
    else:
        level = "low_concern"
        desc = "Không phát hiện tín hiệu đáng lo ngại về gan chuyển hóa trong lần đánh giá này."
        confidence = "medium"

    return PreventiveRiskDomain(
        domain_id="fatty_liver_metabolic",
        display_name_vi="Gan nhiễm mỡ & Chuyển hóa",
        level=level,
        level_vi=_level_vi(level),
        description_vi=desc,
        contributing_factors=factors,
        missing_data=["GGT", "Siêu âm gan", "FIB-4 score", "Viêm gan B/C (HBsAg, anti-HCV)"],
        confidence=confidence,
        evidence_level="moderate",
        safety_note_vi=_SAFETY_NOTE,
    )


def _assess_cv_prevention_opportunity(
    findings: dict,
    derived: dict,
    ctx: PatientContext,
    profile: Any,
) -> PreventiveRiskDomain:
    """Domain 5: CV prevention opportunity (positive framing)."""
    factors: list[str] = []

    if ctx.cv_risk_category in ("intermediate", "high", "very_high"):
        factors.append(f"cv_risk_{ctx.cv_risk_category}")

    if ctx.is_smoker:
        factors.append("is_smoker")

    ldl_status = _status(findings, "ldl")
    if ldl_status in ("borderline", "high", "critical"):
        factors.append("ldl_elevated")

    # Age factors (sex-aware)
    if ctx.age is not None and ctx.sex == "male" and ctx.age >= 40:
        factors.append("age_male_40plus")
    if ctx.age is not None and ctx.sex == "female" and ctx.age >= 50:
        factors.append("age_female_50plus")

    if ctx.has_hypertension:
        factors.append("has_hypertension")

    # Secondary prevention — always include
    if ctx.has_cvd_history:
        factors.append("has_cvd_history")
        level = "high_preventive_priority"
        desc = (
            "Đây là cơ hội phòng ngừa thứ phát quan trọng. "
            "Với tiền sử bệnh tim mạch, việc kiểm soát các yếu tố nguy cơ tích cực giúp giảm nguy cơ tái phát biến cố đáng kể."  # noqa: E501
        )
        confidence = "high"
    elif ctx.cv_risk_category == "very_high":
        level = "high_preventive_priority"
        desc = (
            "Đây là cơ hội phòng ngừa tim mạch ưu tiên cao. "
            "Các yếu tố nguy cơ hiện tại gợi ý nguy cơ tim mạch cao — hành động phòng ngừa sớm mang lại lợi ích lớn nhất."  # noqa: E501
        )
        confidence = "high"
    elif ctx.cv_risk_category == "high":
        level = "discuss_with_doctor"
        desc = (
            "Đây là cơ hội phòng ngừa tim mạch tốt. "
            "Trao đổi với bác sĩ về chiến lược giảm nguy cơ — bao gồm lối sống và theo dõi định kỳ."
        )
        confidence = "medium"
    elif ctx.cv_risk_category == "intermediate" or len(factors) >= 2:
        level = "needs_monitoring"
        desc = (
            "Đây là cơ hội phòng ngừa tim mạch ở mức độ vừa. "
            "Theo dõi định kỳ và duy trì lối sống lành mạnh là bước tốt nhất hiện tại."
        )
        confidence = "medium"
    else:
        level = "low_concern"
        desc = (
            "Không có yếu tố nguy cơ tim mạch đáng lo ngại trong lần đánh giá này. "
            "Tiếp tục duy trì lối sống lành mạnh."
        )
        confidence = "medium"

    return PreventiveRiskDomain(
        domain_id="cv_prevention_opportunity",
        display_name_vi="Cơ hội Phòng ngừa Tim mạch",
        level=level,
        level_vi=_level_vi(level),
        description_vi=desc,
        contributing_factors=factors,
        missing_data=["Huyết áp", "CT Calcium Score", "ApoB"],
        confidence=confidence,
        evidence_level="established",
        safety_note_vi=_SAFETY_NOTE,
    )


# ---------------------------------------------------------------------------
# Rule Registry
# ---------------------------------------------------------------------------

_DOMAIN_REGISTRY: list[RiskDomainRule] = [
    RiskDomainRule(
        domain_id="cardiometabolic",
        display_name_vi="Nguy cơ Tim mạch & Chuyển hóa",
        evidence_level="established",
        assess=_assess_cardiometabolic,
    ),
    RiskDomainRule(
        domain_id="diabetes_progression",
        display_name_vi="Nguy cơ Tiểu đường / Tiền tiểu đường",
        evidence_level="established",
        assess=_assess_diabetes_progression,
    ),
    RiskDomainRule(
        domain_id="ckd_monitoring",
        display_name_vi="Theo dõi chức năng Thận",
        evidence_level="established",
        assess=_assess_ckd_monitoring,
    ),
    RiskDomainRule(
        domain_id="fatty_liver_metabolic",
        display_name_vi="Gan nhiễm mỡ & Chuyển hóa",
        evidence_level="moderate",
        assess=_assess_fatty_liver_metabolic,
    ),
    RiskDomainRule(
        domain_id="cv_prevention_opportunity",
        display_name_vi="Cơ hội Phòng ngừa Tim mạch",
        evidence_level="established",
        assess=_assess_cv_prevention_opportunity,
    ),
]


# ---------------------------------------------------------------------------
# Engine Class
# ---------------------------------------------------------------------------


class PreventiveRiskEngine:
    """Engine 14 — assesses preventive risk domains from findings and context."""

    def assess(
        self,
        findings: dict,     # {canonical: {"status": ...}}
        derived: dict,      # {canonical: float | DerivedMetricResult}
        ctx: PatientContext,
        profile: Any = None,  # PatientProfile for family_history
    ) -> list[PreventiveRiskDomain]:
        """Run all domain rules, return list sorted by level severity (high first)."""
        domains: list[PreventiveRiskDomain] = []
        for rule in _DOMAIN_REGISTRY:
            domain = rule.assess(findings, derived, ctx, profile)
            domains.append(domain)

        # Sort by severity descending
        domains.sort(key=lambda d: -_LEVEL_SEVERITY.get(d.level, 0))
        return domains
