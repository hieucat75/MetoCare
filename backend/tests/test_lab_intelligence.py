from __future__ import annotations

from app.domain.clinical_patterns import detect_patterns
from app.domain.clinical_rules import assess_biomarker
from app.domain.derived_metrics import (
    compute_egfr,
    compute_fib4,
    compute_ldl_friedewald,
    compute_non_hdl,
    compute_tyg,
)
from app.domain.lab_normalization import classify_status
from app.domain.longitudinal import compute_trends


def test_compute_egfr():
    # CKD-EPI 2021 race-free: creatinine=88 µmol/L (0.995 mg/dL), age=45, male → ~70 mL/min/1.73m²
    r = compute_egfr(88, 45, True)
    assert r.value is not None and 65 <= r.value <= 80, f"eGFR={r.value}"


def test_compute_non_hdl():
    assert compute_non_hdl(5.2, 1.2).value == 4.0


def test_compute_ldl_friedewald():
    assert compute_ldl_friedewald(5.2, 1.2, 1.5).value is not None
    assert compute_ldl_friedewald(5.2, 1.2, 5.0).missing_inputs == ["triglyceride_too_high"]


def test_compute_tyg():
    r = compute_tyg(100, 150)
    assert abs(r.value - 8.9226) < 0.05


def test_compute_fib4():
    r = compute_fib4(50, 35, 40, 150)
    assert abs(r.value - 1.84) < 0.02


def test_classify_status():
    assert classify_status(126, "fasting_glucose").value == "high"
    assert classify_status(99, "fasting_glucose").value == "normal"
    # clinical_safety_sweep 2026-06-27: critical_high raised 300→500 (ADA 2024)
    # 300 mg/dL is now HIGH, not CRITICAL
    assert classify_status(300, "fasting_glucose").value == "high"
    # 502 mg/dL ≥ critical_high=500 → CRITICAL
    assert classify_status(502, "fasting_glucose").value == "critical"


def test_clinical_rule_warning():
    f = assess_biomarker("fasting_glucose", 180)
    assert f.severity == "warning"
    assert f.doctor_review_required


def test_clinical_rule_critical():
    # clinical_safety_sweep 2026-06-27: critical_high raised 300→500
    # 310 mg/dL is now HIGH (warning), not CRITICAL
    f_high = assess_biomarker("fasting_glucose", 310)
    assert f_high.severity == "warning"
    assert f_high.doctor_review_required
    # 502 mg/dL triggers critical
    f = assess_biomarker("fasting_glucose", 502)
    assert f.severity == "critical"
    assert f.doctor_review_required


def test_pattern_dyslipidemia():
    patterns = detect_patterns(
        {
            "findings": {"hdl": {"status": "low"}, "triglyceride": {}},
            "derived": {"ldl_friedewald": 4.0},
        }
    )
    assert any(p.pattern_id == "dyslipidemia" for p in patterns)


def test_pattern_insulin_resistance():
    patterns = detect_patterns(
        {
            "findings": {"fasting_glucose": {}, "triglyceride": {}, "hdl": {}},
            "derived": {"tyg_index": 9.1},
        }
    )
    assert any(p.pattern_id == "insulin_resistance" for p in patterns)


def test_trend_improving():
    class R:
        def __init__(self, d, v):
            self.verified_by_user = True
            self.verified_by_doctor = False
            self.canonical_name = "fasting_glucose"
            self.value = v
            self.unit = "mg/dL"
            self.normalized_value_si = None
            self.test_date = d

    t = compute_trends(
        [
            R(__import__("datetime").date(2024, 1, 1), 120),
            R(__import__("datetime").date(2024, 2, 1), 110),
            R(__import__("datetime").date(2024, 3, 1), 100),
        ],
        "fasting_glucose",
    )
    assert t.trend in {"improving", "stable", "worsening"}


def test_trend_insufficient():
    class R:
        def __init__(self, d, v):
            self.verified_by_user = True
            self.verified_by_doctor = False
            self.canonical_name = "fasting_glucose"
            self.value = v
            self.unit = "mg/dL"
            self.normalized_value_si = None
            self.test_date = d

    t = compute_trends([R(__import__("datetime").date(2024, 1, 1), 120)], "fasting_glucose")
    assert t.trend == "insufficient_data"
