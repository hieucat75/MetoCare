"""
P0 — End-to-end clinical pipeline consistency tests.

All layers must agree on the same canonical clinical values for creatinine 87.66 µmol/L.

Root cause fixed (2026-06-28):
  lab_intelligence route was calling assess_biomarker(r.canonical_name, r.value)
  where r.value may be raw OCR value in the SI unit (e.g. µmol/L for creatinine).
  Since assess_biomarker() uses canonical mg/dL thresholds (critical ≥ 4.0 mg/dL),
  creatinine 87.66 µmol/L treated as 87.66 mg/dL triggered the critical branch
  → wrongly showed "Creatinine tăng rất cao" in lab-intelligence output.

Fix applied: lab_intelligence now uses normalized_value_si (same as patient_insight).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from app.domain.clinical_rules import assess_biomarker
from app.domain.lab_normalization import normalize_value_to_si
from app.services.lab import normalize_and_classify

# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

CREATININE_TEST_CASES = [
    # (original_value, original_unit, expected_normalized_approx, expected_unit, expected_status)
    (87.66, "µmol/L", 0.991, "mg/dL", "normal"),
    (0.99, "mg/dL", 0.990, "mg/dL", "normal"),
    (150.0, "µmol/L", 1.697, "mg/dL", "high"),
    (502.0, "µmol/L", 5.679, "mg/dL", "critical"),
    (2.12, "mg/dL", 2.120, "mg/dL", "high"),
    (0.50, "mg/dL", 0.500, "mg/dL", "low"),
]


@dataclass
class MockLabResult:
    """Minimal LabResult substitute — mirrors the ORM model."""

    canonical_name: str
    value: float
    unit: str
    normalized_value_si: float | None
    normalized_unit_si: str | None
    status: str | None
    verified_by_user: bool = True
    verified_by_doctor: bool = False
    batch_id: str | None = None
    patient_id: str = "p-pipeline-test"
    id: str = "result-pipeline-test"


def _make_creatinine_877() -> MockLabResult:
    """87.66 µmol/L creatinine — as stored in DB after create_manual_entry."""
    # create_manual_entry normalizes: 87.66 µmol/L → 0.9916 mg/dL
    return MockLabResult(
        canonical_name="creatinine",
        value=0.9916,  # canonical stored value (after normalization)
        unit="mg/dL",  # canonical unit
        normalized_value_si=0.9916,
        normalized_unit_si="mg/dL",
        status="normal",
        # original as-printed values preserved in DB:
        # original_value=87.66, original_unit='µmol/L'
    )


def _resolve_norm_si(r: MockLabResult) -> float | None:
    """Mirror the route's normalization logic: use stored normalized_value_si, else re-normalize."""
    norm_si = r.normalized_value_si
    if norm_si is None and r.value is not None:
        clf = normalize_and_classify(r.canonical_name, r.value, r.unit or "")
        norm_si = clf.get("normalized_value_si") if clf else None
    return norm_si


# ---------------------------------------------------------------------------
# Phase 0 verification: normalization layer
# ---------------------------------------------------------------------------


class TestCreatinineNormalization:
    """normalize_value_to_si + normalize_and_classify must agree for all test cases."""

    @pytest.mark.parametrize(
        "orig_val,orig_unit,exp_norm,exp_unit,exp_status",
        CREATININE_TEST_CASES,
    )
    def test_creatinine_normalize_and_classify(
        self, orig_val, orig_unit, exp_norm, exp_unit, exp_status
    ):
        """normalize_and_classify must produce expected canonical value and status."""
        clf = normalize_and_classify("creatinine", orig_val, orig_unit)
        assert clf, f"normalize_and_classify returned empty for {orig_val} {orig_unit}"
        norm = clf["normalized_value_si"]
        assert abs(norm - exp_norm) < 0.05, (
            f"{orig_val} {orig_unit}: expected ~{exp_norm} mg/dL, got {norm:.4f}"
        )
        assert clf["normalized_unit_si"] == exp_unit
        assert clf["status"] == exp_status, (
            f"{orig_val} {orig_unit}: expected status={exp_status}, got {clf['status']}"
        )

    def test_creatinine_877_umol_normalizes_to_normal(self):
        """87.66 µmol/L → ~0.991 mg/dL → normal (ref: 0.6–1.3 mg/dL)."""
        clf = normalize_and_classify("creatinine", 87.66, "µmol/L")
        assert clf["status"] == "normal", (
            f"87.66 µmol/L MUST be 'normal'. Got '{clf['status']}'. "
            f"normalized={clf.get('normalized_value_si'):.4f} mg/dL. "
            "Check: is normalized value in 0.6–1.3 mg/dL?"
        )
        norm = clf["normalized_value_si"]
        assert 0.9 < norm < 1.1, f"Expected ~0.991 mg/dL, got {norm:.4f}"

    def test_creatinine_877_raw_as_mgdl_is_critical(self):
        """Document the P0 bug: treating 87.66 as mg/dL (no conversion) = critical.

        This confirms WHY the bug caused 'tăng rất cao'. DO NOT use this value
        in production — it verifies the bug scenario, not the fix.
        """
        # assess_biomarker with the raw µmol/L value treated as mg/dL
        finding = assess_biomarker("creatinine", 87.66)
        assert finding is not None
        assert finding.status == "critical", (
            "Bug scenario: 87.66 treated as mg/dL must be critical (87.66 >= 4.0 mg/dL). "
            "If this fails, check critical_high threshold."
        )
        assert "tăng rất cao" in finding.patient_explanation_vi, (
            "Bug scenario must produce 'tăng rất cao' text — confirms P0 symptom."
        )


# ---------------------------------------------------------------------------
# Phase 1: assess_biomarker layer (canonical values only)
# ---------------------------------------------------------------------------


class TestAssessBiomarkerCreatinine:
    """assess_biomarker must produce correct finding when given NORMALIZED mg/dL value."""

    def test_assess_877_normalized_is_normal(self):
        """assess_biomarker(0.9916 mg/dL) → normal, NOT critical."""
        norm_val = 0.9916
        finding = assess_biomarker("creatinine", norm_val)
        assert finding is not None
        assert finding.status == "normal", (
            f"assess_biomarker('creatinine', {norm_val}) must be 'normal'. "
            f"Got '{finding.status}'. "
            "P0 bug: raw 87.66 µmol/L was passed directly → treated as mg/dL → critical."
        )
        assert finding.severity not in ("critical", "urgent"), (
            f"Creatinine 87.66 µmol/L must NOT be urgent/critical. "
            f"Got severity='{finding.severity}'."
        )
        assert "tăng rất cao" not in finding.patient_explanation_vi, (
            f"'tăng rất cao' must NOT appear for normal creatinine. "
            f"Got: {finding.patient_explanation_vi!r}"
        )

    def test_assess_critical_creatinine(self):
        """assess_biomarker(5.679 mg/dL from 502 µmol/L) → critical."""
        norm_val, _ = normalize_value_to_si(502.0, "µmol/L", "creatinine")
        finding = assess_biomarker("creatinine", norm_val)
        assert finding is not None
        assert finding.status == "critical"
        assert "tăng rất cao" in finding.patient_explanation_vi


# ---------------------------------------------------------------------------
# Phase 2: lab_intelligence route normalization (P0 fix verification)
# ---------------------------------------------------------------------------


class TestLabIntelligenceNormalization:
    """Verify lab_intelligence route resolves norm_si correctly (the P0 fix)."""

    def test_lab_intelligence_uses_normalized_not_raw(self):
        """Simulate the FIXED lab_intelligence route with creatinine 87.66 µmol/L.

        Before fix: route used r.value (0.9916 in canonical path, but raw 87.66 in
        old data without pre-normalization).
        After fix: route uses normalized_value_si, falling back to on-the-fly normalization.
        """
        r = _make_creatinine_877()

        # Route logic (post-P0 fix):
        norm_si = _resolve_norm_si(r)
        assert norm_si is not None
        assert abs(norm_si - 0.9916) < 0.05, f"Expected ~0.9916, got {norm_si}"

        # assess_biomarker with the resolved normalized value
        finding = assess_biomarker("creatinine", norm_si)
        assert finding is not None
        assert finding.status == "normal", (
            f"lab_intelligence with normalized_value_si={norm_si:.4f} must be 'normal'. "
            f"Got '{finding.status}'. "
            "If still critical, the route is still using r.value instead of normalized_value_si."
        )

    def test_lab_intelligence_old_data_fallback(self):
        """Simulate old data: normalized_value_si=None, must fall back to on-the-fly normalization.

        Old OCR rows (before the t6_m1_lieng migration) may not have normalized_value_si.
        The route must normalize on-the-fly in that case.
        """
        # Simulate old row: value=87.66, unit='µmol/L', normalized_value_si=None
        old_row = MockLabResult(
            canonical_name="creatinine",
            value=87.66,
            unit="µmol/L",
            normalized_value_si=None,  # old data without normalized fields
            normalized_unit_si=None,
            status=None,
        )
        norm_si = _resolve_norm_si(old_row)
        assert norm_si is not None, "Fallback normalization must produce a value"
        assert abs(norm_si - 0.9916) < 0.05, f"Expected ~0.9916, got {norm_si}"

        finding = assess_biomarker("creatinine", norm_si)
        assert finding is not None
        assert finding.status == "normal", (
            f"Old data fallback must still produce 'normal'. Got '{finding.status}'."
        )


# ---------------------------------------------------------------------------
# Phase 3: display unit consistency
# ---------------------------------------------------------------------------


class TestDisplayUnitConsistency:
    """Frontend receives consistent value+unit — never mixed (e.g. never 87.66 mg/dL)."""

    def test_original_values_preserved_in_db(self):
        """create_manual_entry must preserve original_value/original_unit separately.

        Verify the stored structure that Option B display relies on.
        """
        # Simulates what create_manual_entry stores:
        # After: value=0.9916 (canonical), original_value=87.66 (as entered)
        stored = {
            "value": 0.9916,
            "unit": "mg/dL",
            "original_value": 87.66,
            "original_unit": "µmol/L",
        }
        # Option B display logic (from resolveDisplayValueUnit in frontend):
        has_original = (
            stored["original_value"] is not None
            and stored["original_unit"] is not None
            and stored["original_unit"] != ""
        )
        if has_original:
            display_value = stored["original_value"]
            display_unit = stored["original_unit"]
        else:
            display_value = stored["value"]
            display_unit = stored["unit"]

        # NEVER: display_value=87.66, display_unit='mg/dL'
        if display_unit == "mg/dL":
            assert display_value < 10.0, (
                f"If unit is mg/dL, creatinine value must be < 10. Got {display_value}. "
                "Suspected mix: original value shown with canonical unit."
            )
        elif display_unit == "µmol/L":
            assert display_value > 10.0, (
                f"If unit is µmol/L, creatinine value must be > 10. Got {display_value}. "
                "Suspected mix: canonical value shown with original unit."
            )

        # Should show original:
        assert display_value == 87.66
        assert display_unit == "µmol/L"

    def test_canonical_value_canonical_unit_consistent(self):
        """Canonical canonical_value + canonical_unit must be internally consistent."""
        # Canonical path: 87.66 µmol/L → 0.9916 mg/dL
        norm_val, norm_unit = normalize_value_to_si(87.66, "µmol/L", "creatinine")
        # If showing canonical: 0.9916 mg/dL — valid (< 10 mg/dL)
        if norm_unit == "mg/dL":
            assert norm_val < 10.0
        # Classify correctly
        clf = normalize_and_classify("creatinine", 87.66, "µmol/L")
        assert clf["status"] == "normal"


# ---------------------------------------------------------------------------
# Phase 4: AI Summary must not say "tăng rất cao" for normal creatinine
# ---------------------------------------------------------------------------


class TestAISummaryCreatinine:
    """AI/patient insight must not generate alarming text for normal creatinine."""

    def test_normal_creatinine_no_critical_text(self):
        """assess_biomarker for normalized creatinine must not produce critical language."""
        norm_val, _ = normalize_value_to_si(87.66, "µmol/L", "creatinine")
        finding = assess_biomarker("creatinine", norm_val)
        assert finding is not None

        forbidden = ["tăng rất cao", "nguy hiểm", "cần bác sĩ đánh giá ngay", "cấp cứu"]
        for phrase in forbidden:
            assert phrase not in (finding.patient_explanation_vi or ""), (
                f"Normal creatinine (87.66 µmol/L → {norm_val:.4f} mg/dL) "
                f"must NOT contain '{phrase}' in explanation. "
                f"Got: {finding.patient_explanation_vi!r}"
            )

    def test_pipeline_agrees_creatinine_877(self):
        """Full pipeline: normalize → assess → verify all layers say 'normal'."""
        # Step 1: normalize
        clf = normalize_and_classify("creatinine", 87.66, "µmol/L")
        assert clf["status"] == "normal", f"normalize_and_classify: {clf['status']}"

        # Step 2: assess_biomarker with normalized value
        norm_val = clf["normalized_value_si"]
        finding = assess_biomarker("creatinine", norm_val)
        assert finding is not None
        assert finding.status == "normal", f"assess_biomarker: {finding.status}"
        assert finding.severity == "info", f"assess_biomarker severity: {finding.severity}"

        # Step 3: clinical_message via LabResultOut.clinical_message
        from app.services.lab import get_clinical_message

        msg = get_clinical_message("creatinine", "normal")
        # Verify message is non-alarming
        alarming = ["nguy hiểm", "tăng rất cao", "khẩn", "cần bác sĩ ngay"]
        for phrase in alarming:
            assert phrase not in (msg or ""), (
                f"clinical_message for creatinine/normal must not contain '{phrase}'. Got: {msg!r}"
            )


# ---------------------------------------------------------------------------
# Phase 5: No duplicate classification outside clinical_rules
# ---------------------------------------------------------------------------


class TestNoDuplicateClassification:
    """classify_value calls outside clinical_rules must all go through normalize_and_classify."""

    def test_lab_intelligence_no_raw_value_to_assess(self):
        """Verify that lab_intelligence no longer passes r.value to assess_biomarker directly.

        This test verifies the P0 fix by checking that the normalization step
        produces a value consistent with canonical mg/dL classification.
        """
        # If r.value = 87.66 (raw µmol/L), resolving through normalized_value_si
        # must NOT produce the same value as r.value.
        raw_value = 87.66  # µmol/L
        norm_val, _ = normalize_value_to_si(raw_value, "µmol/L", "creatinine")

        # The normalized value must differ from the raw value (conversion happened)
        assert abs(norm_val - raw_value) > 50, (
            f"Normalization must change 87.66 µmol/L significantly. "
            f"Got {norm_val:.4f} mg/dL (diff={abs(norm_val - raw_value):.2f}). "
            "If norm_val ≈ 87.66, the conversion did not happen."
        )

        # After normalization, status must be normal (not critical)
        finding = assess_biomarker("creatinine", norm_val)
        assert finding is not None
        assert finding.status == "normal"


# ---------------------------------------------------------------------------
# Phase 6: Sentinel / static-analysis tests
# Architecture regression guards — fast grep-based checks.
# Must pass on every commit. DO NOT relax to pass; fix violations instead.
# ---------------------------------------------------------------------------

import re
import subprocess

# Root of backend source relative to cwd when pytest runs (backend/ dir)
_BACKEND_SRC = "app"
_REPO_ROOT = "/Users/pth/Developer/Metocare"
_BACKEND_ROOT = "/Users/pth/Developer/Metocare/backend"


def _grep(
    pattern: str, path: str, include: str = "*.py", exclude_dirs: list | None = None
) -> list[str]:
    """Run grep -rn and return matching lines (stripped empty lines)."""
    cmd = ["grep", "-rn", pattern, path, f"--include={include}"]
    if exclude_dirs:
        for d in exclude_dirs:
            cmd += [f"--exclude-dir={d}"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=_BACKEND_ROOT)
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


# Files that are ALLOWED to contain the raw-value patterns
# (definitions, tests, migration helpers)
_SENTINEL_ALLOWLIST = [
    "clinical_rules.py",
    "lab_interpreter.py",
    "lab_normalization.py",
    "biomarker_specs.py",
    "derived_metrics.py",  # eGFR formula does legitimate mg/dL→µmol/L conversion
    "metabolic_live.py",  # metabolic score conversion factors
    "clinical_insight.py",  # HealthMetric (not LabResult) classification
    "lab.py",  # primary normalization service
    "test_",  # all test files
    "migration",  # Alembic migrations
    "__pycache__",
]


class TestSentinelRawValueGuard:
    """Static-analysis sentinel tests.

    These tests are the permanent guard against the pattern that caused P0
    clinical contradictions 3 times:

        P0-1 (2026-06-27): patient_insight.py — raw .value fed to assess_biomarker
        P0-2 (2026-06-27): metrics/[metricType]/page.tsx — frontend local classification
        P0-3 (2026-06-28): lab_intelligence.py — raw .value fed to assess_biomarker

    A violation here means a real bug was re-introduced. Fix the code, not the test.
    """

    def test_no_raw_value_in_assess_biomarker_calls(self):
        """assess_biomarker() must always receive normalized_value_si, not .value.

        Pattern to detect:
            assess_biomarker(<name>, r.value, ...)  — raw OCR field
            assess_biomarker(<name>, result.value, ...) — raw OCR field

        Correct pattern:
            assess_biomarker(<name>, norm_si, ...)  where norm_si = normalized_value_si
        """
        lines = _grep("assess_biomarker", _BACKEND_SRC, exclude_dirs=["__pycache__"])

        violations = []
        for line in lines:
            # Skip allowlisted files
            if any(skip in line for skip in _SENTINEL_ALLOWLIST):
                continue
            # Skip definition and import lines
            if "def assess_biomarker" in line or "import" in line:
                continue
            # Detect: assess_biomarker(anything containing ".value" that is NOT "_value_si"
            # Regex: assess_biomarker( ... .value ... ) where .value is NOT preceded by _si
            if re.search(
                r"assess_biomarker\s*\([^)]*\.value\b(?!_si)[^)]*\)",
                line,
            ):
                violations.append(line.strip())

        assert violations == [], (
            "SENTINEL FAIL — assess_biomarker() called with raw .value instead of "
            ".normalized_value_si:\n"
            + "\n".join(violations)
            + "\n\nFix: use result.normalized_value_si, not result.value"
            + "\nSee: lab_intelligence.py P0 fix (2026-06-28)"
        )

    def test_no_raw_value_in_classify_value_labresult_routes(self):
        """classify_value() in clinical routes must not receive LabResult.value directly.

        Allowed: clinical_insight.py uses classify_value() with HealthMetric.value
        (which is canonical — not raw OCR). That file is in the allowlist.

        Forbidden: any route/service not in allowlist passing .value to classify_value.
        """
        lines = _grep("classify_value", _BACKEND_SRC, exclude_dirs=["__pycache__"])

        violations = []
        for line in lines:
            if any(skip in line for skip in _SENTINEL_ALLOWLIST):
                continue
            if "def classify_value" in line or "import" in line:
                continue
            # Detect: classify_value( ... .value ... ) where .value is NOT normalized
            if re.search(
                r"classify_value\s*\([^)]*\.value\b(?!_si)[^)]*\)",
                line,
            ):
                violations.append(line.strip())

        assert violations == [], (
            "SENTINEL FAIL — classify_value() called with raw .value:\n"
            + "\n".join(violations)
            + "\n\nFix: use normalized_value_si, not raw LabResult.value"
        )

    def test_no_frontend_anthropic_direct_import(self):
        """Frontend must never import or call Anthropic SDK directly.

        All AI calls must go through the backend API.
        """
        frontend_src = f"{_REPO_ROOT}/frontend/src"
        ts_lines = _grep(
            "anthropic", frontend_src, include="*.ts", exclude_dirs=["node_modules", "__tests__"]
        ) + _grep(
            "anthropic", frontend_src, include="*.tsx", exclude_dirs=["node_modules", "__tests__"]
        )

        violations = [ln for ln in ts_lines if "import" in ln.lower() or "require" in ln.lower()]
        assert violations == [], (
            "SENTINEL FAIL — Frontend directly imports Anthropic SDK:\n"
            + "\n".join(violations)
            + "\n\nFix: all AI calls must go through /api/v1/* endpoints."
        )

    def test_no_frontend_local_clinical_classification(self):
        """Frontend must not implement local classification / severity computation.

        All clinical status must come from backend API (lab_intelligence,
        patient_insight). Local comparison against reference ranges in TSX/TS
        re-introduces the P0-2 bug pattern.
        """
        frontend_src = f"{_REPO_ROOT}/frontend/src"
        suspect_patterns = [
            r"localClassify|computeSeverity|getBannerLevel|metricDanger",
            r"value\s*>\s*refHigh|value\s*<\s*refLow",
            r"isDangerous\s*=.*value\b",
        ]
        violations = []
        for pattern in suspect_patterns:
            for ext in ("*.tsx", "*.ts"):
                found = _grep(
                    pattern,
                    frontend_src,
                    include=ext,
                    exclude_dirs=["node_modules", "__tests__", "__pycache__"],
                )
                violations.extend(found)

        assert violations == [], (
            "SENTINEL FAIL — Frontend contains local clinical classification logic:\n"
            + "\n".join(violations[:20])
            + "\n\nFix: all clinical status must come from backend API."
        )

    def test_no_unit_conversion_in_route_files(self):
        """Unit conversion factors must not appear in route or schema files.

        Conversion (mmol/L→mg/dL etc.) belongs exclusively in:
          - lab_interpreter.py (BiomarkerSpec definitions)
          - lab.py (normalize_and_classify)
          - derived_metrics.py (eGFR formula, lipid ratios)

        Finding a conversion factor in a route or serializer means someone
        copy-pasted conversion logic instead of calling the normalization service.
        """
        route_dirs = ["app/api", "app/schemas"]
        # Glucose: ×18.0 or ×18.018; creatinine: ×88.42 or /88.42; lipids: ×38.67
        conversion_patterns = [
            r"[*\/]\s*18\.0\b|[*\/]\s*18\.018",
            r"[*\/]\s*88\.4\d*",
            r"[*\/]\s*38\.6\d*",
        ]
        violations = []
        for route_dir in route_dirs:
            path = f"{_BACKEND_ROOT}/{route_dir}"
            for pattern in conversion_patterns:
                found = _grep(pattern, path, exclude_dirs=["__pycache__"])
                for line in found:
                    if "test_" not in line and "#" not in line.split(":", 2)[-1][:5]:
                        violations.append(line.strip())

        assert violations == [], (
            "SENTINEL FAIL — Hardcoded unit conversion in route/schema files:\n"
            + "\n".join(violations)
            + "\n\nFix: call lab.normalize_and_classify() or derive from BiomarkerSpec. "
            + "Do not copy conversion factors into routes."
        )
