"""Tests for new derived ratio metrics: TG/HDL, LDL/HDL, TC/HDL."""
from __future__ import annotations

from app.domain.derived_metrics import (
    compute_ldl_hdl_ratio_from_inputs,
    compute_tc_hdl_ratio_from_inputs,
    compute_tg_hdl_ratio_from_inputs,
)


class TestTgHdlRatio:
    def test_normal(self):
        # TG=80 mg/dL → 0.903 mmol/L, HDL=50 mg/dL → 1.293 mmol/L → ratio ~0.698 (normal <1.0)
        r = compute_tg_hdl_ratio_from_inputs({"triglyceride": 80.0, "hdl": 50.0})
        assert r.status == "normal"
        assert r.value is not None and r.value < 1.0

    def test_abnormal(self):
        r = compute_tg_hdl_ratio_from_inputs({"triglyceride": 265.71, "hdl": 38.67})
        assert r.status == "abnormal"

    def test_missing_hdl(self):
        r = compute_tg_hdl_ratio_from_inputs({"triglyceride": 150.0})
        assert r.status == "insufficient_data"
        assert r.value is None

    def test_missing_tg(self):
        r = compute_tg_hdl_ratio_from_inputs({"hdl": 50.0})
        assert r.status == "insufficient_data"

class TestLdlHdlRatio:
    def test_normal(self):
        r = compute_ldl_hdl_ratio_from_inputs({"ldl": 100.0, "hdl": 60.0})
        assert r.status == "normal"
        assert r.value is not None and r.value < 2.0

    def test_abnormal(self):
        r = compute_ldl_hdl_ratio_from_inputs({"ldl": 200.0, "hdl": 40.0})
        assert r.status == "abnormal"

    def test_missing(self):
        r = compute_ldl_hdl_ratio_from_inputs({"ldl": 100.0})
        assert r.status == "insufficient_data"

class TestTcHdlRatio:
    def test_normal(self):
        r = compute_tc_hdl_ratio_from_inputs({"total_cholesterol": 180.0, "hdl": 60.0})
        assert r.status == "normal"
        assert r.value is not None and r.value < 4.0

    def test_borderline(self):
        r = compute_tc_hdl_ratio_from_inputs({"total_cholesterol": 220.0, "hdl": 50.0})
        assert r.status == "borderline"

    def test_abnormal(self):
        r = compute_tc_hdl_ratio_from_inputs({"total_cholesterol": 280.0, "hdl": 40.0})
        assert r.status == "abnormal"

    def test_missing(self):
        r = compute_tc_hdl_ratio_from_inputs({"total_cholesterol": 200.0})
        assert r.status == "insufficient_data"
