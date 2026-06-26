#!/usr/bin/env python3
"""OCR accuracy benchmark — MetoCare.

Reads real lab report images from bench_data/, calls Azure DI (with result cache),
runs extract_and_map(), compares against ground_truth.json, then prints the report.

Directory layout
----------------
bench_data/
  vinmec/
    report_01/
      image.pdf          (or image.jpg / image.png)
      ground_truth.json
      _azure_result.json  <- auto-created on first run, reused afterwards
    report_02/
      ...
  medlatec/
    ...
  tamanh/
    ...
  hongngoc/
    ...

Ground truth format
-------------------
{
  "hospital_id": "vinmec",
  "test_date": "2024-10-15",
  "rows": [
    {"test_name": "Creatinine",   "value": 72.0,  "unit": "umol/L",  "reference_range": "44-97"},
    {"test_name": "Glucose",      "value": 5.2,   "unit": "mmol/L",  "reference_range": "3.9-6.1"},
    {"test_name": "HbA1c",        "value": 5.4,   "unit": "%",       "reference_range": "4.0-5.7"}
  ]
}

Usage
-----
  cd backend/
  python scripts/benchmark_ocr.py --bench-dir ./bench_data
  python scripts/benchmark_ocr.py --bench-dir ./bench_data --hospital vinmec
  python scripts/benchmark_ocr.py --bench-dir ./bench_data --no-cache   # re-call Azure DI
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

# Bootstrap sys.path so we can import app modules from backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed — run 'pip install httpx'", file=sys.stderr)
    sys.exit(1)

from app.domain.hospital_profiles import (  # noqa: E402
    HOSPITAL_PROFILES,
    HospitalDetector,
    detect_hospital,
)
from app.domain.lab_interpreter import normalize_biomarker  # noqa: E402
from app.domain.lab_table_extractor import extract_and_map  # noqa: E402

# Azure DI settings (from environment)
_AZ_API_VERSION = "2024-11-30"
_AZ_MODEL = os.environ.get("AZURE_DOC_INTEL_MODEL", "prebuilt-layout")
_AZ_ENDPOINT = os.environ.get("AZURE_DOC_INTEL_ENDPOINT", "").rstrip("/")
_AZ_KEY = os.environ.get("AZURE_DOC_INTEL_KEY", "")
_POLL_INTERVAL = 2.0
_POLL_TIMEOUT = 120.0


# ── Azure DI call ──────────────────────────────────────────────────────────────

def _call_azure_di(image_path: Path) -> dict:
    if not _AZ_ENDPOINT or not _AZ_KEY:
        raise RuntimeError(
            "Set AZURE_DOC_INTEL_ENDPOINT and AZURE_DOC_INTEL_KEY before running benchmark."
        )
    mime = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".tiff": "image/tiff", ".tif": "image/tiff",
    }.get(image_path.suffix.lower(), "application/octet-stream")

    analyze_url = (
        f"{_AZ_ENDPOINT}/documentintelligence/documentModels/"
        f"{_AZ_MODEL}:analyze?api-version={_AZ_API_VERSION}"
    )
    headers = {"Ocp-Apim-Subscription-Key": _AZ_KEY, "Content-Type": mime}

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(analyze_url, content=image_path.read_bytes(), headers=headers)
        resp.raise_for_status()
        op_url = resp.headers.get("operation-location") or resp.headers.get("Operation-Location")
        if not op_url:
            raise RuntimeError("No operation-location header in Azure DI response")

        deadline = time.monotonic() + _POLL_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(_POLL_INTERVAL)
            poll = client.get(op_url, headers={"Ocp-Apim-Subscription-Key": _AZ_KEY})
            poll.raise_for_status()
            data = poll.json()
            status = data.get("status", "")
            if status == "succeeded":
                return data.get("analyzeResult") or data
            if status in ("failed", "canceled"):
                raise RuntimeError(f"Azure DI job {status}: {data}")

    raise TimeoutError(f"Azure DI did not complete in {_POLL_TIMEOUT}s")


# ── Normalisation helpers ──────────────────────────────────────────────────────

def _strip_accents_lower(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )


def _norm_value(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _norm_unit(u: str | None) -> str:
    if not u:
        return ""
    return _strip_accents_lower(u).replace("µ", "u").replace("μ", "u").strip()


def _norm_ref(r: str | None) -> str:
    if not r:
        return ""
    s = _strip_accents_lower(r).replace("–", "-").replace("—", "-").replace("~", "-").replace(" ", "")  # noqa: E501
    return s


# ── Ground truth matching ──────────────────────────────────────────────────────

@dataclass
class FieldResult:
    correct: bool
    got: str
    expected: str


@dataclass
class RowResult:
    test_name_gt: str
    test_name_matched: bool
    value: FieldResult
    unit: FieldResult
    reference_range: FieldResult
    needs_edit: bool = field(init=False)

    def __post_init__(self) -> None:
        self.needs_edit = not (self.test_name_matched and self.value.correct and self.unit.correct)


@dataclass
class ReportResult:
    report_id: str
    hospital_id: str
    gt_row_count: int
    matched_rows: list[RowResult] = field(default_factory=list)
    missed_test_names: list[str] = field(default_factory=list)
    detected_hospital_id: str | None = None
    hospital_detected_correctly: bool = False

    @property
    def correct_rows(self) -> int:
        return sum(1 for r in self.matched_rows if not r.needs_edit)

    @property
    def rows_needing_edit(self) -> int:
        return sum(1 for r in self.matched_rows if r.needs_edit)

    @property
    def row_accuracy(self) -> float:
        return self.correct_rows / self.gt_row_count if self.gt_row_count else 0.0

    @property
    def editing_rate(self) -> float:
        return self.rows_needing_edit / self.gt_row_count if self.gt_row_count else 0.0


def _best_match(gt_name: str, extracted_names: list[str]) -> str | None:
    gt_norm = _strip_accents_lower(gt_name)
    for name in extracted_names:
        n = _strip_accents_lower(name)
        if n == gt_norm or n.startswith(gt_norm) or gt_norm.startswith(n):
            return name
    best, best_score = None, 0
    for name in extracted_names:
        n = _strip_accents_lower(name)
        overlap = len(set(gt_norm.split()) & set(n.split()))
        if overlap > best_score:
            best_score, best = overlap, name
    return best if best_score >= 1 else None


def _evaluate_report(report_id: str, gt: dict, azure_result: dict) -> ReportResult:
    hospital_id = gt.get("hospital_id", "unknown")

    full_text = azure_result.get("content", "")
    detected = detect_hospital(full_text)
    detected_id = detected.hospital_id if detected else "unknown"

    rr = ReportResult(
        report_id=report_id,
        hospital_id=hospital_id,
        gt_row_count=len(gt.get("rows", [])),
        detected_hospital_id=detected_id,
        hospital_detected_correctly=(detected_id == hospital_id),
    )

    extracted = extract_and_map(azure_result)
    by_name: dict[str, Any] = {(r.test_name or ""): r for r in extracted}

    for gt_row in gt.get("rows", []):
        gt_name = gt_row.get("test_name", "")
        gt_value = _norm_value(gt_row.get("value"))
        gt_unit = _norm_unit(gt_row.get("unit"))
        gt_ref = _norm_ref(gt_row.get("reference_range"))

        matched_key = _best_match(gt_name, list(by_name.keys()))
        if matched_key is None:
            rr.missed_test_names.append(gt_name)
            rr.matched_rows.append(RowResult(
                test_name_gt=gt_name,
                test_name_matched=False,
                value=FieldResult(False, "(not found)", str(gt_value)),
                unit=FieldResult(False, "(not found)", str(gt_row.get("unit", ""))),
                reference_range=FieldResult(False, "(not found)", str(gt_row.get("reference_range", ""))),  # noqa: E501
            ))
            continue

        ext = by_name[matched_key]
        ext_value = _norm_value(
            getattr(ext, "original_value", None) or getattr(ext, "value", None)
        )
        ext_unit = _norm_unit(getattr(ext, "original_unit", None))
        ext_ref = _norm_ref(getattr(ext, "reference_range", None))

        value_ok = (
            gt_value is not None
            and ext_value is not None
            and (
                math.isclose(gt_value, ext_value, rel_tol=0.01)
                if gt_value != 0 else abs(ext_value) < 0.001
            )
        )
        rr.matched_rows.append(RowResult(
            test_name_gt=gt_name,
            test_name_matched=True,
            value=FieldResult(value_ok, str(ext_value) if ext_value is not None else "(missing)", str(gt_value)),  # noqa: E501
            unit=FieldResult(gt_unit == ext_unit, ext_unit, gt_unit),
            reference_range=FieldResult(not gt_ref or gt_ref == ext_ref, ext_ref, gt_ref),
        ))

    return rr


# ── Report printer ─────────────────────────────────────────────────────────────

_EDITING_TARGETS: dict[str, float] = {
    "vinmec": 0.10,
    "medlatec": 0.15,
    "tamanh": 0.20,      # Phase B P1.1: renamed from tam_anh
    "hongngoc": 0.20,    # Phase B P1.1: renamed from hong_ngoc
    "bachmai": 0.20,     # Phase B P1.1: renamed from bach_mai
    "bachmai108": 0.20,  # Phase B P1.1: renamed from hospital_108
    "fv": 0.20,
    "hoanmy": 0.20,
    "thucuc": 0.20,
    "vietduc": 0.20,
}


def _print_hospital_report(hospital: str, reports: list[ReportResult]) -> None:
    total_rows = sum(r.gt_row_count for r in reports)
    total_correct = sum(r.correct_rows for r in reports)
    total_edit = sum(r.rows_needing_edit for r in reports)
    detect_ok = sum(1 for r in reports if r.hospital_detected_correctly)
    n = len(reports)

    accuracy = total_correct / total_rows if total_rows else 0.0
    editing_rate = total_edit / total_rows if total_rows else 0.0
    detect_rate = detect_ok / n if n else 0.0
    target = _EDITING_TARGETS.get(hospital.lower(), 0.20)
    edit_pass = editing_rate <= target

    print(f"\n{'='*60}")
    print(f"  {hospital.upper()}")
    print(f"{'='*60}")
    print(f"  Reports:              {n}")
    print(f"  Rows (ground truth):  {total_rows}")
    print(f"  Correct rows:         {total_correct}")
    print(f"  Accuracy:             {accuracy:.1%}")
    print(f"  Hospital detection:   {detect_rate:.1%}  ({detect_ok}/{n})")
    print()
    print(f"  User Editing Rate:    {editing_rate:.1%}  ({total_edit} rows need edit)")
    print(f"  Target: <{target:.0%}  ->  {'PASS' if edit_pass else 'FAIL'}")

    # Wrong rows
    wrongs: list[tuple[str, str, str]] = []
    for r in reports:
        if not r.hospital_detected_correctly:
            wrongs.append((r.report_id, "(hospital)", f"detected '{r.detected_hospital_id}'"))
        for row in r.matched_rows:
            if not row.test_name_matched:
                wrongs.append((r.report_id, row.test_name_gt, "not found in OCR output"))
            else:
                if not row.value.correct:
                    wrongs.append((r.report_id, row.test_name_gt,
                                   f"value: got {row.value.got!r}  expected {row.value.expected!r}"))  # noqa: E501
                if not row.unit.correct:
                    wrongs.append((r.report_id, row.test_name_gt,
                                   f"unit: got {row.unit.got!r}  expected {row.unit.expected!r}"))
                if not row.reference_range.correct:
                    wrongs.append((r.report_id, row.test_name_gt,
                                   f"ref: got {row.reference_range.got!r}  expected {row.reference_range.expected!r}"))  # noqa: E501

    if wrongs:
        print(f"\n  Wrong rows ({len(wrongs)}):")
        for rid, name, reason in wrongs:
            print(f"    {rid:<15}  {name:<30}  {reason}")
    else:
        print("\n  No wrong rows.")


def _print_summary(all_hospitals: dict[str, list[ReportResult]]) -> None:
    print(f"\n{'='*60}")
    print("  OVERALL SUMMARY")
    print(f"{'='*60}")

    totals = {"reports": 0, "rows": 0, "correct": 0, "edit": 0, "detected": 0}
    for hospital, reports in all_hospitals.items():
        tr = sum(r.gt_row_count for r in reports)
        tc = sum(r.correct_rows for r in reports)
        te = sum(r.rows_needing_edit for r in reports)
        td = sum(1 for r in reports if r.hospital_detected_correctly)
        n = len(reports)
        totals["reports"] += n
        totals["rows"] += tr
        totals["correct"] += tc
        totals["edit"] += te
        totals["detected"] += td
        acc = tc / tr if tr else 0.0
        edit = te / tr if tr else 0.0
        print(f"  {hospital:<15}  reports={n:>3}  rows={tr:>4}  accuracy={acc:.1%}  editing={edit:.1%}")  # noqa: E501

    print()
    ov_acc = totals["correct"] / totals["rows"] if totals["rows"] else 0.0
    ov_edit = totals["edit"] / totals["rows"] if totals["rows"] else 0.0
    ov_det = totals["detected"] / totals["reports"] if totals["reports"] else 0.0

    print(f"  Total reports:      {totals['reports']}")
    print(f"  Total rows:         {totals['rows']}")
    print(f"  Overall accuracy:   {ov_acc:.1%}")
    print(f"  Hospital detect:    {ov_det:.1%}")
    print(f"  Avg editing rate:   {ov_edit:.1%}")
    print()

    gates = [
        ("Hospital detect   >=99%", ov_det >= 0.99),
        ("Overall accuracy  >=85%", ov_acc >= 0.85),
        ("Avg editing rate  <15%", ov_edit <= 0.15),
    ]
    all_pass = all(ok for _, ok in gates)
    for label, ok in gates:
        print(f"  {'OK' if ok else 'XX'}  {label}")
    print()
    print(f"  => {'ALL GATES PASS' if all_pass else 'ACCEPTANCE GATES FAILED'}")


# ── Main ───────────────────────────────────────────────────────────────────────

def _find_image(report_dir: Path) -> Path | None:
    for ext in (".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"):
        for p in report_dir.glob(f"*{ext}"):
            if not p.name.startswith("_") and "ground" not in p.name:
                return p
    return None


# ── Synthetic benchmark ───────────────────────────────────────────────────────

# Canonical name aliases that appear in expected.json but differ slightly from
# what normalize_biomarker() returns.  Maps expected.json mapped_metric_type →
# canonical returned by normalize_biomarker().  This lets the synthetic mode
# compare correctly without requiring exact string equality on edge cases.
_CANONICAL_ALIASES: dict[str, str] = {
    # vinmec expected.json uses 'hdl_cholesterol' but normalizer returns 'hdl'
    "hdl_cholesterol": "hdl",
    "ldl_cholesterol": "ldl",
    # vinmec uses 'triglycerides' but normalizer returns 'triglyceride'
    "triglycerides": "triglyceride",
    # vinmec uses 'calcium' — added to BIOMARKERS in Phase C fix
    # No alias needed: normalize_biomarker('calcium') already returns 'calcium'
}


class _SynRowResult(NamedTuple):
    original_name: str
    expected_canonical: str | None
    got_canonical: str | None
    correct: bool


class _SynSampleResult(NamedTuple):
    sample_id: str
    hospital: str
    row_results: list[_SynRowResult]
    detection_pass: bool
    detection_pattern: str


def _normalize_expected_canonical(raw: str | None) -> str | None:
    """Normalise a mapped_metric_type from expected.json to what normalize_biomarker returns.

    Some expected.json files use variant names that the live normalizer resolves
    differently (e.g. 'hdl_cholesterol' → 'hdl').  This function collapses those
    so the synthetic benchmark doesn't produce false negatives.
    """
    if raw is None:
        return None
    mapped = _CANONICAL_ALIASES.get(raw)
    if mapped is None and raw in _CANONICAL_ALIASES:
        # Explicitly mapped to None (unknown/future biomarker)
        return None
    return mapped if raw in _CANONICAL_ALIASES else raw


def _test_hospital_detection(hospital_id: str) -> tuple[bool, str]:
    """Test whether HospitalDetector correctly identifies the hospital.

    Strategy: use the first header_pattern of the matching hospital profile as a
    synthetic OCR line, then ask HospitalDetector if it resolves to the correct
    hospital_id.  This tests the detection logic without needing a real image.
    """
    profile = next(
        (p for p in HOSPITAL_PROFILES if p.hospital_id == hospital_id), None
    )
    if profile is None or not profile.header_patterns:
        return False, "(no profile found)"

    detector = HospitalDetector()
    for pattern in profile.header_patterns:
        test_line = pattern  # already accent-stripped lowercase
        detected = detector.detect(test_line)
        if detected is not None and detected.hospital_id == hospital_id:
            return True, pattern

    # Fallback: try hospital_name_variants
    for variant in profile.hospital_name_variants:
        detected = detector.detect(variant)
        if detected is not None and detected.hospital_id == hospital_id:
            return True, variant

    return False, profile.header_patterns[0] if profile.header_patterns else "(none)"


def _run_synthetic_sample(
    sample_path: Path, hospital_id: str
) -> _SynSampleResult | None:
    """Process one expected.json file for the synthetic benchmark."""
    try:
        data = json.loads(sample_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  SKIP {sample_path.name}: {exc}")
        return None

    sample_id = data.get("sample_id", sample_path.stem)
    rows = data.get("rows", [])

    row_results: list[_SynRowResult] = []
    for row in rows:
        original_name = row.get("original_test_name", "")
        expected_raw = row.get("mapped_metric_type")
        expected_canonical = _normalize_expected_canonical(expected_raw)
        got_canonical = normalize_biomarker(original_name)
        correct = (
            expected_canonical is not None
            and got_canonical is not None
            and got_canonical == expected_canonical
        )
        row_results.append(
            _SynRowResult(
                original_name=original_name,
                expected_canonical=expected_canonical,
                got_canonical=got_canonical,
                correct=correct,
            )
        )

    detection_pass, detection_pattern = _test_hospital_detection(hospital_id)
    return _SynSampleResult(
        sample_id=sample_id,
        hospital=hospital_id,
        row_results=row_results,
        detection_pass=detection_pass,
        detection_pattern=detection_pattern,
    )


def run_synthetic_benchmark(bench_dir: Path, hospital_filter: str | None = None) -> bool:
    """Run synthetic mapping accuracy benchmark.  Returns True iff all hospitals pass UER target.

    Walks ``bench_dir/<hospital>/expected/*.expected.json``, runs normalize_biomarker()
    on each original_test_name, compares against mapped_metric_type from the JSON.
    No Azure DI credentials needed.
    """
    if not bench_dir.exists():
        print(f"ERROR: bench_dir not found at {bench_dir}", file=sys.stderr)
        sys.exit(1)

    hospital_dirs = sorted(
        d for d in bench_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    if hospital_filter:
        hospital_dirs = [d for d in hospital_dirs if d.name == hospital_filter]

    if not hospital_dirs:
        print(f"No hospital directories found under {bench_dir}", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("  SYNTHETIC BENCHMARK MODE — MetoCare OCR Phase C")
    print("  (no Azure credentials needed)")
    print("=" * 60)

    all_pass = True
    summary_rows: list[tuple[str, int, int, int, bool]] = []

    for hosp_dir in hospital_dirs:
        hospital_id = hosp_dir.name
        expected_dir = hosp_dir / "expected"
        if not expected_dir.exists():
            print(f"\n[{hospital_id}] No expected/ directory — skipping.")
            continue

        sample_files = sorted(expected_dir.glob("*.expected.json"))
        if not sample_files:
            print(f"\n[{hospital_id}] No *.expected.json files — skipping.")
            continue

        print(f"\nHOSPITAL: {hospital_id}")

        hosp_total = 0
        hosp_mapped = 0
        hosp_unmapped: list[tuple[str, str | None]] = []
        hosp_detection_pass = False
        hosp_detection_pattern = ""
        target_uer = _EDITING_TARGETS.get(hospital_id, 0.20)

        for sf in sample_files:
            result = _run_synthetic_sample(sf, hospital_id)
            if result is None:
                continue

            total = len(result.row_results)
            mapped = sum(1 for r in result.row_results if r.correct)
            unmapped = [
                (r.original_name, r.got_canonical)
                for r in result.row_results
                if not r.correct
            ]

            hosp_total += total
            hosp_mapped += mapped
            hosp_unmapped.extend(unmapped)
            hosp_detection_pass = result.detection_pass
            hosp_detection_pattern = result.detection_pattern

            unmapped_strs = ", ".join(
                f"'{n}' → {c!r}" for n, c in unmapped
            ) if unmapped else "(none)"
            print(
                f"  Sample: {result.sample_id} | Rows: {total} | "
                f"Mapped: {mapped}/{total} | Unmapped: {total - mapped}"
            )
            if unmapped:
                print(f"  Unmapped: [{unmapped_strs}]")

        if hosp_total == 0:
            continue

        canon_acc = hosp_mapped / hosp_total
        uer = 1.0 - canon_acc
        hospital_pass = uer <= target_uer
        detect_label = (
            f"PASS (via pattern '{hosp_detection_pattern}')"
            if hosp_detection_pass
            else f"FAIL (pattern '{hosp_detection_pattern}' not detected)"
        )

        print(f"  Canonicalization accuracy: {canon_acc:.0%}")
        print(f"  Hospital detection: {detect_label}")
        print(
            f"  Target UER: ≤{target_uer:.0%} | "
            f"Actual UER: {uer:.0%} | "
            f"{'PASS' if hospital_pass else 'FAIL'}"
        )

        if not hospital_pass:
            all_pass = False

        summary_rows.append((hospital_id, hosp_total, hosp_mapped, len(hosp_unmapped), hospital_pass))

    # ── Final summary ──────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  SYNTHETIC BENCHMARK SUMMARY")
    print("=" * 60)

    total_rows = sum(r[1] for r in summary_rows)
    total_mapped = sum(r[2] for r in summary_rows)
    passing = sum(1 for r in summary_rows if r[4])
    n_hospitals = len(summary_rows)

    mapped_pct = total_mapped / total_rows * 100 if total_rows else 0
    print(
        f"  Total hospitals: {n_hospitals} | "
        f"Total rows: {total_rows} | "
        f"Mapped: {total_mapped}/{total_rows} ({mapped_pct:.1f}%)"
    )
    print(f"  Passing hospitals (UER ≤ target): {passing}/{n_hospitals}")
    print()
    result_label = "PASS" if all_pass else "FAIL"
    print(f"  RESULT: {result_label}")
    print("=" * 60)

    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="MetoCare OCR accuracy benchmark")
    parser.add_argument("--bench-dir", default="./bench_data", help="Root benchmark directory")
    parser.add_argument("--hospital", help="Run only this hospital (e.g. vinmec)")
    parser.add_argument("--no-cache", action="store_true", help="Re-call Azure DI even if cache exists")  # noqa: E501
    parser.add_argument(
        "--synthetic-mode",
        action="store_true",
        help="Run synthetic mapping benchmark (no Azure credentials needed)",
    )
    args = parser.parse_args()

    # ── Synthetic mode ─────────────────────────────────────────────────────────
    if args.synthetic_mode:
        default_bench = _BACKEND_DIR / "ocr_dataset" / "benchmark"
        bench_dir = Path(args.bench_dir).resolve() if args.bench_dir != "./bench_data" else default_bench
        ok = run_synthetic_benchmark(bench_dir, hospital_filter=args.hospital)
        sys.exit(0 if ok else 1)

    bench_dir = Path(args.bench_dir).resolve()
    if not bench_dir.exists():
        print(f"ERROR: bench_data not found at {bench_dir}", file=sys.stderr)
        print("Layout: bench_data/{hospital}/{report_id}/image.pdf + ground_truth.json", file=sys.stderr)  # noqa: E501
        sys.exit(1)

    hospitals = sorted(
        d.name for d in bench_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    if args.hospital:
        hospitals = [h for h in hospitals if h == args.hospital]

    if not hospitals:
        print(f"No hospital directories found under {bench_dir}", file=sys.stderr)
        sys.exit(1)

    all_hospitals: dict[str, list[ReportResult]] = {}

    for hospital in hospitals:
        report_dirs = sorted(
            d for d in (bench_dir / hospital).iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        if not report_dirs:
            continue

        print(f"\n[{hospital}] processing {len(report_dirs)} reports...")
        results: list[ReportResult] = []

        for report_dir in report_dirs:
            gt_path = report_dir / "ground_truth.json"
            if not gt_path.exists():
                print(f"  SKIP {report_dir.name}: no ground_truth.json")
                continue

            gt = json.loads(gt_path.read_text())
            cache = report_dir / "_azure_result.json"

            if cache.exists() and not args.no_cache:
                azure_result = json.loads(cache.read_text())
                print(f"  {report_dir.name}: (cached)")
            else:
                img = _find_image(report_dir)
                if img is None:
                    print(f"  SKIP {report_dir.name}: no image file")
                    continue
                print(f"  {report_dir.name}: calling Azure DI on {img.name} ...", end="", flush=True)  # noqa: E501
                try:
                    azure_result = _call_azure_di(img)
                    cache.write_text(json.dumps(azure_result, ensure_ascii=False, indent=2))
                    print(" done")
                except Exception as exc:
                    print(f" ERROR: {exc}")
                    continue

            results.append(_evaluate_report(report_dir.name, gt, azure_result))

        all_hospitals[hospital] = results
        _print_hospital_report(hospital, results)

    _print_summary(all_hospitals)


if __name__ == "__main__":
    main()
