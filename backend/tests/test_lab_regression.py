"""Golden-master regression tests for hospital-specific OCR lab reports.

These tests verify that parse_lab_text output matches expected JSON fixtures.
A test failure signals a regression in the parser or interpreter.

Conversion factors (SI → canonical):
  glucose:          mmol/L x 18.018 -> mg/dL
  cholesterol/ldl/hdl: mmol/L x 38.67 -> mg/dL
  triglyceride:     mmol/L x 88.57  -> mg/dL
  tsh:              uIU/mL x 1.0    -> mIU/L  (units normalise, value unchanged)

Physiological plausibility bounds are enforced in lab_parser.parse_lab_text:
  values outside [physiological_min, physiological_max] -> ocr_confidence=0.0
  NOTE: the NUMBER regex caps contiguous digit runs at 3 digits, so
  implausibly large integers must be expressed as decimals (e.g. 250.0 not 2500).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.lab_interpreter import LabStatus, classify_value
from app.services import lab_parser

DATA = Path(__file__).parent / "data" / "lab_reports"


def _load_fixture(hospital: str, name: str = "report_01"):
    txt_path = DATA / hospital / (name + ".txt")
    json_path = DATA / hospital / (name + ".json")
    txt = txt_path.read_text(encoding="utf-8")
    exp = json.loads(json_path.read_text(encoding="utf-8"))
    parsed = lab_parser.parse_lab_text(txt)
    return parsed, exp


def _find(parsed, canonical: str):
    return next((v for v in parsed if v.test_name == canonical), None)


# ---------------------------------------------------------------------------
# Vinmec — SI units, all-normal panel except LDL
# ---------------------------------------------------------------------------


class TestVinmecGoldenMaster:
    """Vinmec report: SI input (mmol/L) → mg/dL after conversion."""

    def test_glucose_converted_from_si(self):
        parsed, exp = _load_fixture("vinmec")
        v = _find(parsed, "fasting_glucose")
        assert v is not None, "fasting_glucose not found in vinmec parse"
        assert v.unit == "mg/dL"
        expected = exp["expected_biomarkers"]["fasting_glucose"]["value_mg_dl"]
        assert abs(v.value - expected) < 0.01
        assert v.ocr_confidence == 1.0

    def test_cholesterol_converted_from_si(self):
        parsed, exp = _load_fixture("vinmec")
        v = _find(parsed, "total_cholesterol")
        assert v is not None
        assert v.unit == "mg/dL"
        expected = exp["expected_biomarkers"]["total_cholesterol"]["value_mg_dl"]
        assert abs(v.value - expected) < 0.01

    def test_triglyceride_converted_from_si(self):
        parsed, exp = _load_fixture("vinmec")
        v = _find(parsed, "triglyceride")
        assert v is not None
        expected = exp["expected_biomarkers"]["triglyceride"]["value_mg_dl"]
        assert abs(v.value - expected) < 0.01

    def test_hdl_converted_from_si(self):
        parsed, exp = _load_fixture("vinmec")
        v = _find(parsed, "hdl")
        assert v is not None
        expected = exp["expected_biomarkers"]["hdl"]["value_mg_dl"]
        assert abs(v.value - expected) < 0.01

    def test_ldl_high_after_si_conversion(self):
        parsed, _ = _load_fixture("vinmec")
        v = _find(parsed, "ldl")
        assert v is not None
        # 2.90 mmol/L × 38.67 = 112.143 mg/dL > ref_high=99 → HIGH
        assert classify_value("ldl", v.value) == LabStatus.HIGH

    def test_tsh_unit_normalised_to_miu_l(self):
        """uIU/mL and µIU/mL normalise the same; si_factor=1.0 so value is unchanged."""
        parsed, exp = _load_fixture("vinmec")
        v = _find(parsed, "tsh")
        assert v is not None
        assert v.unit == "mIU/L"
        assert abs(v.value - exp["expected_biomarkers"]["tsh"]["value_mg_dl"]) < 0.01
        assert v.ocr_confidence == 1.0

    def test_ft4_extracted(self):
        parsed, exp = _load_fixture("vinmec")
        v = _find(parsed, "ft4")
        assert v is not None
        assert v.unit == "pmol/L"
        assert abs(v.value - 15.0) < 0.01

    def test_ft3_extracted(self):
        parsed, _ = _load_fixture("vinmec")
        v = _find(parsed, "ft3")
        assert v is not None
        assert abs(v.value - 4.2) < 0.01

    def test_hba1c_normal(self):
        parsed, _ = _load_fixture("vinmec")
        v = _find(parsed, "hba1c")
        assert v is not None
        assert classify_value("hba1c", v.value) == LabStatus.NORMAL

    def test_alt_normal(self):
        parsed, _ = _load_fixture("vinmec")
        v = _find(parsed, "alt")
        assert v is not None
        assert classify_value("alt", v.value) == LabStatus.NORMAL

    def test_ast_normal(self):
        parsed, _ = _load_fixture("vinmec")
        v = _find(parsed, "ast")
        assert v is not None
        assert classify_value("ast", v.value) == LabStatus.NORMAL

    def test_all_vinmec_biomarkers_extracted(self):
        """Every canonical key in the fixture JSON must appear in parser output."""
        parsed, exp = _load_fixture("vinmec")
        found = {v.test_name for v in parsed}
        for canonical in exp["expected_biomarkers"]:
            assert canonical in found, f"{canonical} missing from vinmec parse"

    def test_no_zero_confidence_values(self):
        """All vinmec values are within physiological bounds → confidence must be 1.0."""
        parsed, _ = _load_fixture("vinmec")
        for v in parsed:
            assert v.ocr_confidence == 1.0, (
                f"{v.test_name}={v.value} has unexpected confidence {v.ocr_confidence}"
            )


# ---------------------------------------------------------------------------
# Medlatec — metabolic syndrome panel (multiple HIGH, one LOW)
# ---------------------------------------------------------------------------


class TestMedlatecGoldenMaster:
    """Medlatec report: elevated glucose, lipids, ALT; low HDL."""

    def test_glucose_elevated_value(self):
        parsed, exp = _load_fixture("medlatec")
        v = _find(parsed, "fasting_glucose")
        assert v is not None
        expected = exp["expected_biomarkers"]["fasting_glucose"]["value_mg_dl"]
        assert abs(v.value - expected) < 0.01

    def test_glucose_classified_high(self):
        parsed, _ = _load_fixture("medlatec")
        v = _find(parsed, "fasting_glucose")
        assert v is not None
        # 6.50 mmol/L × 18.018 = 117.117 mg/dL > ref_high=99
        assert classify_value("fasting_glucose", v.value) == LabStatus.HIGH

    def test_alt_classified_high(self):
        parsed, _ = _load_fixture("medlatec")
        v = _find(parsed, "alt")
        assert v is not None
        # 68.0 U/L > ref_high=56
        assert classify_value("alt", v.value) == LabStatus.HIGH

    def test_total_cholesterol_high(self):
        parsed, _ = _load_fixture("medlatec")
        v = _find(parsed, "total_cholesterol")
        assert v is not None
        # 6.20 × 38.67 = 239.754 > ref_high=199
        assert classify_value("total_cholesterol", v.value) == LabStatus.HIGH

    def test_triglyceride_elevated(self):
        parsed, _ = _load_fixture("medlatec")
        v = _find(parsed, "triglyceride")
        assert v is not None
        # 2.50 × 88.57 = 221.425 > ref_high=149
        assert classify_value("triglyceride", v.value) == LabStatus.HIGH

    def test_hdl_low(self):
        parsed, _ = _load_fixture("medlatec")
        v = _find(parsed, "hdl")
        assert v is not None
        # 0.85 × 38.67 = 32.8695 < ref_low=40
        assert classify_value("hdl", v.value) == LabStatus.LOW

    def test_ldl_high(self):
        parsed, _ = _load_fixture("medlatec")
        v = _find(parsed, "ldl")
        assert v is not None
        # 4.10 × 38.67 = 158.547 > ref_high=99
        assert classify_value("ldl", v.value) == LabStatus.HIGH

    def test_hba1c_high(self):
        parsed, _ = _load_fixture("medlatec")
        v = _find(parsed, "hba1c")
        assert v is not None
        # 6.2% > ref_high=5.6
        assert classify_value("hba1c", v.value) == LabStatus.HIGH

    def test_all_medlatec_biomarkers_extracted(self):
        parsed, exp = _load_fixture("medlatec")
        found = {v.test_name for v in parsed}
        for canonical in exp["expected_biomarkers"]:
            assert canonical in found, f"{canonical} missing from medlatec parse"


# ---------------------------------------------------------------------------
# Tam Anh — thyroid panel (hypothyroid pattern: high TSH, low FT4+FT3)
# ---------------------------------------------------------------------------


class TestTamAnhGoldenMaster:
    """Tam Anh report: hypothyroid pattern — high TSH, low FT3 and FT4."""

    def test_tsh_value(self):
        parsed, exp = _load_fixture("tam_anh")
        v = _find(parsed, "tsh")
        assert v is not None
        expected = exp["expected_biomarkers"]["tsh"]["value_mg_dl"]
        assert abs(v.value - expected) < 0.01
        assert v.unit == "mIU/L"

    def test_tsh_high(self):
        parsed, _ = _load_fixture("tam_anh")
        v = _find(parsed, "tsh")
        assert v is not None
        # 8.50 mIU/L > ref_high=4.0
        assert classify_value("tsh", v.value) == LabStatus.HIGH

    def test_ft4_low(self):
        parsed, _ = _load_fixture("tam_anh")
        v = _find(parsed, "ft4")
        assert v is not None
        # 9.5 pmol/L < ref_low=12.0
        assert classify_value("ft4", v.value) == LabStatus.LOW

    def test_ft3_low(self):
        parsed, _ = _load_fixture("tam_anh")
        v = _find(parsed, "ft3")
        assert v is not None
        # 2.8 pmol/L < ref_low=3.1
        assert classify_value("ft3", v.value) == LabStatus.LOW

    def test_glucose_normal(self):
        parsed, _ = _load_fixture("tam_anh")
        v = _find(parsed, "fasting_glucose")
        assert v is not None
        # 5.1 × 18.018 = 91.8918 → normal (70–99)
        assert classify_value("fasting_glucose", v.value) == LabStatus.NORMAL

    def test_all_tam_anh_biomarkers_extracted(self):
        parsed, exp = _load_fixture("tam_anh")
        found = {v.test_name for v in parsed}
        for canonical in exp["expected_biomarkers"]:
            assert canonical in found, f"{canonical} missing from tam_anh parse"


# ---------------------------------------------------------------------------
# Generic — conventional mg/dL input, all-normal panel
# ---------------------------------------------------------------------------


class TestGenericNoHospital:
    """Generic report with no hospital header: mg/dL values must pass through unchanged."""

    def test_glucose_unchanged_in_mg_dl(self):
        parsed, _ = _load_fixture("generic")
        v = _find(parsed, "fasting_glucose")
        assert v is not None
        assert v.unit == "mg/dL"
        # No SI conversion: 92 mg/dL must stay 92.0
        assert abs(v.value - 92.0) < 0.01

    def test_cholesterol_unchanged(self):
        parsed, _ = _load_fixture("generic")
        v = _find(parsed, "total_cholesterol")
        assert v is not None
        assert abs(v.value - 185.0) < 0.01

    def test_triglyceride_unchanged(self):
        parsed, _ = _load_fixture("generic")
        v = _find(parsed, "triglyceride")
        assert v is not None
        assert abs(v.value - 140.0) < 0.01

    def test_hdl_unchanged(self):
        parsed, _ = _load_fixture("generic")
        v = _find(parsed, "hdl")
        assert v is not None
        assert abs(v.value - 52.0) < 0.01

    def test_ldl_unchanged(self):
        parsed, _ = _load_fixture("generic")
        v = _find(parsed, "ldl")
        assert v is not None
        assert abs(v.value - 96.0) < 0.01

    def test_all_generic_biomarkers_extracted(self):
        parsed, exp = _load_fixture("generic")
        found = {v.test_name for v in parsed}
        for canonical in exp["expected_biomarkers"]:
            assert canonical in found, f"{canonical} missing from generic parse"

    def test_all_values_normal(self):
        """Every parsed value in the all-normal fixture must classify as NORMAL."""
        parsed, _ = _load_fixture("generic")
        for v in parsed:
            status = classify_value(v.test_name, v.value)
            assert status in (LabStatus.NORMAL, LabStatus.UNKNOWN), (
                f"{v.test_name}={v.value} classified as {status}, expected NORMAL"
            )


# ---------------------------------------------------------------------------
# Physiological plausibility — values outside absolute bounds
# ---------------------------------------------------------------------------


class TestPhysiologicalPlausibility:
    """Values outside biomarker physiological bounds must get ocr_confidence=0.0.

    NOTE: the parser NUMBER regex matches at most 3 contiguous digits before a
    separator, so four-digit integers (e.g. 9000) are truncated. Tests use decimal
    notation (e.g. 250.0) to reliably exceed bounds without truncation.
    """

    def test_hdl_above_physiological_max_zero_confidence(self):
        # physiological_max=200 mg/dL; 250.0 > 200 → confidence must be 0.0
        values = lab_parser.parse_lab_text("HDL-C 250.0 mg/dL")
        assert values, "Parser returned nothing for implausible HDL input"
        assert values[0].ocr_confidence == 0.0, (
            f"Expected ocr_confidence=0.0 for HDL 250.0, got {values[0].ocr_confidence}"
        )

    def test_hba1c_above_physiological_max_zero_confidence(self):
        # physiological_max=20 %; 25.0 > 20 → confidence must be 0.0
        values = lab_parser.parse_lab_text("HbA1c 25.0 %")
        assert values, "Parser returned nothing for implausible HbA1c input"
        assert values[0].ocr_confidence == 0.0, (
            f"Expected ocr_confidence=0.0 for HbA1c 25.0, got {values[0].ocr_confidence}"
        )

    def test_tsh_above_physiological_max_zero_confidence(self):
        # physiological_max=500 mIU/L; 600.0 > 500 → confidence must be 0.0
        values = lab_parser.parse_lab_text("TSH 600.0 mIU/L")
        assert values, "Parser returned nothing for implausible TSH input"
        assert values[0].ocr_confidence == 0.0, (
            f"Expected ocr_confidence=0.0 for TSH 600.0, got {values[0].ocr_confidence}"
        )

    def test_normal_glucose_passes_plausibility(self):
        # 95 mg/dL is within [20, 1500] → confidence must be > 0
        values = lab_parser.parse_lab_text("GLUCOSE 95 mg/dL")
        assert values, "Parser returned nothing for normal glucose"
        assert values[0].ocr_confidence > 0.0, (
            f"Normal glucose 95 should not be flagged, got confidence={values[0].ocr_confidence}"
        )

    def test_normal_hdl_passes_plausibility(self):
        values = lab_parser.parse_lab_text("HDL-C 55 mg/dL")
        assert values
        assert values[0].ocr_confidence > 0.0

    def test_normal_hba1c_passes_plausibility(self):
        values = lab_parser.parse_lab_text("HbA1c 5.8 %")
        assert values
        assert values[0].ocr_confidence > 0.0
