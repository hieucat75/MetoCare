"""Medical Narrative Layer — Phase 3.

Generates patient-friendly Vietnamese narrative from PatientInsightReport.
Uses Claude (Anthropic) as the narrative engine.

Pipeline:
  PatientInsightReport (Rule Engine output)
  → NarrativeInput (distilled JSON, safe for Claude)
  → Claude API call (via claude_client.py directly)
  → NarrativeValidator (safety check, always wins)
  → NarrativeQualityScore (internal QA)
  → NarrativeCache (persist result)
  → Return to caller

Safety: if Claude fails OR validator fails → deterministic fallback
Async: supports background generation via generate_narrative_async()
NEVER raises: always returns a valid NarrativeResult
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.services.claude_client import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, get_client
from app.services.narrative_cache import (
    get_cached_narrative,
    make_narrative_key,
    save_narrative,
)
from app.services.narrative_input import build_narrative_input
from app.services.narrative_prompts import ENGINE_VERSION, PROMPT_VERSION, PromptRegistry
from app.services.narrative_quality import NarrativeQualityScore, score_narrative
from app.services.narrative_validator import validate_narrative

logger = logging.getLogger("metocare.narrative")

NARRATIVE_PROVIDER = "anthropic"
NARRATIVE_LANGUAGE = "vi"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class NarrativeResult:
    patient_id: str
    batch_id: str | None
    narrative: dict           # 10 sections
    source: str               # "claude" | "fallback_validator_fail" | "fallback_error" | "fallback_empty" | "cache"
    cached: bool
    prompt_version: str
    engine_version: str
    provider: str
    model: str
    quality_score: NarrativeQualityScore | None = None
    validation_passed: bool = True
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


# ---------------------------------------------------------------------------
# Deterministic fallback narrative
# ---------------------------------------------------------------------------

def _build_fallback_narrative(report: Any) -> dict:
    """Build a deterministic 10-section narrative from PatientInsightReport.

    Used when Claude is unavailable or validator rejects the output.
    No invented content — only uses fields from the report.
    """
    from app.services.narrative_input import _get  # local import

    overall_status = _get(report, "overall_status", "attention")
    overall_text = _get(report, "overall_status_text_vi", "Có một số chỉ số cần chú ý.")

    insights = _get(report, "insights", []) or []
    missing_context = _get(report, "missing_context", []) or []
    urgent_alerts = _get(report, "urgent_alerts", []) or []
    next_best_action_raw = _get(report, "next_best_action", None)
    action_cards = _get(report, "action_cards", []) or []

    # Section 1: summary
    if urgent_alerts:
        section1 = (
            f"{overall_text} "
            "MetoCare đã phát hiện một số điểm cần chú ý trong kết quả xét nghiệm của bạn. "
            "Vui lòng xem chi tiết bên dưới và trao đổi với bác sĩ."
        )
    else:
        section1 = (
            f"{overall_text} "
            "Kết quả phân tích cho thấy tình trạng sức khỏe tổng thể của bạn. "
            "Hãy xem các nhận định chi tiết để hiểu rõ hơn về các chỉ số."
        )

    # Section 2: what happened
    if insights:
        top = insights[0]
        title = _get(top, "title_vi", "các chỉ số xét nghiệm")
        rationale = _get(top, "rationale_vi", "")
        section2 = (
            f"Phân tích cho thấy: {title}. "
            f"{rationale} "
            "Các chỉ số này phản ánh tình trạng sinh lý hiện tại của cơ thể bạn."
        ).strip()
    else:
        section2 = (
            "Dựa trên kết quả xét nghiệm, hệ thống đã phân tích các chỉ số sinh hóa và lâm sàng. "
            "Chưa có đủ dữ liệu để đưa ra nhận định chi tiết."
        )

    # Section 3: reasoning
    insight_count = len(insights)
    section3 = (
        f"Hệ thống đã phân tích {insight_count} chỉ số được phân loại từ kết quả xét nghiệm của bạn. "
        "Mỗi chỉ số được so sánh với ngưỡng tham chiếu theo độ tuổi và giới tính. "
        "Các chỉ số có liên quan được phân tích cùng nhau để phát hiện các mẫu hình lâm sàng."
    )

    # Section 4: personal context
    completeness = _get(report, "context_completeness", 0.0) or 0.0
    if completeness > 0.5:
        section4 = (
            "Nhận định này được cá nhân hóa dựa trên thông tin sức khỏe bạn đã cung cấp. "
            "Mức độ hoàn chỉnh của hồ sơ sức khỏe giúp phân tích chính xác hơn."
        )
    else:
        section4 = (
            "Để phân tích chính xác hơn, bạn có thể bổ sung thông tin về tuổi, giới tính, "
            "cân nặng và các bệnh nền. Điều này giúp hệ thống đưa ra nhận định phù hợp hơn."
        )

    # Section 5: if nothing changes
    if overall_status in ("urgent", "action_required"):
        section5 = (
            "Nếu không có thay đổi, một số chỉ số có thể tiếp tục ở mức cần chú ý. "
            "Việc theo dõi định kỳ và trao đổi với bác sĩ sẽ giúp ngăn ngừa diễn tiến xấu hơn."
        )
    else:
        section5 = (
            "Duy trì lối sống lành mạnh sẽ giúp các chỉ số ổn định theo thời gian. "
            "Theo dõi định kỳ là cách tốt nhất để phát hiện sớm các thay đổi."
        )

    # Section 6: most important today
    if next_best_action_raw:
        nba_title = _get(next_best_action_raw, "title_vi", "")
        nba_why = _get(next_best_action_raw, "why_vi", "")
        section6 = f"{nba_title}. {nba_why}".strip().rstrip(".") + "."
    elif urgent_alerts:
        alert = urgent_alerts[0]
        section6 = f"Ưu tiên hàng đầu: {_get(alert, 'title_vi', 'gặp bác sĩ để được đánh giá')}."
    elif insights:
        top_insight = insights[0]
        section6 = f"Chú ý đến: {_get(top_insight, 'title_vi', 'các chỉ số cần theo dõi')}."
    else:
        section6 = "Duy trì lối sống lành mạnh và theo dõi sức khỏe định kỳ."

    # Section 7: monthly plan (list)
    monthly_plan: list[str] = []
    for ac in action_cards[:3]:
        title = _get(ac, "title_vi", "")
        if title:
            monthly_plan.append(title)
    if not monthly_plan:
        monthly_plan = [
            "Xét nghiệm theo dõi định kỳ theo lịch hẹn",
            "Duy trì chế độ ăn uống và vận động lành mạnh",
            "Trao đổi với bác sĩ về kết quả xét nghiệm này",
        ]

    # Section 8: what AI doesn't know (list)
    if missing_context:
        what_unknown = [f"Thông tin chưa có: {ctx}" for ctx in missing_context[:3]]
    else:
        what_unknown = [
            "Tiền sử bệnh gia đình",
            "Tình trạng sức khỏe toàn diện ngoài các chỉ số xét nghiệm này",
        ]

    # Section 9: doctor questions (list)
    doctor_questions: list[str] = []
    for ins in insights[:3]:
        dq = _get(ins, "doctor_questions", []) or []
        if dq and isinstance(dq, list) and len(dq) > 0:
            doctor_questions.append(dq[0])
    if not doctor_questions:
        doctor_questions = [
            "Tôi cần làm thêm xét nghiệm nào để theo dõi các chỉ số này?",
            "Lối sống nào phù hợp nhất với tình trạng sức khỏe hiện tại của tôi?",
            "Khi nào tôi cần quay lại tái khám?",
        ]

    # Section 10: disclaimer
    disclaimer = (
        "Giải thích này chỉ hỗ trợ hiểu thông tin sức khỏe, không thay thế đánh giá, "
        "chẩn đoán hoặc điều trị từ chuyên gia y tế."
    )

    return {
        "section_1_summary": section1,
        "section_2_what_happened": section2,
        "section_3_reasoning": section3,
        "section_4_personal_context": section4,
        "section_5_if_nothing_changes": section5,
        "section_6_most_important_today": section6,
        "section_7_monthly_plan": monthly_plan,
        "section_8_what_ai_doesnt_know": what_unknown,
        "section_9_doctor_questions": doctor_questions[:3],
        "section_10_disclaimer": disclaimer,
    }


def _get_overall_status(report: Any) -> str:
    """Get overall_status safely from report or dict."""
    if isinstance(report, dict):
        return report.get("overall_status", "attention")
    return getattr(report, "overall_status", "attention")


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_narrative(
    report: Any,
    patient_id: str,
    batch_id: str | None,
    use_cache: bool = True,
) -> NarrativeResult:
    """Generate a full-report narrative from PatientInsightReport.

    NEVER raises — always returns a valid NarrativeResult.
    Falls back to deterministic narrative on any error.
    """
    t0 = time.monotonic()
    overall_status = _get_overall_status(report)

    # Step 1: build cache key
    cache_key = make_narrative_key(
        patient_id=patient_id,
        batch_id=batch_id,
        engine_version=ENGINE_VERSION,
        prompt_version=PROMPT_VERSION,
        provider=NARRATIVE_PROVIDER,
        model=ANTHROPIC_MODEL,
        language=NARRATIVE_LANGUAGE,
    )

    # Step 2: cache check
    if use_cache:
        cached_data = get_cached_narrative(cache_key)
        if cached_data and "narrative" in cached_data:
            latency_ms = int((time.monotonic() - t0) * 1000)
            narrative = cached_data["narrative"]
            quality = score_narrative(narrative, overall_status)
            return NarrativeResult(
                patient_id=patient_id,
                batch_id=batch_id,
                narrative=narrative,
                source="cache",
                cached=True,
                prompt_version=cached_data.get("prompt_version", PROMPT_VERSION),
                engine_version=cached_data.get("engine_version", ENGINE_VERSION),
                provider=NARRATIVE_PROVIDER,
                model=ANTHROPIC_MODEL,
                quality_score=quality,
                validation_passed=True,
                latency_ms=latency_ms,
                prompt_tokens=cached_data.get("prompt_tokens", 0),
                completion_tokens=cached_data.get("completion_tokens", 0),
            )

    # Step 3: check API key before calling
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — using fallback narrative")
        fallback = _build_fallback_narrative(report)
        quality = score_narrative(fallback, overall_status)
        return NarrativeResult(
            patient_id=patient_id,
            batch_id=batch_id,
            narrative=fallback,
            source="fallback_empty",
            cached=False,
            prompt_version=PROMPT_VERSION,
            engine_version=ENGINE_VERSION,
            provider=NARRATIVE_PROVIDER,
            model=ANTHROPIC_MODEL,
            quality_score=quality,
            validation_passed=True,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    # Step 4: build narrative input
    narrative_input = build_narrative_input(report, language=NARRATIVE_LANGUAGE)

    # Step 5: get prompt
    prompt = PromptRegistry.current()

    # Step 6–11: call Claude, validate, score, cache
    try:
        client = get_client()

        user_content = prompt.user_template.format(
            report_json=json.dumps(narrative_input, ensure_ascii=False, indent=2)
        )

        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2000,
            temperature=0.3,
            system=prompt.system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )

        raw_output = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw_output.startswith("```"):
            lines = raw_output.split("\n")
            raw_output = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()

        parsed: dict = json.loads(raw_output)

        prompt_tokens = getattr(response.usage, "input_tokens", 0)
        completion_tokens = getattr(response.usage, "output_tokens", 0)

        # Step 7: validate
        validation = validate_narrative(parsed, overall_status)

        if not validation["passed"]:
            logger.warning(
                "narrative validation failed for patient=%s batch=%s: %s",
                patient_id,
                batch_id,
                validation["reason"],
            )
            fallback = _build_fallback_narrative(report)
            quality = score_narrative(fallback, overall_status)
            return NarrativeResult(
                patient_id=patient_id,
                batch_id=batch_id,
                narrative=fallback,
                source="fallback_validator_fail",
                cached=False,
                prompt_version=PROMPT_VERSION,
                engine_version=ENGINE_VERSION,
                provider=NARRATIVE_PROVIDER,
                model=ANTHROPIC_MODEL,
                quality_score=quality,
                validation_passed=False,
                latency_ms=int((time.monotonic() - t0) * 1000),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        # Step 9: score
        quality = score_narrative(parsed, overall_status)

        latency_ms = int((time.monotonic() - t0) * 1000)

        # Step 10: save to cache
        cache_payload = {
            "narrative": parsed,
            "prompt_version": PROMPT_VERSION,
            "engine_version": ENGINE_VERSION,
            "provider": NARRATIVE_PROVIDER,
            "model": ANTHROPIC_MODEL,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        save_narrative(cache_key, cache_payload)

        logger.info(
            "narrative generated: patient=%s batch=%s latency=%dms tokens=%d+%d quality=%.2f",
            patient_id,
            batch_id,
            latency_ms,
            prompt_tokens,
            completion_tokens,
            quality.overall,
        )

        # Step 11: return
        return NarrativeResult(
            patient_id=patient_id,
            batch_id=batch_id,
            narrative=parsed,
            source="claude",
            cached=False,
            prompt_version=PROMPT_VERSION,
            engine_version=ENGINE_VERSION,
            provider=NARRATIVE_PROVIDER,
            model=ANTHROPIC_MODEL,
            quality_score=quality,
            validation_passed=True,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    except Exception as exc:
        logger.error(
            "narrative generation error for patient=%s batch=%s: %s",
            patient_id,
            batch_id,
            exc,
        )
        fallback = _build_fallback_narrative(report)
        quality = score_narrative(fallback, overall_status)
        return NarrativeResult(
            patient_id=patient_id,
            batch_id=batch_id,
            narrative=fallback,
            source="fallback_error",
            cached=False,
            prompt_version=PROMPT_VERSION,
            engine_version=ENGINE_VERSION,
            provider=NARRATIVE_PROVIDER,
            model=ANTHROPIC_MODEL,
            quality_score=quality,
            validation_passed=True,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


# ---------------------------------------------------------------------------
# Async wrapper
# ---------------------------------------------------------------------------

def generate_narrative_async(
    report: Any,
    patient_id: str,
    batch_id: str | None,
    background_tasks: Any,
) -> str:
    """Background task wrapper for narrative generation.

    Returns generation_id (cache key) immediately.
    Adds the generate_narrative call to background_tasks.
    Frontend can poll GET /patients/{patient_id}/narrative/{batch_id} for result.
    """
    from app.services.narrative_cache import make_narrative_key  # already imported above

    generation_id = make_narrative_key(
        patient_id=patient_id,
        batch_id=batch_id,
        engine_version=ENGINE_VERSION,
        prompt_version=PROMPT_VERSION,
        provider=NARRATIVE_PROVIDER,
        model=ANTHROPIC_MODEL,
        language=NARRATIVE_LANGUAGE,
    )

    background_tasks.add_task(generate_narrative, report, patient_id, batch_id, True)
    return generation_id
