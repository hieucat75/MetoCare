"""Tests for Engine 1 — PatientContextEngine."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.domain.patient_context import (
    LifestyleProfileMedicationProvider,
    PatientContext,
    PatientContextEngine,
    PatientContextInput,
    _compute_cv_risk_category,
    _parse_condition_flags,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_profile(**kwargs) -> Any:
    """Create a mock PatientProfile with given attributes."""
    profile = MagicMock()
    defaults = {
        "id": "patient-123",
        "gender": None,
        "dob": None,
        "height_cm": None,
        "weight_kg": None,
        "waist_cm": None,
        "known_conditions": None,
        "lifestyle_profile": None,
        "family_history": None,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(profile, k, v)
    return profile


# ── Engine 1: PatientContextEngine Tests ──────────────────────────────────────

class TestBuildFromNoneProfile:
    """test_build_from_none_profile: returns valid context with all defaults."""

    def test_no_profile_returns_valid_context(self):
        engine = PatientContextEngine(profile=None)
        ctx = engine.build()
        assert isinstance(ctx, PatientContext)
        assert ctx.age is None
        assert ctx.sex is None
        assert ctx.bmi is None
        assert ctx.has_diabetes is False
        assert ctx.has_hypertension is False
        assert ctx.has_cvd_history is False
        assert ctx.medications == []
        assert ctx.cv_risk_category == "low"
        assert 0.0 <= ctx.context_completeness <= 1.0
        assert isinstance(ctx.missing_context, list)
        assert len(ctx.missing_context) > 0  # many fields missing


class TestBMIComputed:
    """test_bmi_computed: height=170, weight=70 → bmi=24.2."""

    def test_bmi_calculation(self):
        engine = PatientContextEngine(
            profile=None,
            override=PatientContextInput(height_cm=170.0, weight_kg=70.0),
        )
        ctx = engine.build()
        assert ctx.bmi == pytest.approx(24.2, rel=0.01)

    def test_bmi_from_profile(self):
        profile = _mock_profile(height_cm=160.0, weight_kg=64.0)
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert ctx.bmi == pytest.approx(25.0, rel=0.01)

    def test_bmi_none_when_height_missing(self):
        engine = PatientContextEngine(
            profile=None,
            override=PatientContextInput(weight_kg=70.0),
        )
        ctx = engine.build()
        assert ctx.bmi is None

    def test_bmi_override_takes_priority(self):
        """Override values take priority over profile values."""
        profile = _mock_profile(height_cm=160.0, weight_kg=60.0)
        engine = PatientContextEngine(
            profile=profile,
            override=PatientContextInput(height_cm=170.0, weight_kg=70.0),
        )
        ctx = engine.build()
        assert ctx.bmi == pytest.approx(24.2, rel=0.01)


class TestCVRiskVeryHighWithCVD:
    """test_cv_risk_very_high_with_cvd: has_cvd_history=True → "very_high"."""

    def test_cvd_history_very_high(self):
        result = _compute_cv_risk_category(
            age=50, sex="male", is_smoker=False,
            has_cvd_history=True, has_diabetes=False, has_hypertension=False,
        )
        assert result == "very_high"

    def test_cvd_history_from_conditions_text(self):
        profile = _mock_profile(known_conditions="Bệnh nhân có tiền sử nhồi máu cơ tim 2020")
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert ctx.has_cvd_history is True
        assert ctx.cv_risk_category == "very_high"

    def test_stroke_triggers_very_high(self):
        profile = _mock_profile(known_conditions="đột quỵ não 2019")
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert ctx.has_cvd_history is True
        assert ctx.cv_risk_category == "very_high"


class TestCVRiskHighElderlyMale:
    """test_cv_risk_high_elderly_male: age=65, male, smoker → "high"."""

    def test_elderly_male_smoker_high(self):
        result = _compute_cv_risk_category(
            age=65, sex="male", is_smoker=True,
            has_cvd_history=False, has_diabetes=False, has_hypertension=False,
        )
        assert result == "high"

    def test_elderly_male_no_smoker_still_intermediate(self):
        # age=65 (+3), male (+1) = 4 → intermediate
        result = _compute_cv_risk_category(
            age=65, sex="male", is_smoker=False,
            has_cvd_history=False, has_diabetes=False, has_hypertension=False,
        )
        assert result == "intermediate"

    def test_diabetes_age_40_high(self):
        result = _compute_cv_risk_category(
            age=40, sex="female", is_smoker=False,
            has_cvd_history=False, has_diabetes=True, has_hypertension=False,
        )
        assert result == "high"

    def test_young_nonsmoker_low(self):
        result = _compute_cv_risk_category(
            age=30, sex="female", is_smoker=False,
            has_cvd_history=False, has_diabetes=False, has_hypertension=False,
        )
        assert result == "low"


class TestMedicationParsingFromJSON:
    """test_medication_parsing_from_json: lifestyle_profile JSON with medications list."""

    def test_medication_list_parsed(self):
        profile = _mock_profile(
            lifestyle_profile='{"medications": ["statin", "metformin"], "exercise": "moderate"}'
        )
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert "statin" in ctx.medications
        assert "metformin" in ctx.medications

    def test_medication_string_parsed(self):
        profile = _mock_profile(
            lifestyle_profile='{"medications": "statin, aspirin"}'
        )
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert "statin" in ctx.medications
        assert "aspirin" in ctx.medications

    def test_invalid_json_does_not_crash(self):
        profile = _mock_profile(lifestyle_profile="{invalid json}")
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert isinstance(ctx.medications, list)

    def test_override_medications_take_priority(self):
        profile = _mock_profile(lifestyle_profile='{"medications": ["statin"]}')
        engine = PatientContextEngine(
            profile=profile,
            override=PatientContextInput(medications=["insulin", "metformin"]),
        )
        ctx = engine.build()
        assert "insulin" in ctx.medications
        assert "metformin" in ctx.medications
        assert "statin" not in ctx.medications  # override replaces profile


class TestMedicationKeywordScan:
    """test_medication_keyword_scan: known_conditions contains "rosuvastatin" → ["statin"]."""

    def test_rosuvastatin_maps_to_statin(self):
        provider = LifestyleProfileMedicationProvider(
            lifestyle_profile_json=None,
            known_conditions="Đang dùng rosuvastatin 10mg/ngày",
        )
        meds = provider.get_medications("p1")
        assert "statin" in meds

    def test_atorvastatin_maps_to_statin(self):
        provider = LifestyleProfileMedicationProvider(
            lifestyle_profile_json=None,
            known_conditions="Lipitor (atorvastatin) 20mg",
        )
        meds = provider.get_medications("p1")
        assert "statin" in meds

    def test_glucophage_maps_to_metformin(self):
        provider = LifestyleProfileMedicationProvider(
            lifestyle_profile_json=None,
            known_conditions="Điều trị bằng Glucophage",
        )
        meds = provider.get_medications("p1")
        assert "metformin" in meds

    def test_multiple_medications_detected(self):
        provider = LifestyleProfileMedicationProvider(
            lifestyle_profile_json=None,
            known_conditions="Đang dùng atorvastatin và lisinopril",
        )
        meds = provider.get_medications("p1")
        assert "statin" in meds
        assert "ace_inhibitor" in meds

    def test_no_medications_empty_list(self):
        provider = LifestyleProfileMedicationProvider(
            lifestyle_profile_json=None,
            known_conditions="Không có bệnh nền",
        )
        meds = provider.get_medications("p1")
        assert meds == []


class TestConditionFlagsFromText:
    """test_condition_flags_from_text: known_conditions contains "tiểu đường" → has_diabetes=True."""

    def test_diabetes_vi_detected(self):
        flags = _parse_condition_flags("Bệnh nhân có tiểu đường type 2")
        assert flags["has_diabetes"] is True

    def test_hypertension_vi_detected(self):
        flags = _parse_condition_flags("Tăng huyết áp, đang điều trị")
        assert flags["has_hypertension"] is True

    def test_multiple_conditions_detected(self):
        flags = _parse_condition_flags("Tiểu đường + tăng huyết áp + rối loạn lipid")
        assert flags["has_diabetes"] is True
        assert flags["has_hypertension"] is True
        assert flags["has_dyslipidemia"] is True

    def test_english_conditions_detected(self):
        flags = _parse_condition_flags("Type 2 diabetes mellitus, hypertension, CKD stage 3")
        assert flags["has_diabetes"] is True
        assert flags["has_hypertension"] is True
        assert flags["has_ckd"] is True

    def test_empty_text_all_false(self):
        flags = _parse_condition_flags(None)
        assert all(v is False for v in flags.values())

    def test_fatty_liver_detected(self):
        flags = _parse_condition_flags("Gan nhiễm mỡ độ 1, không có bệnh nền khác")
        assert flags["has_fatty_liver"] is True

    def test_no_false_positives(self):
        flags = _parse_condition_flags("Không có bệnh nền gì đặc biệt")
        assert flags["has_diabetes"] is False
        assert flags["has_cvd_history"] is False


class TestCompletenessEmpty:
    """test_completeness_empty: no profile → low completeness, missing_context non-empty."""

    def test_empty_profile_low_completeness(self):
        engine = PatientContextEngine(profile=None)
        ctx = engine.build()
        # With no data except smoking (always has bool), completeness should be low
        assert ctx.context_completeness < 0.3
        assert len(ctx.missing_context) >= 4  # multiple fields missing

    def test_missing_context_contains_expected_fields(self):
        engine = PatientContextEngine(profile=None)
        ctx = engine.build()
        # These are all expected to be missing with no profile
        missing = ctx.missing_context
        assert "Tuổi" in missing
        assert "Giới tính" in missing
        assert "Vòng eo" in missing


class TestCompletenessFull:
    """test_completeness_full: all fields → high completeness."""

    def test_full_profile_high_completeness(self):
        profile = _mock_profile(
            gender="female",
            dob="1975-05-15",
            height_cm=160.0,
            weight_kg=60.0,
            waist_cm=78.0,
            known_conditions="Không có bệnh nền",
            family_history="Cha có tiểu đường",
            lifestyle_profile='{"medications": ["aspirin"], "exercise": "moderate"}',
        )
        engine = PatientContextEngine(
            profile=profile,
            override=PatientContextInput(
                is_smoker=False,
                is_vegetarian=False,
                exercise_level="moderate",
            ),
        )
        ctx = engine.build()
        # With all fields filled: age, sex, height/weight, waist, conditions,
        # medications, exercise, smoking, diet, family_history → high completeness
        assert ctx.context_completeness >= 0.7

    def test_age_computed_from_dob(self):
        profile = _mock_profile(dob="1980-01-01")
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert ctx.age is not None
        assert ctx.age >= 40  # Born 1980, current year >= 2024

    def test_invalid_dob_returns_none_age(self):
        profile = _mock_profile(dob="invalid-date")
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert ctx.age is None


class TestOnMedication:
    """Test PatientContext.on_medication helper."""

    def test_on_medication_case_insensitive(self):
        ctx = PatientContext(medications=["Statin", "METFORMIN"])
        assert ctx.on_medication("statin") is True
        assert ctx.on_medication("metformin") is True
        assert ctx.on_medication("insulin") is False

    def test_on_medication_empty(self):
        ctx = PatientContext(medications=[])
        assert ctx.on_medication("statin") is False


class TestBMIHelpers:
    """Test PatientContext helper methods."""

    def test_is_overweight(self):
        ctx = PatientContext(bmi=26.0)
        assert ctx.is_overweight() is True

    def test_not_overweight(self):
        ctx = PatientContext(bmi=22.0)
        assert ctx.is_overweight() is False

    def test_is_obese(self):
        ctx = PatientContext(bmi=31.0)
        assert ctx.is_obese() is True
        assert ctx.is_overweight() is True

    def test_has_metabolic_risk_diabetes(self):
        ctx = PatientContext(has_diabetes=True)
        assert ctx.has_metabolic_risk() is True

    def test_has_metabolic_risk_overweight(self):
        ctx = PatientContext(bmi=27.0)
        assert ctx.has_metabolic_risk() is True


class TestLifestyleParsingFromProfile:
    """Test lifestyle parsing from lifestyle_profile text."""

    def test_smoker_detected_vi(self):
        profile = _mock_profile(lifestyle_profile="Bệnh nhân hút thuốc 10 điếu/ngày")
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert ctx.is_smoker is True

    def test_alcohol_detected(self):
        profile = _mock_profile(lifestyle_profile="Uống rượu 2 lần/tuần")
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert ctx.drinks_alcohol is True

    def test_vegetarian_detected(self):
        profile = _mock_profile(lifestyle_profile="Ăn chay trường")
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert ctx.is_vegetarian is True

    def test_exercise_active_detected(self):
        profile = _mock_profile(lifestyle_profile="Tập gym 5 ngày/tuần, vận động nhiều")
        engine = PatientContextEngine(profile=profile)
        ctx = engine.build()
        assert ctx.exercise_level == "active"
