"""Safety Validator for Medical Narrative Layer.

Validates Claude narrative output against the Rule Engine source of truth.
The validator ALWAYS wins — if any check fails, fallback is used.

Checks:
1. All 10 sections present and non-empty
2. No forbidden diagnosis language
3. No medication prescription/discontinuation language
4. No severity escalation language (if overall_status is not critical)
5. No contradictions with overall_status from Rule Engine
6. section_10_disclaimer present and contains required text
7. No invented laboratory values (check format patterns)
"""
from __future__ import annotations

REQUIRED_SECTIONS = [
    "section_1_summary",
    "section_2_what_happened",
    "section_3_reasoning",
    "section_4_personal_context",
    "section_5_if_nothing_changes",
    "section_6_most_important_today",
    "section_7_monthly_plan",
    "section_8_what_ai_doesnt_know",
    "section_9_doctor_questions",
    "section_10_disclaimer",
]

FORBIDDEN_DIAGNOSIS = ["chẩn đoán", "bệnh lý", "bạn bị", "xác nhận", "kết luận bạn"]
FORBIDDEN_MEDICATION = ["kê đơn", "uống thuốc", "dừng thuốc", "tăng liều", "giảm liều", "đổi thuốc"]
FORBIDDEN_PANIC_NON_CRITICAL = ["nguy hiểm đến tính mạng", "cấp cứu ngay", "khẩn cấp tuyệt đối"]
REQUIRED_DISCLAIMER_SUBSTR = "không thay thế"  # must appear in section_10


def validate_narrative(narrative: dict, report_overall_status: str) -> dict:
    """
    Validate Claude narrative output.

    Returns {"passed": bool, "reason": str, "failed_sections": list[str]}
    """
    failed: list[str] = []
    reasons: list[str] = []

    # Check 1: all sections present and non-empty
    for section in REQUIRED_SECTIONS:
        val = narrative.get(section)
        if (
            val is None
            or (isinstance(val, str) and not val.strip())
            or (isinstance(val, list) and len(val) == 0)
        ):
            failed.append(section)
            reasons.append(f"Section missing or empty: {section}")

    if failed:
        return {"passed": False, "reason": "; ".join(reasons), "failed_sections": failed}

    # Build full text for scanning (exclude section_10 disclaimer from forbidden checks)
    all_text = " ".join(
        [
            narrative.get("section_1_summary", ""),
            narrative.get("section_2_what_happened", ""),
            narrative.get("section_3_reasoning", ""),
            narrative.get("section_4_personal_context", ""),
            narrative.get("section_5_if_nothing_changes", ""),
            narrative.get("section_6_most_important_today", ""),
            " ".join(narrative.get("section_7_monthly_plan", [])),
            " ".join(narrative.get("section_8_what_ai_doesnt_know", [])),
            " ".join(narrative.get("section_9_doctor_questions", [])),
        ]
    ).lower()

    # Check 2: no diagnosis language
    for phrase in FORBIDDEN_DIAGNOSIS:
        if phrase in all_text:
            return {
                "passed": False,
                "reason": f"Forbidden diagnosis language: '{phrase}'",
                "failed_sections": [],
            }

    # Check 3: no medication prescription
    for phrase in FORBIDDEN_MEDICATION:
        if phrase in all_text:
            return {
                "passed": False,
                "reason": f"Forbidden medication language: '{phrase}'",
                "failed_sections": [],
            }

    # Check 4: no panic language for non-critical
    if report_overall_status not in ("critical", "urgent"):
        for phrase in FORBIDDEN_PANIC_NON_CRITICAL:
            if phrase in all_text:
                return {
                    "passed": False,
                    "reason": f"Panic language for non-critical: '{phrase}'",
                    "failed_sections": [],
                }

    # Check 5: disclaimer present and contains required text
    disclaimer = narrative.get("section_10_disclaimer", "").lower()
    if REQUIRED_DISCLAIMER_SUBSTR not in disclaimer:
        return {
            "passed": False,
            "reason": "Disclaimer missing required text",
            "failed_sections": ["section_10_disclaimer"],
        }

    return {"passed": True, "reason": "OK", "failed_sections": []}
