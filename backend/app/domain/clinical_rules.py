"""Pure rule-based clinical engine for verified lab results only.

This module intentionally contains no I/O, no DB access, and no LLM calls.
It consumes normalized/verified lab values and emits explainable findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .lab_interpreter import BIOMARKERS


@dataclass
class ClinicalFinding:
    canonical: str
    finding_type: str        # "biomarker" | "derived_metric" | "pattern"
    status: str              # "normal" | "borderline" | "high" | "low" | "critical" | "abnormal"
    severity: str            # "info" | "watch" | "warning" | "critical"
    priority: int            # 1=critical, 2=warning, 3=watch, 4=info
    patient_explanation_vi: str
    doctor_note: str
    doctor_review_required: bool
    evidence_strength: str   # "established" | "moderate" | "emerging"


@dataclass
class ClinicalRuleResult:
    findings: list[ClinicalFinding] = field(default_factory=list)
    summary_vi: str = ""
    top_priorities: list[str] = field(default_factory=list)
    doctor_review_required: bool = False


_SPEC_BY_CANONICAL = {spec.canonical: spec for spec in BIOMARKERS}


def _finding(
    canonical: str,
    finding_type: str,
    status: str,
    severity: str,
    priority: int,
    patient_explanation_vi: str,
    doctor_note: str,
    doctor_review_required: bool,
    evidence_strength: str = "established",
) -> ClinicalFinding:
    return ClinicalFinding(
        canonical=canonical,
        finding_type=finding_type,
        status=status,
        severity=severity,
        priority=priority,
        patient_explanation_vi=patient_explanation_vi,
        doctor_note=doctor_note,
        doctor_review_required=doctor_review_required,
        evidence_strength=evidence_strength,
    )


def assess_biomarker(canonical: str, value: float, *, age_years: int | None = None, is_male: bool = True) -> ClinicalFinding | None:  # noqa: E501
    spec = _SPEC_BY_CANONICAL.get(canonical)
    if spec is None:
        return None

    # Critical rules
    if canonical == "fasting_glucose" and (value >= 300 or value <= 54):
        return _finding(canonical, "biomarker", "critical", "critical", 1,
                        "Đường huyết ở mức rất nguy hiểm, cần bác sĩ đánh giá ngay.",
                        f"{canonical}={value} mg/dL critical", True)
    if canonical == "hba1c" and value >= 10:
        return _finding(canonical, "biomarker", "critical", "critical", 1,
                        "HbA1c đang ở mức rất cao, cần bác sĩ xem xét sớm.",
                        f"{canonical}={value}% critical", True)
    if canonical == "creatinine" and value >= (spec.critical_high or 1e9):
        return _finding(canonical, "biomarker", "critical", "critical", 1,
                        "Creatinine tăng rất cao, cần bác sĩ đánh giá chức năng thận.",
                        f"{canonical}={value} mg/dL critical", True)
    if canonical in {"sodium", "potassium", "hemoglobin"}:
        if spec.critical_low is not None and value <= spec.critical_low:
            return _finding(canonical, "biomarker", "critical", "critical", 1,
                            "Chỉ số đang ở mức rất thấp và cần bác sĩ đánh giá.",
                            f"{canonical}={value} critical low", True)
        if spec.critical_high is not None and value >= spec.critical_high:
            return _finding(canonical, "biomarker", "critical", "critical", 1,
                            "Chỉ số đang ở mức rất cao và cần bác sĩ đánh giá.",
                            f"{canonical}={value} critical high", True)

    # Warning/watch patterns
    if canonical == "fasting_glucose" and 100 <= value <= 125:
        return _finding(canonical, "biomarker", "borderline", "watch", 3,
                        "Đường huyết lúc đói đang ở vùng tiền tiểu đường.",
                        f"{canonical}={value} mg/dL prediabetes range", True)
    if canonical == "fasting_glucose" and 126 <= value < 300:
        return _finding(canonical, "biomarker", "high", "warning", 2,
                        "Đường huyết đang cao và cần bác sĩ xem xét thêm.",
                        f"{canonical}={value} mg/dL high", True)
    if canonical == "hba1c" and 5.7 <= value <= 6.4:
        return _finding(canonical, "biomarker", "borderline", "watch", 3,
                        "HbA1c đang ở vùng tiền tiểu đường.",
                        f"{canonical}={value}% prediabetes range", True)
    if canonical == "hdl":
        low_cut = 40 if is_male else 50
        if value < low_cut:
            return _finding(canonical, "biomarker", "low", "watch", 3,
                            "HDL đang thấp hơn mức mong muốn.",
                            f"{canonical}={value} low HDL", False)
    if canonical == "ldl" and value > 3.4:
        return _finding(canonical, "biomarker", "high", "warning", 2,
                        "LDL đang cao, có thể làm tăng nguy cơ tim mạch.",
                        f"{canonical}={value} mmol/L high LDL", True)
    if canonical == "triglyceride" and value > 5.6:
        return _finding(canonical, "biomarker", "high", "warning", 2,
                        "Triglyceride đang rất cao, cần bác sĩ đánh giá thêm.",
                        f"{canonical}={value} mmol/L very high TG", True)
    if canonical in {"alt", "ast"} and value > (spec.ref_high or 0) * 3:
        return _finding(canonical, "biomarker", "high", "warning", 2,
                        "Men gan đang tăng cao, cần đánh giá thêm.",
                        f"{canonical}={value} >3x ULN", True)
    if canonical == "tsh" and (value < 0.1 or value > 10):
        return _finding(canonical, "biomarker", "abnormal", "warning", 2,
                        "Tuyến giáp có chỉ số bất thường.",
                        f"{canonical}={value} abnormal", True)
    if canonical == "egfr":
        if value < 60:
            return _finding(canonical, "derived_metric", "abnormal", "warning", 2,
                            "Chức năng thận giảm, cần bác sĩ xem xét.",
                            f"{canonical}={value} <60", True)
        if 60 <= value < 90:
            return _finding(canonical, "derived_metric", "borderline", "watch", 3,
                            "Chức năng thận hơi giảm so với mức lý tưởng.",
                            f"{canonical}={value} 60-89", False)

    return _finding(canonical, "biomarker", "normal", "info", 4,
                    "Chỉ số này đang trong khoảng chấp nhận được.",
                    f"{canonical}={value} normal", False)


def summarize_findings(findings: list[ClinicalFinding]) -> tuple[str, list[str], bool]:
    top = [f.canonical for f in sorted(findings, key=lambda x: x.priority) if f.severity != "info"][:5]  # noqa: E501
    doctor = any(f.doctor_review_required for f in findings)
    if not findings:
        return "Chưa ghi nhận phát hiện nổi bật từ các xét nghiệm đã xác minh.", [], False
    critical = [f for f in findings if f.severity == "critical"]
    warning = [f for f in findings if f.severity == "warning"]
    if critical:
        summary = "Một số chỉ số ở mức rất cao hoặc rất thấp và cần bác sĩ đánh giá sớm."
    elif warning:
        summary = "Có một số chỉ số cần theo dõi hoặc cần bác sĩ xem xét thêm."
    else:
        summary = "Các chỉ số hiện chưa cho thấy vấn đề nổi bật trong bộ quy tắc này."
    return summary, top, doctor
