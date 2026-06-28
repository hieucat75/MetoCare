"""Meaningful cluster detection from verified lab results only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PatternDetection:
    pattern_id: str
    display_name_vi: str
    description_vi: str
    severity: str  # "info" | "watch" | "warning"
    supporting_findings: list[str]
    confidence: str  # "high" | "moderate" | "low"
    doctor_review_required: bool
    evidence_strength: str


def _confidence(n_signals: int, has_derived: bool = False) -> str:
    if n_signals >= 2:
        return "high"
    if n_signals == 1 and has_derived:
        return "moderate"
    return "low"


def detect_patterns(summary: dict[str, object]) -> list[PatternDetection]:
    findings = summary.get("findings", {})
    derived = summary.get("derived", {})
    patterns: list[PatternDetection] = []

    def has(c: str) -> bool:
        return c in findings or c in derived

    # 1 insulin resistance
    if (
        derived.get("tyg_index") is not None
        and float(derived["tyg_index"]) > 9.0
        and has("fasting_glucose")
        and has("triglyceride")
        and has("hdl")
    ):
        patterns.append(
            PatternDetection(
                "insulin_resistance",
                "Kháng insulin",
                "Mẫu hình gợi ý kháng insulin.",
                "warning",
                ["tyg_index", "fasting_glucose", "triglyceride", "hdl"],
                _confidence(3, True),
                True,
                "established",
            )
        )

    ms = derived.get("metabolic_syndrome")
    if isinstance(ms, dict) and ms.get("status") == "meets_criteria":
        patterns.append(
            PatternDetection(
                "metabolic_syndrome",
                "Hội chứng chuyển hóa",
                "Đạt tiêu chí hội chứng chuyển hóa.",
                "warning",
                ["metabolic_syndrome"],
                "high" if int(ms.get("criteria_count", 0)) >= 3 else "low",
                True,
                "established",
            )
        )

    if (
        (derived.get("ldl_friedewald") is not None and float(derived["ldl_friedewald"]) > 3.4)
        or (
            derived.get("non_hdl_cholesterol") is not None
            and float(derived["non_hdl_cholesterol"]) > 4.1
            and has("triglyceride")
        )  # noqa: E501
        or (has("hdl") and findings.get("hdl", {}).get("status") == "low")
    ):
        patterns.append(
            PatternDetection(
                "dyslipidemia",
                "Rối loạn lipid máu",
                "Có mẫu hình rối loạn lipid máu.",
                "watch",
                [
                    k
                    for k in ["ldl_friedewald", "non_hdl_cholesterol", "triglyceride", "hdl"]
                    if has(k)
                ],
                "high"
                if sum(
                    int(has(k))
                    for k in ["ldl_friedewald", "non_hdl_cholesterol", "triglyceride", "hdl"]
                )
                >= 2
                else "low",  # noqa: E501
                False,
                "established",
            )
        )

    if (
        has("alt")
        and has("triglyceride")
        and (has("fasting_glucose") or summary.get("bmi_proxy") is not None)
    ):  # noqa: E501
        patterns.append(
            PatternDetection(
                "fatty_liver_pattern",
                "Mẫu hình gan nhiễm mỡ",
                "ALT tăng cùng triglyceride tăng gợi ý cần theo dõi gan nhiễm mỡ.",
                "watch",
                [k for k in ["alt", "triglyceride", "fasting_glucose"] if has(k)],
                _confidence(2, False),
                True,
                "moderate",
            )
        )

    if has("egfr") or has("creatinine"):
        patterns.append(
            PatternDetection(
                "kidney_risk",
                "Nguy cơ thận",
                "Có tín hiệu cần theo dõi chức năng thận.",
                "watch",
                [k for k in ["egfr", "creatinine"] if has(k)],
                _confidence(sum(int(has(k)) for k in ["egfr", "creatinine"]), has("egfr")),
                True,
                "established",
            )
        )

    if has("tsh"):
        patterns.append(
            PatternDetection(
                "thyroid_pattern",
                "Mẫu hình tuyến giáp",
                "TSH ngoài khoảng tham chiếu.",
                "watch",
                [k for k in ["tsh", "ft4"] if has(k)],
                _confidence(sum(int(has(k)) for k in ["tsh", "ft4"]), has("ft4")),
                True,
                "established",
            )
        )

    return patterns
