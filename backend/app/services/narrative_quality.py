"""Narrative quality evaluation. Internal QA metrics only.

Never visible to patients. Used for monitoring and A/B testing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.narrative_validator import (
    FORBIDDEN_DIAGNOSIS,
    FORBIDDEN_MEDICATION,
    FORBIDDEN_PANIC_NON_CRITICAL,
)

# Personal context indicators (words suggesting personalization)
_PERSONAL_CONTEXT_WORDS = [
    "tuổi", "nam", "nữ", "cân nặng", "chiều cao", "bmi", "bệnh nền",
    "thuốc", "gia đình", "lối sống", "vận động", "ăn", "ngủ",
]

# Action verb patterns (Vietnamese)
_ACTION_VERBS = [
    "nên", "cần", "thực hiện", "duy trì", "tăng", "giảm", "hạn chế",
    "bổ sung", "kiểm tra", "theo dõi", "đo", "gặp", "xét nghiệm",
    "uống nước", "tập", "nghỉ ngơi", "ăn", "tránh",
]

# Warm/empathetic language indicators
_EMPATHY_WORDS = [
    "bạn", "chúng tôi", "cùng", "hỗ trợ", "đồng hành",
    "quan tâm", "hiểu", "hy vọng", "tốt hơn", "cải thiện",
    "tích cực", "lạc quan", "tiến bộ",
]


@dataclass
class NarrativeQualityScore:
    medical_consistency: float   # 0-1: no contradictions with Rule Engine
    personalization: float       # 0-1: contains personal context indicators
    readability: float           # 0-1: avg sentence length reasonable
    actionability: float         # 0-1: concrete actions present
    empathy: float               # 0-1: warm language indicators
    safety: float                # 0-1: no forbidden phrases
    estimated_read_seconds: int  # target: 60-90s
    hallucination_risk: float    # 0-1: lower is safer
    overall: float               # weighted average


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _count_sentences(text: str) -> int:
    """Rough sentence count by punctuation."""
    return max(1, len(re.findall(r"[.!?。！？]", text)))


def _count_words(text: str) -> int:
    return len(text.split())


def score_narrative(narrative: dict, report_overall_status: str) -> NarrativeQualityScore:
    """Score a narrative on 7 dimensions. Returns NarrativeQualityScore."""
    # Collect all text sections
    text_sections = [
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
    full_text = " ".join(text_sections).lower()
    section6 = narrative.get("section_6_most_important_today", "").lower()
    section7_text = " ".join(narrative.get("section_7_monthly_plan", [])).lower()

    # --- medical_consistency: 1.0 base, -0.2 per forbidden phrase ---
    consistency = 1.0
    for phrase in FORBIDDEN_DIAGNOSIS + FORBIDDEN_MEDICATION:
        if phrase in full_text:
            consistency -= 0.2
    if report_overall_status not in ("critical", "urgent"):
        for phrase in FORBIDDEN_PANIC_NON_CRITICAL:
            if phrase in full_text:
                consistency -= 0.2
    medical_consistency = _clamp(consistency)

    # --- personalization: ratio of personal context words found ---
    found_personal = sum(1 for w in _PERSONAL_CONTEXT_WORDS if w in full_text)
    personalization = _clamp(found_personal / max(1, len(_PERSONAL_CONTEXT_WORDS)) * 3.0)

    # --- readability: avg words per sentence; penalty if >30 avg ---
    total_words = _count_words(full_text)
    total_sentences = max(1, _count_sentences(full_text))
    avg_words_per_sentence = total_words / total_sentences
    if avg_words_per_sentence <= 20:
        readability = 1.0
    elif avg_words_per_sentence <= 30:
        readability = 1.0 - (avg_words_per_sentence - 20) / 10 * 0.5
    else:
        readability = _clamp(0.5 - (avg_words_per_sentence - 30) / 20 * 0.5)

    # --- actionability: action verbs in section_6 and section_7 ---
    action_hits = sum(1 for v in _ACTION_VERBS if v in section6 or v in section7_text)
    actionability = _clamp(action_hits / max(1, len(_ACTION_VERBS)) * 4.0)

    # --- empathy: warm language count ---
    empathy_hits = sum(1 for w in _EMPATHY_WORDS if w in full_text)
    empathy = _clamp(empathy_hits / max(1, len(_EMPATHY_WORDS)) * 3.0)

    # --- safety: from validator result ---
    from app.services.narrative_validator import validate_narrative  # noqa: PLC0415
    validation = validate_narrative(narrative, report_overall_status)
    safety = 1.0 if validation["passed"] else 0.0

    # --- estimated_read_seconds: words / 3 (Vietnamese ~180 wpm) ---
    estimated_read_seconds = max(1, total_words // 3)

    # --- hallucination_risk ---
    # Look for invented number patterns (e.g. "5.7 mmol/L", "120 mg/dL")
    # that may not be in the source (we use a simple heuristic: count numeric patterns)
    number_pattern = re.compile(r"\d+\.?\d*\s*(?:mmol|mg|g|dl|l|iu|u|meq|%)", re.IGNORECASE)
    invented_numbers = len(number_pattern.findall(full_text))
    hallucination_risk = _clamp(0.1 + invented_numbers * 0.05)

    # --- overall weighted average ---
    overall = _clamp(
        medical_consistency * 0.30
        + safety * 0.25
        + personalization * 0.15
        + actionability * 0.15
        + readability * 0.10
        + empathy * 0.05
    )

    return NarrativeQualityScore(
        medical_consistency=round(medical_consistency, 3),
        personalization=round(personalization, 3),
        readability=round(readability, 3),
        actionability=round(actionability, 3),
        empathy=round(empathy, 3),
        safety=round(safety, 3),
        estimated_read_seconds=estimated_read_seconds,
        hallucination_risk=round(hallucination_risk, 3),
        overall=round(overall, 3),
    )
