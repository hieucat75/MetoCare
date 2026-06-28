"""Tests for OCR dataset structure, schema, and validation scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BACKEND_DIR / "ocr_dataset"
SCRIPTS_DIR = BACKEND_DIR / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
from ocr_dataset_validate import ExpectedLabReport, validate_file  # noqa: E402

HOSPITALS = (
    "vinmec",
    "medlatec",
    "tamanh",
    "hongngoc",
    "bachmai",
    "bachmai108",
    "fv",
    "hoanmy",
    "thucuc",
    "vietduc",
    "other",
)
TIERS = ("golden", "benchmark")
HOSPITAL_SUBDIRS = ("images", "expected", "azure_cache", "notes")
TOP_LEVEL_DIRS = ("incoming", "anonymized", "reports", "schema")

SYNTHETIC_SAMPLE = {
    "sample_id": "20261224_vinmec_001",
    "hospital": "vinmec",
    "report_type": "lab_result",
    "language": "vi",
    "test_date": "2024-12-24",
    "source": {
        "uploaded_by": "synthetic",
        "anonymized": True,
        "contains_phi": False,
    },
    "rows": [
        {
            "row_index": 1,
            "original_test_name": "Glucose",
            "display_name_vi": "Đường huyết",
            "mapped_metric_type": "fasting_glucose",
            "value": 4.78,
            "unit": "mmol/L",
            "reference_range": "4.11–6.05",
            "status": "normal",
        }
    ],
}


class TestDirectoryStructure:
    def test_top_level_dirs_exist(self):
        for d in TOP_LEVEL_DIRS:
            assert (DATASET_DIR / d).is_dir(), f"Missing: ocr_dataset/{d}/"

    @pytest.mark.parametrize("tier", TIERS)
    @pytest.mark.parametrize("hospital", HOSPITALS)
    def test_hospital_subdirs_exist(self, tier: str, hospital: str):
        for subdir in HOSPITAL_SUBDIRS:
            path = DATASET_DIR / tier / hospital / subdir
            assert path.is_dir(), f"Missing: ocr_dataset/{tier}/{hospital}/{subdir}/"

    def test_schema_file_exists(self):
        schema = DATASET_DIR / "schema" / "expected_lab_report.schema.json"
        assert schema.is_file(), "Missing schema/expected_lab_report.schema.json"

    def test_readme_exists(self):
        assert (DATASET_DIR / "README.md").is_file()

    def test_gitignore_exists(self):
        assert (DATASET_DIR / ".gitignore").is_file()


class TestGitignoreProtection:
    def _load_gitignore(self) -> str:
        return (DATASET_DIR / ".gitignore").read_text()

    def test_images_ignored(self):
        assert "images/*" in self._load_gitignore()

    def test_azure_cache_ignored(self):
        assert "azure_cache/*" in self._load_gitignore()

    def test_incoming_ignored(self):
        assert "incoming/*" in self._load_gitignore()

    def test_anonymized_ignored(self):
        assert "anonymized/*" in self._load_gitignore()

    def test_gitkeep_not_ignored(self):
        content = self._load_gitignore()
        assert "!images/.gitkeep" in content or ".gitkeep" in content


class TestSchemaValidation:
    def test_synthetic_sample_passes_pydantic(self):
        report = ExpectedLabReport.model_validate(SYNTHETIC_SAMPLE)
        assert report.sample_id == "20261224_vinmec_001"
        assert report.hospital == "vinmec"
        assert len(report.rows) == 1
        assert report.rows[0].value == pytest.approx(4.78)

    def test_committed_synthetic_example_is_valid(self):
        path = (
            DATASET_DIR / "benchmark" / "vinmec" / "expected" / "20261224_vinmec_001.expected.json"
        )
        assert path.exists(), "Synthetic example file missing"
        errors = validate_file(path)
        assert errors == [], f"Synthetic example failed validation: {errors}"

    def test_committed_example_has_no_phi(self):
        path = (
            DATASET_DIR / "benchmark" / "vinmec" / "expected" / "20261224_vinmec_001.expected.json"
        )
        data = json.loads(path.read_text())
        assert data["source"]["contains_phi"] is False

    def test_schema_json_is_parseable(self):
        schema_path = DATASET_DIR / "schema" / "expected_lab_report.schema.json"
        schema = json.loads(schema_path.read_text())
        assert schema["title"] == "ExpectedLabReport"
        assert "properties" in schema
        assert "rows" in schema["properties"]


class TestValidator:
    def test_valid_sample_returns_no_errors(self, tmp_path: Path):
        f = tmp_path / "test.expected.json"
        f.write_text(json.dumps(SYNTHETIC_SAMPLE), encoding="utf-8")
        assert validate_file(f) == []

    def test_phi_flag_true_returns_error(self, tmp_path: Path):
        sample = {
            **SYNTHETIC_SAMPLE,
            "source": {**SYNTHETIC_SAMPLE["source"], "contains_phi": True},
        }
        f = tmp_path / "phi.expected.json"
        f.write_text(json.dumps(sample), encoding="utf-8")
        errors = validate_file(f)
        assert any("contains_phi" in e for e in errors)

    def test_missing_required_field_returns_error(self, tmp_path: Path):
        sample = {k: v for k, v in SYNTHETIC_SAMPLE.items() if k != "test_date"}
        f = tmp_path / "missing.expected.json"
        f.write_text(json.dumps(sample), encoding="utf-8")
        errors = validate_file(f)
        assert errors, "Expected validation error for missing test_date"

    def test_invalid_sample_id_format_returns_error(self, tmp_path: Path):
        sample = {**SYNTHETIC_SAMPLE, "sample_id": "bad-format"}
        f = tmp_path / "bad_id.expected.json"
        f.write_text(json.dumps(sample), encoding="utf-8")
        errors = validate_file(f)
        assert any("sample_id" in e for e in errors)

    def test_invalid_test_date_format_returns_error(self, tmp_path: Path):
        sample = {**SYNTHETIC_SAMPLE, "test_date": "24/12/2024"}
        f = tmp_path / "bad_date.expected.json"
        f.write_text(json.dumps(sample), encoding="utf-8")
        errors = validate_file(f)
        assert any("test_date" in e for e in errors)

    def test_unknown_hospital_returns_error(self, tmp_path: Path):
        sample = {**SYNTHETIC_SAMPLE, "hospital": "unknown_hospital"}
        f = tmp_path / "bad_hosp.expected.json"
        f.write_text(json.dumps(sample), encoding="utf-8")
        errors = validate_file(f)
        assert errors, "Expected validation error for unknown hospital"

    def test_invalid_json_returns_error(self, tmp_path: Path):
        f = tmp_path / "bad.expected.json"
        f.write_text("{not valid json", encoding="utf-8")
        errors = validate_file(f)
        assert any("JSON" in e for e in errors)

    def test_value_must_be_number(self, tmp_path: Path):
        row = {**SYNTHETIC_SAMPLE["rows"][0], "value": "not-a-number"}
        sample = {**SYNTHETIC_SAMPLE, "rows": [row]}
        f = tmp_path / "bad_value.expected.json"
        f.write_text(json.dumps(sample), encoding="utf-8")
        errors = validate_file(f)
        assert errors, "Expected validation error for non-numeric value"
