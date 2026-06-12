"""Lab interpreter tests — classification, normalization, safe explanations."""

from __future__ import annotations

from app.domain import lab_interpreter, policies
from app.domain.lab_interpreter import LabStatus, RawLabValue


def test_normalize_aliases():
    assert lab_interpreter.normalize_biomarker("Glucose") == "fasting_glucose"
    assert lab_interpreter.normalize_biomarker("đường huyết đói") == "fasting_glucose"
    assert lab_interpreter.normalize_biomarker("HbA1c") == "hba1c"
    assert lab_interpreter.normalize_biomarker("mỡ máu") == "triglyceride"
    assert lab_interpreter.normalize_biomarker("không biết chỉ số này") is None


def test_classify_boundaries():
    assert lab_interpreter.classify_value("fasting_glucose", 90) == LabStatus.NORMAL
    assert lab_interpreter.classify_value("fasting_glucose", 120) == LabStatus.HIGH
    # 60 is below ref_low (70) but above critical_low (54) -> LOW
    assert lab_interpreter.classify_value("fasting_glucose", 60) == LabStatus.LOW
    # 50 is at/below critical_low (54) -> CRITICAL
    assert lab_interpreter.classify_value("fasting_glucose", 50) == LabStatus.CRITICAL
    assert lab_interpreter.classify_value("fasting_glucose", 320) == LabStatus.CRITICAL


def test_unknown_biomarker_needs_verification():
    b = lab_interpreter.interpret_value(RawLabValue("mystery_marker", 1.0))
    assert b.status == LabStatus.UNKNOWN
    assert b.needs_verification is True


def test_low_ocr_confidence_flags_verification():
    b = lab_interpreter.interpret_value(RawLabValue("HDL", 38.0, ocr_confidence=0.5))
    assert b.needs_verification is True
    assert "xác nhận" in b.patient_note


def test_panel_explanation_is_safe():
    panel = [
        RawLabValue("Glucose", 320.0, "mg/dL"),       # critical
        RawLabValue("Triglyceride", 220.0, "mg/dL"),  # high
        RawLabValue("HDL", 60.0, "mg/dL"),            # normal
    ]
    result = lab_interpreter.interpret_panel(panel)
    assert "fasting_glucose" in result.critical
    assert "triglyceride" in result.abnormal
    # mandatory disclaimer present, no diagnosis assertion language
    assert policies.DISCLAIMER_VI in result.patient_explanation
    assert "bạn bị" not in result.patient_explanation.lower()
    # doctor summary is data-only
    assert "no AI conclusion" in result.doctor_summary


def test_mock_ocr_extract_is_deterministic():
    a = lab_interpreter.mock_ocr_extract("doc-1")
    b = lab_interpreter.mock_ocr_extract("doc-1")
    assert [(x.test_name, x.value) for x in a] == [(x.test_name, x.value) for x in b]
