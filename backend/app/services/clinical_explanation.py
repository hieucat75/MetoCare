"""
Generate patient-friendly Vietnamese clinical explanation using Claude Sonnet.

HARD RULES:
1. Claude receives ONLY canonical pre-classified output — never raw lab values alone.
2. Claude output is validated against canonical status before use.
3. If validation fails → use deterministic fallback, never show contradicting text.
4. No diagnosis, no medication advice, no contradiction with canonical status.
"""

from __future__ import annotations

import json
import logging

from app.services.claude_client import ANTHROPIC_MODEL, get_client, hash_clinical_input
from app.services.explanation_cache import (
    get_cached_explanation,
    save_cached_explanation,
)

logger = logging.getLogger("metocare.explanation")

# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Bạn là trợ lý sức khỏe của MetoCare. Nhiệm vụ của bạn là giải thích kết quả xét nghiệm cho bệnh nhân người Việt Nam, ở độ tuổi 45–70, không có nền tảng y khoa.

QUY TẮC TUYỆT ĐỐI:
1. Bạn CHỈ được giải thích kết quả đã được phân loại sẵn. KHÔNG tự so sánh con số với ngưỡng.
2. KHÔNG được đặt chẩn đoán bệnh.
3. KHÔNG được thay đổi hoặc mâu thuẫn với trạng thái lâm sàng đã cung cấp (canonical_status).
4. KHÔNG được đề nghị thay đổi thuốc.
5. KHÔNG được nói "nguy hiểm" hoặc "cần gặp bác sĩ ngay" nếu canonical_severity không phải urgent/critical.
6. KHÔNG được nói "bình thường" nếu canonical_status là high/borderline_high/low.
7. Dùng ngôn ngữ ấm áp, dễ hiểu, không gây hoảng loạn không cần thiết.
8. Độ dài: 3–5 câu. Không dùng bullet points trong giải thích chính.

Bạn sẽ nhận một JSON với kết quả đã phân loại. Hãy viết giải thích theo cấu trúc yêu cầu."""


def build_prompt(clinical_input: dict) -> str:
    return f"""Đây là kết quả xét nghiệm đã được hệ thống phân loại lâm sàng xử lý:

```json
{json.dumps(clinical_input, ensure_ascii=False, indent=2)}
```

Hãy viết giải thích bệnh nhân theo đúng định dạng JSON sau:
{{
  "explanation": "Giải thích chính, 3–5 câu, bằng tiếng Việt thông thường.",
  "why_it_matters": "Tại sao chỉ số này quan trọng (1–2 câu).",
  "what_to_monitor": "Điều cần theo dõi tiếp theo (1–2 câu).",
  "what_to_ask_doctor": "Câu hỏi nên hỏi bác sĩ nếu có lịch khám (1 câu).",
  "next_step": "Hành động tiếp theo cụ thể (1 câu)."
}}

Chỉ trả về JSON. Không thêm văn bản ngoài JSON."""


# ---------------------------------------------------------------------------
# Forbidden phrase sets per status group
# ---------------------------------------------------------------------------

FORBIDDEN_FOR_NON_CRITICAL = [
    "nguy hiểm",
    "cần gặp bác sĩ ngay",
    "cấp cứu",
    "khẩn cấp",
    "nghiêm trọng",
]
FORBIDDEN_FOR_NORMAL = [
    "cao",
    "thấp",
    "bất thường",
    "cần chú ý",
    "đáng lo",
]
FORBIDDEN_FOR_HIGH = [
    "bình thường",
    "không đáng lo",
    "hoàn toàn ổn",
]
FORBIDDEN_FOR_LOW = [
    "bình thường",
    "không đáng lo",
    "hoàn toàn ổn",
]


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_explanation(output: dict, clinical_input: dict) -> dict:
    """
    Validate that Claude output does not contradict canonical_status.

    Returns: {"passed": bool, "reason": str}
    """
    status = clinical_input.get("canonical_status", "")
    severity = clinical_input.get("canonical_severity", "")
    doctor_required = clinical_input.get("doctor_review_required", False)

    explanation_text = " ".join(
        [
            output.get("explanation", ""),
            output.get("why_it_matters", ""),
            output.get("what_to_monitor", ""),
            output.get("next_step", ""),
        ]
    ).lower()

    # Rule 1: non-urgent status → no dangerous language
    if status not in (
        "critical",
        "very_high",
        "critical_high",
        "critical_low",
    ) and severity not in ("urgent", "critical"):
        for phrase in FORBIDDEN_FOR_NON_CRITICAL:
            if phrase in explanation_text:
                return {
                    "passed": False,
                    "reason": f"Non-critical status but output contains '{phrase}'",
                }

    # Rule 2: normal status → no alarming language
    if status == "normal":
        for phrase in FORBIDDEN_FOR_NORMAL:
            if phrase in explanation_text:
                return {
                    "passed": False,
                    "reason": f"Normal status but output contains '{phrase}'",
                }

    # Rule 3: high status → no "bình thường" reassurance
    if status in ("high", "very_high", "borderline_high", "critical_high"):
        for phrase in FORBIDDEN_FOR_HIGH:
            if phrase in explanation_text:
                return {
                    "passed": False,
                    "reason": f"High status but output contains '{phrase}'",
                }

    # Rule 4: low status → no normal reassurance
    if status in ("low", "critical_low"):
        for phrase in FORBIDDEN_FOR_LOW:
            if phrase in explanation_text:
                return {
                    "passed": False,
                    "reason": f"Low status but output contains '{phrase}'",
                }

    # Rule 5: doctor_review_required=False → no "cần gặp bác sĩ ngay"
    if not doctor_required:
        if "cần gặp bác sĩ ngay" in explanation_text:
            return {
                "passed": False,
                "reason": "doctor_review_required=False but output says 'cần gặp bác sĩ ngay'",
            }

    return {"passed": True, "reason": "OK"}


# ---------------------------------------------------------------------------
# Deterministic fallback — NO LLM, always safe
# ---------------------------------------------------------------------------

FALLBACK_TEMPLATES: dict[str, str] = {
    "normal": (
        "Chỉ số {name} của bạn đang ở mức bình thường ({value} {unit}). "
        "Tiếp tục duy trì lối sống lành mạnh."
    ),
    "borderline_high": (
        "Chỉ số {name} ({value} {unit}) đang hơi cao so với mức bình thường. Nên theo dõi định kỳ."
    ),
    # Align with ClinicalFinding.status values used by the existing engine
    "borderline": ("Chỉ số {name} ({value} {unit}) đang ở vùng cần chú ý. Nên theo dõi định kỳ."),
    "high": (
        "Chỉ số {name} ({value} {unit}) cao hơn mức bình thường. "
        "Nên thảo luận với bác sĩ trong lần khám tiếp theo."
    ),
    "very_high": ("Chỉ số {name} ({value} {unit}) ở mức cao đáng kể. Cần được bác sĩ đánh giá."),
    "critical_high": ("Chỉ số {name} ({value} {unit}) ở mức rất cao. Cần liên hệ bác sĩ sớm."),
    "critical": (
        "Chỉ số {name} ({value} {unit}) ở mức cần được bác sĩ đánh giá khẩn. "
        "Vui lòng liên hệ bác sĩ sớm."
    ),
    "low": ("Chỉ số {name} ({value} {unit}) đang thấp hơn mức bình thường. Nên theo dõi."),
    "critical_low": ("Chỉ số {name} ({value} {unit}) ở mức thấp đáng lo. Cần liên hệ bác sĩ."),
    "unknown": (
        "Chỉ số {name} ({value} {unit}) đã được ghi nhận. Vui lòng tham khảo bác sĩ để hiểu rõ hơn."
    ),
}


def get_deterministic_fallback(clinical_input: dict) -> dict:
    """Return a deterministic (no-LLM) explanation always consistent with status."""
    status = clinical_input.get("canonical_status", "unknown")
    template = FALLBACK_TEMPLATES.get(status, FALLBACK_TEMPLATES["unknown"])
    text = template.format(
        name=clinical_input.get(
            "biomarker_display_name",
            clinical_input.get("biomarker_name", "xét nghiệm"),
        ),
        value=clinical_input.get("normalized_value", ""),
        unit=clinical_input.get("normalized_unit", ""),
    )
    return {
        "explanation": text,
        "why_it_matters": "",
        "what_to_monitor": "",
        "what_to_ask_doctor": "",
        "next_step": "",
        "source": "deterministic_fallback",
        "validated": True,
    }


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log_explanation_attempt(
    lab_result_id: str,
    input_hash: str,
    model: str,
    output: dict,
    validation: dict,
) -> None:
    logger.info(
        json.dumps(
            {
                "event": "explanation_attempt",
                "lab_result_id": lab_result_id,
                "input_hash": input_hash,
                "model": model,
                "validation_passed": validation["passed"],
                "validation_reason": validation.get("reason"),
                "output_source": "claude" if validation["passed"] else "fallback",
            },
            ensure_ascii=False,
        )
    )


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


def generate_explanation(
    lab_result_id: str,
    clinical_input: dict,
    use_cache: bool = True,
) -> dict:
    """
    Generate Claude explanation for a pre-classified lab result.

    ``clinical_input`` must include:
    - biomarker_name, biomarker_display_name
    - normalized_value, normalized_unit
    - canonical_status  (REQUIRED — e.g. "borderline_high")
    - canonical_severity  (REQUIRED — e.g. "moderate")
    - canonical_priority  (e.g. "routine" / "urgent" / "critical")
    - doctor_review_required (bool)

    Returns:
        {explanation, why_it_matters, what_to_monitor,
         what_to_ask_doctor, next_step, source, validated}

    NEVER raises — always returns a valid (possibly fallback) dict.
    """
    # Validate required fields
    required = ["canonical_status", "canonical_severity", "normalized_value", "normalized_unit"]
    for field in required:
        if clinical_input.get(field) is None:
            logger.warning(
                "generate_explanation: missing required field '%s' for lab_result=%s — using fallback",  # noqa: E501
                field,
                lab_result_id,
            )
            fallback = get_deterministic_fallback(clinical_input)
            fallback["source"] = "fallback_missing_field"
            return fallback

    input_hash = hash_clinical_input(clinical_input)

    # Cache lookup
    if use_cache:
        cached = get_cached_explanation(lab_result_id, input_hash)
        if cached:
            logger.info("Cache hit for lab_result=%s hash=%s", lab_result_id, input_hash)
            return cached

    # Call Claude
    try:
        client = get_client()
        prompt = build_prompt(clinical_input)

        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=800,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_output = response.content[0].text.strip()
        # Strip markdown code fences if Claude wraps in ```json ... ```
        if raw_output.startswith("```"):
            lines = raw_output.split("\n")
            raw_output = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()

        parsed = json.loads(raw_output)

        # Validate — CRITICAL step
        validation = validate_explanation(parsed, clinical_input)

        log_explanation_attempt(
            lab_result_id=lab_result_id,
            input_hash=input_hash,
            model=ANTHROPIC_MODEL,
            output=parsed,
            validation=validation,
        )

        if not validation["passed"]:
            logger.warning(
                "Claude output rejected for lab_result=%s: %s",
                lab_result_id,
                validation["reason"],
            )
            fallback = get_deterministic_fallback(clinical_input)
            fallback["source"] = "fallback_after_validation_failure"
            fallback["validation_failure"] = validation["reason"]
            return fallback

        result = {
            **parsed,
            "source": "claude",
            "validated": True,
            "input_hash": input_hash,
        }
        save_cached_explanation(lab_result_id, input_hash, result)
        return result

    except Exception as exc:
        logger.error(
            "Claude explanation failed for lab_result=%s: %s",
            lab_result_id,
            exc,
        )
        fallback = get_deterministic_fallback(clinical_input)
        fallback["source"] = "fallback_after_error"
        return fallback
