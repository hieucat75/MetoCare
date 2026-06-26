from __future__ import annotations

import math

from app.domain.derived_metrics import (
    compute_egfr,
    compute_fib4,
    compute_ldl_friedewald,
    compute_non_hdl,
    compute_tyg,
)


def test_egfr_precision():
    # CKD-EPI 2021 race-free: creatinine=88 µmol/L (0.995 mg/dL), age=45, male
    # Expected ~70 mL/min/1.73m² (normal-range for this creatinine level)
    r = compute_egfr(88, 45, True)
    assert 65 <= r.value <= 80, f"eGFR={r.value} outside expected CKD-EPI 2021 range"


def test_non_hdl_precision():
    r = compute_non_hdl(5.2, 1.2)
    assert r.value == 4.0


def test_ldl_friedewald_precision():
    r = compute_ldl_friedewald(5.2, 1.2, 1.5)
    assert r.value is not None
    assert r.status in {"normal", "borderline", "abnormal"}
    r2 = compute_ldl_friedewald(5.2, 1.2, 5.0)
    assert r2.value is None
    assert "triglyceride_too_high" in r2.missing_inputs


def test_tyg_precision():
    r = compute_tyg(100, 150)
    assert abs(r.value - math.log(100 * 150 / 2)) < 0.01


def test_fib4_precision():
    r = compute_fib4(50, 35, 40, 150)
    assert abs(r.value - 1.84) < 0.02
