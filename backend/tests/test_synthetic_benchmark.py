"""Tests for the synthetic benchmark mode added in Phase C.

These tests verify the synthetic benchmark logic works correctly without
requiring Azure DI credentials or real lab images.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Bootstrap sys.path so we can import from backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from scripts.benchmark_ocr import (  # noqa: E402
    _normalize_expected_canonical,
    _test_hospital_detection,
    run_synthetic_benchmark,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_BENCH_DIR = _BACKEND_DIR / "ocr_dataset" / "benchmark"


# ── 1. _normalize_expected_canonical ─────────────────────────────────────────

class TestNormalizeExpectedCanonical:
    """_normalize_expected_canonical() maps expected.json aliases to live canonical names."""

    def test_hdl_cholesterol_maps_to_hdl(self) -> None:
        assert _normalize_expected_canonical("hdl_cholesterol") == "hdl"

    def test_ldl_cholesterol_maps_to_ldl(self) -> None:
        assert _normalize_expected_canonical("ldl_cholesterol") == "ldl"

    def test_triglycerides_maps_to_triglyceride(self) -> None:
        assert _normalize_expected_canonical("triglycerides") == "triglyceride"

    def test_calcium_passthrough(self) -> None:
        # calcium added to BIOMARKERS in Phase C — now passes through as-is
        assert _normalize_expected_canonical("calcium") == "calcium"

    def test_passthrough_known_canonical(self) -> None:
        # Standard canonicals pass through unchanged
        assert _normalize_expected_canonical("fasting_glucose") == "fasting_glucose"
        assert _normalize_expected_canonical("hba1c") == "hba1c"
        assert _normalize_expected_canonical("creatinine") == "creatinine"
        assert _normalize_expected_canonical("urea") == "urea"

    def test_none_input_returns_none(self) -> None:
        assert _normalize_expected_canonical(None) is None


# ── 2. _test_hospital_detection ───────────────────────────────────────────────

class TestHospitalDetection:
    """_test_hospital_detection() returns True for every known hospital profile."""

    @pytest.mark.parametrize("hospital_id", [
        "vinmec",
        "medlatec",
        "tamanh",
        "hongngoc",
        "bachmai",
        "bachmai108",
        "fv",
    ])
    def test_known_hospitals_detected(self, hospital_id: str) -> None:
        ok, pattern = _test_hospital_detection(hospital_id)
        assert ok, (
            f"Hospital '{hospital_id}' was not detected via pattern '{pattern}'. "
            "Check that header_patterns or hospital_name_variants contain a valid "
            "string that HospitalDetector resolves correctly."
        )
        assert pattern, f"Hospital '{hospital_id}': detection pattern should be non-empty"

    def test_unknown_hospital_returns_false(self) -> None:
        ok, _ = _test_hospital_detection("totally_unknown_hospital_xyz")
        assert not ok


# ── 3. run_synthetic_benchmark (integration) ──────────────────────────────────

class TestRunSyntheticBenchmark:
    """Full integration test of run_synthetic_benchmark()."""

    def test_returns_true_for_benchmark_dir(self) -> None:
        """All current hospitals in ocr_dataset/benchmark should pass their UER target."""
        if not _BENCH_DIR.exists():
            pytest.skip(f"Benchmark directory not found: {_BENCH_DIR}")
        result = run_synthetic_benchmark(_BENCH_DIR)
        assert result is True, (
            "run_synthetic_benchmark() returned False; one or more hospitals exceeded UER target."
        )

    def test_hospital_filter_works(self) -> None:
        """--hospital filter restricts processing to a single hospital."""
        if not _BENCH_DIR.exists():
            pytest.skip(f"Benchmark directory not found: {_BENCH_DIR}")
        # vinmec always has expected data
        result = run_synthetic_benchmark(_BENCH_DIR, hospital_filter="vinmec")
        assert result is True

    def test_nonexistent_bench_dir_exits(self, tmp_path: Path) -> None:
        """A missing bench_dir should call sys.exit(1)."""
        missing = tmp_path / "does_not_exist"
        with pytest.raises(SystemExit) as exc_info:
            run_synthetic_benchmark(missing)
        assert exc_info.value.code == 1

    def test_synthetic_benchmark_with_synthetic_expected_json(self, tmp_path: Path) -> None:
        """run_synthetic_benchmark() works correctly on a hand-crafted expected.json."""
        # Create minimal directory structure
        hosp_dir = tmp_path / "vinmec" / "expected"
        hosp_dir.mkdir(parents=True)

        sample = {
            "sample_id": "test_vinmec_001",
            "hospital": "vinmec",
            "rows": [
                {
                    "row_index": 1,
                    "original_test_name": "Glucose",
                    "mapped_metric_type": "fasting_glucose",
                },
                {
                    "row_index": 2,
                    "original_test_name": "HbA1c",
                    "mapped_metric_type": "hba1c",
                },
                {
                    "row_index": 3,
                    "original_test_name": "Creatinine",
                    "mapped_metric_type": "creatinine",
                },
            ],
        }
        (hosp_dir / "test_vinmec_001.expected.json").write_text(
            json.dumps(sample), encoding="utf-8"
        )

        result = run_synthetic_benchmark(tmp_path, hospital_filter="vinmec")
        assert result is True


# ── 4. normalize_biomarker edge cases (used by synthetic mode) ────────────────

class TestNormalizeBiomarkerEdgeCases:
    """Spot-check normalize_biomarker() for names appearing in expected.json files."""

    @pytest.mark.parametrize("raw_name,expected_canonical", [
        # Vietnamese test names from tamanh
        ("Đường huyết lúc đói", "fasting_glucose"),  # Phase C fix: accented alias added
        ("Urê", "urea"),                                # Phase C fix: Urê alias added
        # tamanh SGOT/SGPT with leading keyword
        ("SGOT (AST)", "ast"),
        ("SGPT (ALT)", "alt"),
        # Vinmec parenthetical stripping
        ("AST (SGOT)", "ast"),
        ("ALT (SGPT)", "alt"),
        ("eGFR (CKD-EPI)", "egfr"),
        # Plain names
        ("Glucose", "fasting_glucose"),
        ("HbA1c", "hba1c"),
        ("Creatinine", "creatinine"),
        ("Triglycerid", "triglyceride"),
        ("Triglycerides", "triglyceride"),
        ("HDL-Cholesterol", "hdl"),
        ("LDL-Cholesterol", "ldl"),
        ("Acid Uric", "uric_acid"),
        ("TSH", "tsh"),
    ])
    def test_normalize(self, raw_name: str, expected_canonical: str | None) -> None:
        from app.domain.lab_interpreter import normalize_biomarker
        assert normalize_biomarker(raw_name) == expected_canonical
