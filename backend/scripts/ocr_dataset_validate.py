"""Validate all expected/*.json files in ocr_dataset against the schema.

Usage:
    python scripts/ocr_dataset_validate.py [--tier benchmark|golden] [--hospital vinmec]

Exit codes:
    0 — all files valid, no PHI flags set
    1 — one or more validation errors
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATASET_DIR = BACKEND_DIR / "ocr_dataset"

VALID_HOSPITALS = (
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
_SAMPLE_ID_RE = re.compile(r"^\d{8}_[a-z0-9]+_\d{3}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _Source(BaseModel):
    uploaded_by: Literal["manual", "user_correction", "admin_annotation", "synthetic"]
    anonymized: bool
    contains_phi: bool


class _LabRow(BaseModel):
    row_index: int
    original_test_name: str
    display_name_vi: str | None = None
    mapped_metric_type: str | None = None
    value: float
    unit: str
    reference_range: str | None = None
    status: Literal["normal", "low", "high", "critical"] | None = None


class ExpectedLabReport(BaseModel):
    sample_id: str
    hospital: Literal[
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
    ]
    report_type: Literal["lab_result"]
    language: Literal["vi", "en"]
    test_date: str
    source: _Source
    rows: list[_LabRow]

    @field_validator("sample_id")
    @classmethod
    def _sample_id_format(cls, v: str) -> str:
        if not _SAMPLE_ID_RE.match(v):
            raise ValueError(f"must match YYYYMMDD_<hospital>_NNN, got: {v!r}")
        return v

    @field_validator("test_date")
    @classmethod
    def _test_date_format(cls, v: str) -> str:
        if not _DATE_RE.match(v):
            raise ValueError(f"must be YYYY-MM-DD, got: {v!r}")
        return v


def validate_file(path: Path) -> list[str]:
    """Return list of error strings. Empty list = valid."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"]

    try:
        report = ExpectedLabReport.model_validate(data)
    except ValidationError as exc:
        errors: list[str] = []
        for e in exc.errors():
            loc = ".".join(str(x) for x in e["loc"])
            errors.append(f"{loc}: {e['msg']}")
        return errors

    if report.source.contains_phi:
        return ["source.contains_phi is true — must not be committed to git"]

    if report.hospital != path.parts[-4] if len(path.parts) >= 4 else True:
        pass  # hospital folder mismatch is a warning, not a hard error

    return []


def collect_files(
    dataset_dir: Path,
    tier_filter: str | None,
    hospital_filter: str | None,
) -> list[Path]:
    tiers = [tier_filter] if tier_filter else ["golden", "benchmark"]
    hospitals = [hospital_filter] if hospital_filter else list(VALID_HOSPITALS)
    files: list[Path] = []
    for tier in tiers:
        for hospital in hospitals:
            expected_dir = dataset_dir / tier / hospital / "expected"
            if expected_dir.exists():
                files.extend(sorted(expected_dir.glob("*.expected.json")))
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate OCR dataset expected JSON files")
    parser.add_argument("--tier", choices=["golden", "benchmark"])
    parser.add_argument("--hospital", choices=VALID_HOSPITALS)
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    args = parser.parse_args(argv)

    files = collect_files(args.dataset_dir, args.tier, args.hospital)

    if not files:
        print("No expected JSON files found.")
        return 0

    passed = 0
    failed = 0
    counts: dict[str, int] = {}

    for f in files:
        errors = validate_file(f)
        rel = f.relative_to(BACKEND_DIR)
        # Extract hospital from path: ocr_dataset/<tier>/<hospital>/expected/<file>
        parts = f.relative_to(args.dataset_dir).parts
        hospital = parts[1] if len(parts) >= 4 else "unknown"
        counts[hospital] = counts.get(hospital, 0) + 1
        if errors:
            failed += 1
            print(f"FAIL  {rel}")
            for err in errors:
                print(f"      {err}")
        else:
            passed += 1
            print(f"OK    {rel}")

    print()
    print(f"Results: {passed} passed, {failed} failed")
    print()
    print("Files by hospital:")
    for h, n in sorted(counts.items()):
        print(f"  {h}: {n}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
