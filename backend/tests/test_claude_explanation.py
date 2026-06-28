"""
Tests for Claude Sonnet Clinical Explanation Layer.

Covers:
- Contradiction validator logic (5 rules)
- Deterministic fallback correctness
- generate_explanation: fallback on validation failure, success path, cache
- No frontend direct Anthropic import
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from app.services.clinical_explanation import (
    generate_explanation,
    get_deterministic_fallback,
    validate_explanation,
)

# ---------------------------------------------------------------------------
# Shared test fixture
# ---------------------------------------------------------------------------

GLUCOSE_57_INPUT = {
    "biomarker_name": "fasting_glucose",
    "biomarker_display_name": "Đường huyết lúc đói",
    "normalized_value": 102.7,
    "normalized_unit": "mg/dL",
    "original_value": 5.7,
    "original_unit": "mmol/L",
    "reference_range_low": 70,
    "reference_range_high": 99,
    "canonical_status": "borderline_high",
    "canonical_severity": "moderate",
    "canonical_priority": "routine",
    "doctor_review_required": False,
    "safety_flags": [],
    "rule_id": "glucose_ada_2024",
    "evidence_strength": "high",
}

# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


def test_validator_rejects_dangerous_for_borderline():
    """Claude says dangerous for borderline_high → must be rejected."""
    bad_output = {
        "explanation": "Đường huyết của bạn ở mức rất nguy hiểm, cần gặp bác sĩ ngay.",
        "why_it_matters": "...",
        "what_to_monitor": "...",
        "what_to_ask_doctor": "...",
        "next_step": "...",
    }
    result = validate_explanation(bad_output, GLUCOSE_57_INPUT)
    assert result["passed"] is False
    assert "nguy hiểm" in result["reason"] or "Non-critical" in result["reason"]


def test_validator_accepts_appropriate_for_borderline():
    """Appropriate output for borderline_high → passes validation."""
    good_output = {
        "explanation": "Đường huyết của bạn hơi cao, cần theo dõi thêm.",
        "why_it_matters": "Tiền tiểu đường cần chú ý.",
        "what_to_monitor": "Kiểm tra 3 tháng/lần.",
        "what_to_ask_doctor": "Chế độ ăn nào phù hợp?",
        "next_step": "Tái kiểm tra sau 3 tháng.",
    }
    result = validate_explanation(good_output, GLUCOSE_57_INPUT)
    assert result["passed"] is True


def test_validator_rejects_normal_for_high():
    """'bình thường' in output for high status → rejected."""
    high_input = {**GLUCOSE_57_INPUT, "canonical_status": "high"}
    bad_output = {
        "explanation": "Chỉ số hoàn toàn bình thường, không đáng lo ngại.",
        "why_it_matters": "",
        "what_to_monitor": "",
        "what_to_ask_doctor": "",
        "next_step": "",
    }
    result = validate_explanation(bad_output, high_input)
    assert result["passed"] is False


def test_validator_rejects_alarming_for_normal():
    """'cao' in output for normal status → rejected."""
    normal_input = {**GLUCOSE_57_INPUT, "canonical_status": "normal"}
    bad_output = {
        "explanation": "Chỉ số đường huyết của bạn cao.",
        "why_it_matters": "",
        "what_to_monitor": "",
        "what_to_ask_doctor": "",
        "next_step": "",
    }
    result = validate_explanation(bad_output, normal_input)
    assert result["passed"] is False


def test_validator_rejects_normal_for_low():
    """'bình thường' in output for low status → rejected."""
    low_input = {**GLUCOSE_57_INPUT, "canonical_status": "low"}
    bad_output = {
        "explanation": "Chỉ số hoàn toàn bình thường.",
        "why_it_matters": "",
        "what_to_monitor": "",
        "what_to_ask_doctor": "",
        "next_step": "",
    }
    result = validate_explanation(bad_output, low_input)
    assert result["passed"] is False


def test_validator_rejects_urgent_when_doctor_not_required():
    """'cần gặp bác sĩ ngay' when doctor_review_required=False → rejected."""
    bad_output = {
        "explanation": "Cần gặp bác sĩ ngay hôm nay.",
        "why_it_matters": "",
        "what_to_monitor": "",
        "what_to_ask_doctor": "",
        "next_step": "",
    }
    result = validate_explanation(bad_output, GLUCOSE_57_INPUT)
    assert result["passed"] is False


# ---------------------------------------------------------------------------
# Deterministic fallback tests
# ---------------------------------------------------------------------------


def test_fallback_borderline_high_not_dangerous():
    """Fallback for borderline_high must not contain 'nguy hiểm'."""
    fb = get_deterministic_fallback(GLUCOSE_57_INPUT)
    assert "nguy hiểm" not in fb["explanation"]
    assert "hơi cao" in fb["explanation"] or "theo dõi" in fb["explanation"]
    assert fb["validated"] is True
    assert fb["source"] == "deterministic_fallback"


def test_fallback_normal_says_normal():
    """Fallback for normal status must say 'bình thường'."""
    normal_input = {**GLUCOSE_57_INPUT, "canonical_status": "normal", "normalized_value": 85}
    fb = get_deterministic_fallback(normal_input)
    assert "bình thường" in fb["explanation"]


def test_fallback_high_mentions_doctor():
    """Fallback for high status should mention discussion with doctor."""
    high_input = {**GLUCOSE_57_INPUT, "canonical_status": "high"}
    fb = get_deterministic_fallback(high_input)
    # Not dangerous but suggests talking to doctor
    assert "bác sĩ" in fb["explanation"] or "theo dõi" in fb["explanation"]
    assert "nguy hiểm" not in fb["explanation"]


def test_glucose_502_mgdl_urgent_fallback():
    """Fallback for critical_high must mention bác sĩ."""
    urgent_input = {
        **GLUCOSE_57_INPUT,
        "normalized_value": 502,
        "canonical_status": "critical_high",
        "canonical_severity": "critical",
        "canonical_priority": "urgent",
        "doctor_review_required": True,
    }
    fb = get_deterministic_fallback(urgent_input)
    assert "bác sĩ" in fb["explanation"]
    assert fb["validated"] is True


def test_fallback_low_not_normal():
    """Fallback for low status must not reassure 'hoàn toàn bình thường' / 'không đáng lo'."""
    low_input = {**GLUCOSE_57_INPUT, "canonical_status": "low", "normalized_value": 60}
    fb = get_deterministic_fallback(low_input)
    # Must NOT say it's completely normal or nothing to worry about
    assert "hoàn toàn bình thường" not in fb["explanation"]
    assert "không đáng lo" not in fb["explanation"]
    assert "hoàn toàn ổn" not in fb["explanation"]
    # Must indicate that value is low and needs attention
    assert "thấp" in fb["explanation"] or "theo dõi" in fb["explanation"]


# ---------------------------------------------------------------------------
# Integration: generate_explanation
# ---------------------------------------------------------------------------


def test_generate_uses_fallback_when_claude_contradicts():
    """If Claude returns dangerous text for borderline → fallback is used."""
    with patch("app.services.clinical_explanation.get_client") as mock_client:
        mock_response = MagicMock()
        mock_response.content[0].text = (
            '{"explanation": "Rất nguy hiểm, cần cấp cứu ngay!", '
            '"why_it_matters": "", "what_to_monitor": "", '
            '"what_to_ask_doctor": "", "next_step": ""}'
        )
        mock_client.return_value.messages.create.return_value = mock_response

        result = generate_explanation("test-id-001", GLUCOSE_57_INPUT, use_cache=False)
        assert result["source"] in (
            "fallback_after_validation_failure",
            "deterministic_fallback",
        )
        assert "nguy hiểm" not in result["explanation"]


def test_generate_uses_claude_when_output_valid():
    """Valid Claude output → returned with source='claude'."""
    valid_claude_text = (
        '{"explanation": "Đường huyết hơi cao, cần chú ý.", '
        '"why_it_matters": "Nguy cơ tiền đái tháo đường.", '
        '"what_to_monitor": "Kiểm tra 3 tháng.", '
        '"what_to_ask_doctor": "Chế độ ăn nào?", '
        '"next_step": "Tái kiểm tra."}'
    )
    with patch("app.services.clinical_explanation.get_client") as mock_client:
        mock_response = MagicMock()
        mock_response.content[0].text = valid_claude_text
        mock_client.return_value.messages.create.return_value = mock_response

        result = generate_explanation("test-id-002", GLUCOSE_57_INPUT, use_cache=False)
        assert result["source"] == "claude"
        assert result["validated"] is True


def test_generate_fallback_on_missing_required_field():
    """Missing canonical_status → fallback immediately."""
    bad_input = {**GLUCOSE_57_INPUT}
    del bad_input["canonical_status"]

    result = generate_explanation("test-id-003", bad_input, use_cache=False)
    assert result["source"] == "fallback_missing_field"
    assert result["validated"] is True


def test_generate_fallback_on_claude_error():
    """Claude raises exception → deterministic fallback returned."""
    with patch("app.services.clinical_explanation.get_client") as mock_client:
        mock_client.side_effect = RuntimeError("Network error")

        result = generate_explanation("test-id-004", GLUCOSE_57_INPUT, use_cache=False)
        assert result["source"] == "fallback_after_error"
        assert result["validated"] is True


def test_generate_caches_valid_result(tmp_path, monkeypatch):
    """Valid Claude result is cached; second call returns from cache."""
    monkeypatch.setenv("EXPLANATION_CACHE_DIR", str(tmp_path))

    # Reload cache module with patched env
    import importlib

    import app.services.explanation_cache as ec_module

    importlib.reload(ec_module)
    import app.services.clinical_explanation as ce_module

    importlib.reload(ce_module)

    valid_claude_text = (
        '{"explanation": "Đường huyết hơi cao, cần chú ý.", '
        '"why_it_matters": "Nguy cơ tiền đái tháo đường.", '
        '"what_to_monitor": "Kiểm tra 3 tháng.", '
        '"what_to_ask_doctor": "Chế độ ăn nào?", '
        '"next_step": "Tái kiểm tra."}'
    )
    with patch("app.services.clinical_explanation.get_client") as mock_client:
        mock_response = MagicMock()
        mock_response.content[0].text = valid_claude_text
        mock_client.return_value.messages.create.return_value = mock_response

        result1 = ce_module.generate_explanation("cached-id-001", GLUCOSE_57_INPUT, use_cache=True)
        assert result1["source"] == "claude"

        # Second call — Claude should NOT be called again
        result2 = ce_module.generate_explanation("cached-id-001", GLUCOSE_57_INPUT, use_cache=True)
        assert mock_client.return_value.messages.create.call_count == 1
        assert result2["explanation"] == result1["explanation"]


# ---------------------------------------------------------------------------
# Creatinine normal case
# ---------------------------------------------------------------------------


def test_creatinine_normal_not_dangerous():
    """Fallback for normal creatinine must say bình thường and not nguy hiểm."""
    creatinine_normal = {
        "biomarker_name": "creatinine",
        "biomarker_display_name": "Creatinine",
        "normalized_value": 0.93,
        "normalized_unit": "mg/dL",
        "original_value": 82.2,
        "original_unit": "µmol/L",
        "reference_range_low": 0.6,
        "reference_range_high": 1.2,
        "canonical_status": "normal",
        "canonical_severity": "none",
        "canonical_priority": "routine",
        "doctor_review_required": False,
        "safety_flags": [],
        "rule_id": "creatinine_adult",
        "evidence_strength": "high",
    }
    fb = get_deterministic_fallback(creatinine_normal)
    assert "nguy hiểm" not in fb["explanation"]
    assert "bình thường" in fb["explanation"]


# ---------------------------------------------------------------------------
# Security: no frontend direct Anthropic import
# ---------------------------------------------------------------------------


def test_no_frontend_direct_claude_call():
    """Frontend source files must not directly import the @anthropic-ai SDK.

    We grep for actual SDK import/require statements only, not the plain word
    'anthropic' which legitimately appears in test-description strings and
    assertion regex literals (e.g. ExplanationSection.test.tsx).
    """
    # grep -E matches actual SDK imports: `from '@anthropic-ai/...'` or
    # `require('@anthropic-ai/...')`.  Test files that merely mention the word
    # 'anthropic' in describe/it strings or .not.toMatch(/@anthropic-ai/)
    # patterns do NOT match this pattern and are correctly excluded.
    result = subprocess.run(
        [
            "grep",
            "-rE",
            r"from ['\"]@anthropic-ai|require\(['\"]@anthropic-ai",
            "frontend/src/",
            "--include=*.ts",
            "--include=*.tsx",
            "-l",
        ],
        capture_output=True,
        text=True,
        cwd="/Users/pth/Developer/Metocare",
    )
    assert result.stdout.strip() == "", (
        f"Frontend directly imports @anthropic-ai SDK (must go via backend only): {result.stdout}"
    )
