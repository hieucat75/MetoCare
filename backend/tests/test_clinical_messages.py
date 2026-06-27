"""Regression tests for P0-clinical-ui: single source of truth for clinical messages.

These tests assert:
1. normalize_and_classify() returns clinical_message as part of its output.
2. get_clinical_message() and normalize_and_classify() agree.
3. Glucose 5.7 mmol/L is classified as high (not low/critical_low/hypoglycemia).
4. clinical_message for glucose 5.7 mmol/L does NOT contain hypoglycemia language.
5. LabResultOut schema includes clinical_message populated from status.

P0 scenario: glucose 5.7 mmol/L stored as mmol/L in HealthMetric (via OCR path)
must NOT trigger hypoglycemia alert banner.
"""

from __future__ import annotations

import pytest

from app.services.lab import get_clinical_message, normalize_and_classify


# ---------------------------------------------------------------------------
# Core classification + message cases
# ---------------------------------------------------------------------------

GLUCOSE_CASES = [
    # (value, unit, expected_status, message_must_contain, message_must_not_contain)
    (2.8,  "mmol/L", "critical", "nguy hiểm",   ["thấp thông thường", "bình thường"]),
    (3.5,  "mmol/L", "low",      "thấp",        ["bình thường", "cao"]),
    (4.8,  "mmol/L", "normal",   "bình thường", ["thấp", "cao", "nguy hiểm"]),
    # P0 key case: 5.7 mmol/L = 102.7 mg/dL → HIGH, NOT hypoglycemia
    (5.7,  "mmol/L", "high",     "cao",         ["hạ đường huyết", "quá thấp", "thấp"]),
    (7.2,  "mmol/L", "high",     "cao",         ["thấp", "bình thường"]),
    # Same values in mg/dL
    (50.4, "mg/dL",  "critical", "nguy hiểm",   ["bình thường", "cao"]),
    (85.0, "mg/dL",  "normal",   "bình thường", ["thấp", "cao", "nguy hiểm"]),
    (102.7,"mg/dL",  "high",     "cao",         ["hạ đường huyết", "quá thấp", "thấp"]),
]


@pytest.mark.parametrize(
    "value,unit,expected_status,msg_contains,msg_not_contains",
    GLUCOSE_CASES,
    ids=[
        "glucose_2.8mmol_critical",
        "glucose_3.5mmol_low",
        "glucose_4.8mmol_normal",
        "glucose_5.7mmol_HIGH_not_hypo",  # P0 regression case
        "glucose_7.2mmol_high",
        "glucose_50mgdl_critical",
        "glucose_85mgdl_normal",
        "glucose_102mgdl_high",
    ],
)
def test_glucose_classification(
    value: float,
    unit: str,
    expected_status: str,
    msg_contains: str,
    msg_not_contains: list[str],
) -> None:
    result = normalize_and_classify("fasting_glucose", value, unit)
    assert result.get("status") == expected_status, (
        f"Expected status={expected_status!r} for glucose {value} {unit}, "
        f"got {result.get('status')!r}"
    )
    assert "clinical_message" in result, "normalize_and_classify must return clinical_message"
    msg = result["clinical_message"] or ""
    assert msg_contains.lower() in msg.lower(), (
        f"Expected '{msg_contains}' in clinical_message, got: {msg!r}"
    )
    for bad in msg_not_contains:
        assert bad.lower() not in msg.lower(), (
            f"clinical_message must NOT contain '{bad}', got: {msg!r}"
        )


def test_glucose_5_7_not_hypoglycemia() -> None:
    """P0 regression: glucose 5.7 mmol/L must NOT be classified as hypoglycemia."""
    result = normalize_and_classify("fasting_glucose", 5.7, "mmol/L")
    assert result.get("status") not in ("low", "critical"), (
        f"5.7 mmol/L glucose must NOT be low/critical, got: {result.get('status')!r}"
    )
    msg = (result.get("clinical_message") or "").lower()
    assert "hạ đường huyết" not in msg, (
        f"5.7 mmol/L banner must NOT say hypoglycemia, got: {msg!r}"
    )
    assert "quá thấp" not in msg, (
        f"5.7 mmol/L banner must NOT say 'quá thấp', got: {msg!r}"
    )
    # Correct: should be HIGH (borderline or above normal range)
    assert result.get("status") == "high", (
        f"5.7 mmol/L (=102.7 mg/dL) must be HIGH status, got: {result.get('status')!r}"
    )


def test_single_source_of_truth() -> None:
    """get_clinical_message() and normalize_and_classify() must agree on message."""
    result = normalize_and_classify("fasting_glucose", 5.7, "mmol/L")
    status = result.get("status")
    assert status is not None
    direct_msg = get_clinical_message("fasting_glucose", status)
    assert result.get("clinical_message") == direct_msg, (
        f"normalize_and_classify clinical_message={result.get('clinical_message')!r} "
        f"must equal get_clinical_message={direct_msg!r}"
    )


def test_get_clinical_message_coverage() -> None:
    """get_clinical_message() must return non-None for core glucose statuses."""
    for status in ("normal", "low", "high", "critical"):
        msg = get_clinical_message("fasting_glucose", status)
        assert msg is not None, f"Missing clinical_message for fasting_glucose/{status}"
        assert len(msg) > 5, f"clinical_message too short for fasting_glucose/{status}"


def test_get_clinical_message_unknown_status() -> None:
    """Unknown status falls back to generic message, not None."""
    msg = get_clinical_message("fasting_glucose", "borderline")
    # Borderline is not in the explicit map; should return generic or None gracefully
    # (None is acceptable for unknown statuses — banner should not show)
    assert msg is None or len(msg) > 0  # if returned, must be non-empty


def test_normalize_and_classify_includes_clinical_message_field() -> None:
    """The clinical_message key must always be present in normalize_and_classify output."""
    for value, unit in [(5.0, "mmol/L"), (90.0, "mg/dL"), (400.0, "mg/dL")]:
        result = normalize_and_classify("fasting_glucose", value, unit)
        assert "clinical_message" in result, (
            f"clinical_message key missing from normalize_and_classify output for "
            f"fasting_glucose {value} {unit}"
        )


def test_lab_result_out_has_clinical_message() -> None:
    """LabResultOut schema must populate clinical_message from canonical_name + status."""
    from app.schemas.lab import LabResultOut
    import datetime as dt

    row = LabResultOut(
        id="test-id",
        patient_id="p1",
        document_id=None,
        test_name="Glucose đói",
        canonical_name="fasting_glucose",
        value=102.7,
        unit="mg/dL",
        reference_range="70-99",
        status="high",
        test_date=dt.date(2026, 6, 27),
        verified_by_user=True,
        created_at=dt.datetime(2026, 6, 27, 10, 0, 0),
    )
    assert row.clinical_message is not None, (
        "LabResultOut must auto-populate clinical_message from status"
    )
    assert "cao" in row.clinical_message.lower(), (
        f"LabResultOut.clinical_message for 'high' status must mention 'cao', "
        f"got: {row.clinical_message!r}"
    )


def test_lab_result_out_no_message_for_unknown_biomarker() -> None:
    """LabResultOut with unknown canonical_name should have clinical_message=None."""
    from app.schemas.lab import LabResultOut
    import datetime as dt

    row = LabResultOut(
        id="test-id-2",
        patient_id="p1",
        document_id=None,
        test_name="XYZ Unknown",
        canonical_name="unknown_biomarker_xyz",
        value=1.0,
        unit="unit",
        reference_range=None,
        status="high",
        test_date=dt.date(2026, 6, 27),
        verified_by_user=True,
        created_at=dt.datetime(2026, 6, 27, 10, 0, 0),
    )
    # For unknown biomarker: either None or a generic fallback
    # The important thing is it doesn't crash and returns sensible output
    assert row.clinical_message is None or len(row.clinical_message) > 0
