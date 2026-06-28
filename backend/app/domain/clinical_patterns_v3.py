"""Engine 2 — Cross-Marker Correlation Engine v3.

Detects clinically meaningful multi-marker patterns.
Returns ClinicalPattern (richer than legacy PatternDetection).

Rules:
- No hardcoded single-biomarker logic — patterns require ≥2 signals.
- Context-aware: PatientContext modifies severity and clinical_significance_vi.
- All patterns use "có thể gợi ý" / "phù hợp với" — never diagnose.
- Pattern registry is a list of PatternRule; add new patterns without touching engine code.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.domain.patient_context import PatientContext


@dataclass
class ClinicalPattern:
    pattern_id: str
    display_name_vi: str
    description_vi: str
    severity: str                           # "info"|"watch"|"warning"|"urgent"
    supporting_findings: list[str]          # canonicals that triggered
    confidence: str                         # "high"|"medium"|"low"
    evidence_based: bool
    evidence_source: str                    # "established"|"moderate"|"emerging"
    reasoning_vi: str                       # Why these markers → this pattern
    clinical_significance_vi: str          # What it means for the patient
    context_modifiers: list[str] = field(default_factory=list)   # How context changes interpretation
    recommended_additional_tests: list[str] = field(default_factory=list)
    limitation_vi: str = ""


# ── Pattern Rule ──────────────────────────────────────────────────────────────

@dataclass
class PatternRule:
    pattern_id: str
    display_name_vi: str
    base_severity: str
    evidence_source: str
    # detector: receives (findings_dict, derived_dict, ctx) → list[str] of matching canonicals or []
    detector: Callable[[dict, dict, PatientContext], list[str]]
    build_pattern: Callable[[list[str], PatientContext], ClinicalPattern]


# ── Helper ────────────────────────────────────────────────────────────────────

def _has(findings: dict, derived: dict, canonical: str) -> bool:
    return canonical in findings or canonical in derived

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

def _confidence(n: int, has_derived: bool = False) -> str:
    if n >= 3 or (n >= 2 and has_derived):
        return "high"
    if n == 2:
        return "medium"
    return "low"


# ── Pattern Registry ──────────────────────────────────────────────────────────

def _register_patterns() -> list[PatternRule]:
    rules: list[PatternRule] = []

    # 1. Insulin Resistance
    def _ir_detect(findings, derived, ctx):
        signals = []
        tyg = _derived_val(derived, "tyg_index")
        if tyg is not None and tyg > 9.0:
            signals.append("tyg_index")
        tg_hdl = _derived_val(derived, "tg_hdl_ratio")
        if tg_hdl is not None and tg_hdl > 3.0:
            signals.append("tg_hdl_ratio")
        if _status(findings, "fasting_glucose") in ("high", "borderline", "critical"):
            signals.append("fasting_glucose")
        if _status(findings, "triglyceride") in ("high", "borderline", "critical"):
            signals.append("triglyceride")
        if _status(findings, "hdl") in ("low",):
            signals.append("hdl")
        return signals if len(signals) >= 2 else []

    def _ir_build(signals, ctx):
        ctx_mods = []
        severity = "warning"
        significance = "Mẫu hình này có thể gợi ý tình trạng kháng insulin — tế bào cơ thể phản ứng kém với insulin, khiến tụy phải tăng sản xuất để duy trì đường huyết."
        if ctx.has_diabetes:
            ctx_mods.append("Bệnh nhân đã có chẩn đoán tiểu đường — kháng insulin là yếu tố nền quan trọng cần kiểm soát.")
            severity = "urgent"
        elif ctx.is_overweight():
            ctx_mods.append(f"BMI {ctx.bmi} — thừa cân làm tăng nguy cơ kháng insulin. Giảm cân có thể cải thiện đáng kể các chỉ số.")
        if ctx.on_medication("metformin"):
            ctx_mods.append("Đang dùng metformin — các chỉ số đường huyết cần xem trong bối cảnh điều trị.")
        return ClinicalPattern(
            pattern_id="insulin_resistance",
            display_name_vi="Dấu hiệu kháng insulin",
            description_vi="Mẫu hình chỉ số gợi ý tình trạng kháng insulin.",
            severity=severity,
            supporting_findings=signals,
            confidence=_confidence(len(signals), "tyg_index" in signals),
            evidence_based=True,
            evidence_source="moderate",
            reasoning_vi="TyG Index và tỷ lệ TG/HDL là chỉ số tầm soát gián tiếp kháng insulin. Khi kết hợp với glucose và TG cao, HDL thấp — mẫu hình này phù hợp với rối loạn chuyển hóa insulin.",
            clinical_significance_vi=significance,
            context_modifiers=ctx_mods,
            recommended_additional_tests=["Insulin lúc đói (HOMA-IR)", "HbA1c", "Vòng eo"],
            limitation_vi="TyG và TG/HDL là chỉ số tầm soát — không thay thế đo insulin máu hoặc HOMA-IR để xác nhận chẩn đoán.",
        )

    rules.append(PatternRule("insulin_resistance", "Dấu hiệu kháng insulin", "warning", "moderate", _ir_detect, _ir_build))

    # 2. Atherogenic Cholesterol Pattern
    def _ath_detect(findings, derived, ctx):
        signals = []
        ldl_fw = _derived_val(derived, "ldl_friedewald")
        if ldl_fw is not None and ldl_fw > 130:  # mg/dL
            signals.append("ldl_friedewald")
        if _status(findings, "ldl") in ("high", "critical"):
            signals.append("ldl")
        non_hdl = _derived_val(derived, "non_hdl_cholesterol")
        if non_hdl is not None and non_hdl > 4.1:  # mmol/L
            signals.append("non_hdl_cholesterol")
        if _status(findings, "total_cholesterol") in ("high", "critical"):
            signals.append("total_cholesterol")
        tc_hdl = _derived_val(derived, "tc_hdl_ratio")
        if tc_hdl is not None and tc_hdl > 5.0:
            signals.append("tc_hdl_ratio")
        return signals if len(signals) >= 2 else []

    def _ath_build(signals, ctx):
        ctx_mods = []
        severity = "warning"
        if ctx.has_cvd_history:
            ctx_mods.append("Tiền sử bệnh tim mạch — ngưỡng LDL mục tiêu cần nghiêm ngặt hơn (<1.8 mmol/L). Cần trao đổi với bác sĩ về điều trị tích cực hơn.")
            severity = "urgent"
        elif ctx.has_diabetes:
            ctx_mods.append("Tiểu đường làm tăng gấp đôi nguy cơ tim mạch — mẫu hình tăng cholesterol trong bối cảnh này cần được ưu tiên xử lý.")
            severity = "warning"
        if ctx.on_medication("statin"):
            ctx_mods.append("Đang dùng statin — LDL vẫn cao có thể cần điều chỉnh liều hoặc thêm thuốc (cần bác sĩ đánh giá).")
        return ClinicalPattern(
            pattern_id="atherogenic_cholesterol",
            display_name_vi="Mẫu hình cholesterol sinh xơ vữa",
            description_vi="LDL và Non-HDL đều tăng — gợi ý tăng gánh nặng lipoprotein sinh xơ vữa.",
            severity=severity,
            supporting_findings=signals,
            confidence=_confidence(len(signals), "ldl_friedewald" in signals or "non_hdl_cholesterol" in signals),
            evidence_based=True,
            evidence_source="established",
            reasoning_vi="LDL tăng + Non-HDL tăng = tăng gánh nặng tổng thể của các lipoprotein mang cholesterol vào thành mạch. Đây là mẫu hình rõ nhất của tăng cholesterol đơn thuần (hypercholesterolemia).",
            clinical_significance_vi="Mẫu hình này liên quan đến nguy cơ xơ vữa động mạch nếu kéo dài nhiều năm. Mức độ nguy cơ phụ thuộc vào bối cảnh toàn thân.",
            context_modifiers=ctx_mods,
            recommended_additional_tests=["ApoB", "Lp(a)", "CT Calcium Score (nếu nguy cơ trung bình)"],
            limitation_vi="Friedewald LDL không chính xác khi TG ≥ 4.5 mmol/L. ApoB cho bức tranh chính xác hơn về số lượng hạt lipoprotein.",
        )

    rules.append(PatternRule("atherogenic_cholesterol", "Cholesterol sinh xơ vữa", "warning", "established", _ath_detect, _ath_build))

    # 3. Dyslipidemia (TG↑ HDL↓ pattern)
    def _dys_detect(findings, derived, ctx):
        signals = []
        if _status(findings, "triglyceride") in ("high", "borderline", "critical"):
            signals.append("triglyceride")
        if _status(findings, "hdl") in ("low",):
            signals.append("hdl")
        tg_hdl = _derived_val(derived, "tg_hdl_ratio")
        if tg_hdl is not None and tg_hdl > 2.5:
            signals.append("tg_hdl_ratio")
        return signals if len(signals) >= 2 else []

    def _dys_build(signals, ctx):
        ctx_mods = []
        if ctx.has_diabetes or ctx.is_overweight():
            ctx_mods.append("TG cao + HDL thấp trong bối cảnh thừa cân/tiểu đường thường phản ánh rối loạn lipid nguồn gốc chuyển hóa.")
        if ctx.on_medication("statin"):
            ctx_mods.append("Statin ít tác dụng lên TG và HDL — fibrate hoặc omega-3 có thể phù hợp hơn (cần bác sĩ).")
        return ClinicalPattern(
            pattern_id="hypertriglyceridemia_low_hdl",
            display_name_vi="TG cao — HDL thấp",
            description_vi="Tỷ lệ TG/HDL bất lợi — gợi ý rối loạn lipid máu chuyển hóa.",
            severity="watch",
            supporting_findings=signals,
            confidence=_confidence(len(signals), "tg_hdl_ratio" in signals),
            evidence_based=True,
            evidence_source="established",
            reasoning_vi="TG cao + HDL thấp tạo ra tỷ lệ TG/HDL bất lợi — mẫu hình liên quan đến rối loạn lipid nguồn gốc chuyển hóa, thường đi kèm kháng insulin.",
            clinical_significance_vi="Mẫu hình này có thể gợi ý rối loạn lipid máu chuyển hóa (metabolic dyslipidemia). Không nguy hiểm ngay, nhưng cần kiểm soát dài hạn.",
            context_modifiers=ctx_mods,
            recommended_additional_tests=["TyG Index", "Insulin lúc đói", "HbA1c"],
            limitation_vi="TG/HDL là chỉ số tầm soát — không thay thế đánh giá nguy cơ tim mạch toàn diện.",
        )

    rules.append(PatternRule("hypertriglyceridemia_low_hdl", "TG cao — HDL thấp", "watch", "established", _dys_detect, _dys_build))

    # 4. Hepatic Metabolic Pattern (MAFLD proxy)
    def _mafld_detect(findings, derived, ctx):
        signals = []
        if _status(findings, "alt") in ("high", "critical"):
            signals.append("alt")
        if _status(findings, "ast") in ("high", "critical"):
            signals.append("ast")
        if _status(findings, "triglyceride") in ("high", "borderline", "critical"):
            signals.append("triglyceride")
        if ctx.is_overweight() and "alt" in signals:
            signals.append("bmi_proxy")
        return signals if len(signals) >= 2 else []

    def _mafld_build(signals, ctx):
        ctx_mods = []
        if ctx.is_overweight():
            ctx_mods.append(f"BMI {ctx.bmi} — thừa cân là yếu tố nguy cơ hàng đầu của gan nhiễm mỡ không do rượu.")
        if ctx.drinks_alcohol:
            ctx_mods.append("Uống rượu — cần phân biệt gan nhiễm mỡ do rượu (ALD) và không do rượu (NAFLD). Tỷ lệ AST/ALT có thể giúp phân biệt.")
        return ClinicalPattern(
            pattern_id="hepatic_metabolic",
            display_name_vi="Mẫu hình gan chuyển hóa",
            description_vi="ALT/AST tăng kết hợp TG cao — có thể gợi ý gan nhiễm mỡ chuyển hóa.",
            severity="watch",
            supporting_findings=[s for s in signals if s != "bmi_proxy"],
            confidence=_confidence(len(signals), False),
            evidence_based=True,
            evidence_source="moderate",
            reasoning_vi="ALT tăng là dấu hiệu tổn thương tế bào gan. Khi kết hợp với TG cao (và thừa cân), mẫu hình này phù hợp với gan nhiễm mỡ chuyển hóa (MAFLD — Metabolic-associated Fatty Liver Disease).",
            clinical_significance_vi="MAFLD có thể tiến triển thành xơ hóa gan nếu không kiểm soát. Giai đoạn sớm thường hồi phục tốt với thay đổi lối sống.",
            context_modifiers=ctx_mods,
            recommended_additional_tests=["Siêu âm gan", "FIB-4", "Viêm gan B/C (anti-HBs, anti-HCV)"],
            limitation_vi="Chẩn đoán xác định MAFLD cần siêu âm hoặc sinh thiết gan — không thể kết luận chỉ từ xét nghiệm máu.",
        )

    rules.append(PatternRule("hepatic_metabolic", "Gan chuyển hóa", "watch", "moderate", _mafld_detect, _mafld_build))

    # 5. Metabolic Syndrome Full Pattern
    def _ms_detect(findings, derived, ctx):
        signals = []
        ms = derived.get("metabolic_syndrome")
        if isinstance(ms, dict) and ms.get("status") == "meets_criteria":
            return ["metabolic_syndrome"]
        # Manual check if metabolic_syndrome not in derived
        if _status(findings, "triglyceride") in ("high", "borderline", "critical"):
            signals.append("triglyceride")
        if _status(findings, "hdl") in ("low",):
            signals.append("hdl")
        if _status(findings, "fasting_glucose") in ("high", "borderline", "critical"):
            signals.append("fasting_glucose")
        if ctx.has_hypertension:
            signals.append("blood_pressure")
        if ctx.waist_cm:
            waist_threshold = 90 if ctx.sex == "male" else 80
            if ctx.waist_cm >= waist_threshold:
                signals.append("waist")
        return signals if len(signals) >= 3 else []

    def _ms_build(signals, ctx):
        ctx_mods = []
        if ctx.has_diabetes:
            ctx_mods.append("Hội chứng chuyển hóa trên nền tiểu đường làm tăng đáng kể nguy cơ tim mạch. Cần kiểm soát đồng thời nhiều yếu tố nguy cơ.")
        return ClinicalPattern(
            pattern_id="metabolic_syndrome",
            display_name_vi="Hội chứng chuyển hóa",
            description_vi="Mẫu hình đa yếu tố phù hợp với hội chứng chuyển hóa.",
            severity="warning",
            supporting_findings=signals,
            confidence="high" if len(signals) >= 3 else "medium",
            evidence_based=True,
            evidence_source="established",
            reasoning_vi="Hội chứng chuyển hóa được xác định khi có ≥3 trong 5 tiêu chí (IDF/AHA 2009): TG tăng, HDL thấp, glucose tăng, huyết áp cao, vòng eo lớn.",
            clinical_significance_vi="Hội chứng chuyển hóa làm tăng gấp 2–5 lần nguy cơ tiểu đường loại 2 và bệnh tim mạch so với người không mắc.",
            context_modifiers=ctx_mods,
            recommended_additional_tests=["HOMA-IR", "HbA1c", "Vòng eo (nếu chưa đo)", "Huyết áp 24h"],
            limitation_vi="Hội chứng chuyển hóa là khái niệm lâm sàng — không phải chẩn đoán bệnh. Cần bác sĩ xác nhận và đánh giá toàn diện.",
        )

    rules.append(PatternRule("metabolic_syndrome", "Hội chứng chuyển hóa", "warning", "established", _ms_detect, _ms_build))

    # 6. Kidney Risk Pattern
    def _ckd_detect(findings, derived, ctx):
        signals = []
        if _status(findings, "creatinine") in ("high", "critical"):
            signals.append("creatinine")
        egfr = _derived_val(derived, "egfr_ckd_epi")
        if egfr is not None and egfr < 60:
            signals.append("egfr_ckd_epi")
        if ctx.has_diabetes:
            signals.append("diabetes_context")
        if ctx.has_hypertension:
            signals.append("hypertension_context")
        return signals if ("creatinine" in signals or "egfr_ckd_epi" in signals) else []

    def _ckd_build(signals, ctx):
        ctx_mods = []
        severity = "watch"
        if ctx.has_diabetes:
            ctx_mods.append("Tiểu đường là nguyên nhân hàng đầu của bệnh thận mạn tính. Cần kiểm tra microalbumin niệu mỗi năm.")
            severity = "warning"
        if ctx.has_hypertension:
            ctx_mods.append("Tăng huyết áp làm tổn thương mao mạch thận theo thời gian. Kiểm soát huyết áp tốt giúp bảo vệ thận.")
        return ClinicalPattern(
            pattern_id="kidney_risk",
            display_name_vi="Tín hiệu chức năng thận",
            description_vi="Creatinine hoặc eGFR bất thường — cần theo dõi chức năng thận.",
            severity=severity,
            supporting_findings=[s for s in signals if not s.endswith("_context")],
            confidence=_confidence(sum(1 for s in signals if not s.endswith("_context")), "egfr_ckd_epi" in signals),
            evidence_based=True,
            evidence_source="established",
            reasoning_vi="Creatinine tăng hoặc eGFR giảm phản ánh khả năng lọc thận suy giảm. eGFR < 60 mL/min/1.73m² kéo dài ≥3 tháng là tiêu chí Bệnh thận mạn tính (CKD) — KDIGO 2022.",
            clinical_significance_vi="Suy giảm chức năng thận ảnh hưởng đến chuyển hóa thuốc, độc chất và cân bằng điện giải. Phát hiện sớm giúp làm chậm tiến triển.",
            context_modifiers=ctx_mods,
            recommended_additional_tests=["Microalbumin niệu", "Tổng phân tích nước tiểu", "Điện giải đồ", "Xét nghiệm lại creatinine sau 3 tháng"],
            limitation_vi="Một kết quả creatinine cao có thể do mất nước tạm thời. Cần xác nhận bằng ít nhất 2 lần đo cách nhau ≥3 tháng trước khi kết luận CKD.",
        )

    rules.append(PatternRule("kidney_risk", "Thận", "watch", "established", _ckd_detect, _ckd_build))

    # 7. Inflammatory Process Pattern
    def _inflam_detect(findings, derived, ctx):
        signals = []
        if _status(findings, "crp") in ("high", "critical"):
            signals.append("crp")
        if _status(findings, "ferritin") in ("high", "critical"):
            signals.append("ferritin")
        if _status(findings, "wbc") in ("high", "critical"):
            signals.append("wbc")
        return signals if len(signals) >= 2 else []

    def _inflam_build(signals, ctx):
        ctx_mods = []
        if ctx.has_cvd_history:
            ctx_mods.append("CRP cao trong bối cảnh tiền sử tim mạch — viêm mạn tính là yếu tố nguy cơ độc lập của tái phát biến cố tim mạch.")
        return ClinicalPattern(
            pattern_id="inflammatory_process",
            display_name_vi="Tín hiệu viêm",
            description_vi="CRP và/hoặc Ferritin tăng — có thể gợi ý quá trình viêm đang diễn ra.",
            severity="watch",
            supporting_findings=signals,
            confidence=_confidence(len(signals)),
            evidence_based=True,
            evidence_source="moderate",
            reasoning_vi="CRP (C-Reactive Protein) và Ferritin đều tăng khi có viêm cấp hoặc mạn tính. Tăng đồng thời gợi ý phản ứng viêm có ý nghĩa lâm sàng.",
            clinical_significance_vi="Viêm mạn tính liên quan đến nhiều bệnh: nhiễm trùng, tự miễn, ung thư, bệnh tim mạch. Cần xác định nguyên nhân.",
            context_modifiers=ctx_mods,
            recommended_additional_tests=["Công thức máu toàn bộ", "ESR", "Kiểm tra nhiễm trùng tiềm ẩn"],
            limitation_vi="CRP và Ferritin tăng không đặc hiệu — có thể do rất nhiều nguyên nhân. Không thể kết luận nguyên nhân chỉ từ hai chỉ số này.",
        )

    rules.append(PatternRule("inflammatory_process", "Viêm", "watch", "moderate", _inflam_detect, _inflam_build))

    # 8. Thyroid Pattern
    def _thyroid_detect(findings, derived, ctx):
        signals = []
        if _has(findings, derived, "tsh"):
            signals.append("tsh")
        if _has(findings, derived, "ft4"):
            signals.append("ft4")
        if _has(findings, derived, "ft3"):
            signals.append("ft3")
        tsh_status = _status(findings, "tsh")
        if tsh_status not in ("high", "low", "critical"):
            return []  # Only flag if TSH is actually abnormal
        return signals

    def _thyroid_build(signals, ctx):
        ctx_mods = []
        if ctx.on_medication("levothyroxine"):
            ctx_mods.append("Đang dùng levothyroxine — kết quả tuyến giáp cần xem trong bối cảnh điều trị. TSH bình thường khi đang điều trị là mục tiêu tốt.")
        return ClinicalPattern(
            pattern_id="thyroid_dysfunction",
            display_name_vi="Chức năng tuyến giáp bất thường",
            description_vi="TSH bất thường — cần đánh giá chức năng tuyến giáp toàn diện.",
            severity="watch",
            supporting_findings=signals,
            confidence=_confidence(len(signals), "ft4" in signals),
            evidence_based=True,
            evidence_source="established",
            reasoning_vi="TSH là chỉ số nhạy nhất để tầm soát rối loạn tuyến giáp. TSH tăng (suy giáp) hoặc giảm (cường giáp) đều cần FT4/FT3 để xác định mức độ.",
            clinical_significance_vi="Rối loạn tuyến giáp ảnh hưởng đến chuyển hóa, tim mạch, thần kinh và nhiều cơ quan. Điều trị sớm cải thiện chất lượng sống đáng kể.",
            context_modifiers=ctx_mods,
            recommended_additional_tests=["FT4", "FT3", "Anti-TPO (tự miễn)", "Siêu âm tuyến giáp"],
            limitation_vi="TSH biến đổi theo thời gian trong ngày và trạng thái bệnh cấp tính. Một kết quả bất thường cần xác nhận lại.",
        )

    rules.append(PatternRule("thyroid_dysfunction", "Tuyến giáp", "watch", "established", _thyroid_detect, _thyroid_build))

    return rules


_PATTERN_REGISTRY: list[PatternRule] = _register_patterns()


# ── CrossMarkerCorrelationEngine ──────────────────────────────────────────────

class CrossMarkerCorrelationEngine:
    """Detect clinical patterns from multi-marker combinations.

    Args:
        findings: {canonical: ClinicalFinding.__dict__ or {"status": ...}}
        derived: {canonical: float | DerivedMetricResult}
        ctx: PatientContext
    """

    def detect(
        self,
        findings: dict,
        derived: dict,
        ctx: PatientContext,
    ) -> list[ClinicalPattern]:
        patterns: list[ClinicalPattern] = []
        seen: set[str] = set()
        for rule in _PATTERN_REGISTRY:
            if rule.pattern_id in seen:
                continue
            matching = rule.detector(findings, derived, ctx)
            if not matching:
                continue
            seen.add(rule.pattern_id)
            patterns.append(rule.build_pattern(matching, ctx))
        return patterns


def detect_patterns_v3(
    findings: dict,
    derived: dict,
    ctx: PatientContext,
) -> list[ClinicalPattern]:
    """Public API — replaces detect_patterns() from clinical_patterns.py."""
    return CrossMarkerCorrelationEngine().detect(findings, derived, ctx)
