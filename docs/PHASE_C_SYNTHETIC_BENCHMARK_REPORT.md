# MetoCare OCR — Phase C: Synthetic Benchmark Report

**Date:** 2026-06-26  
**Author:** Subagent (Claude Code)  
**Task:** Add `--synthetic-mode` to `benchmark_ocr.py` for CI accuracy checks without Azure credentials.

---

## Implementation Summary

### What was changed

**File modified:** `backend/scripts/benchmark_ocr.py`

Added:
1. **`_CANONICAL_ALIASES` dict** — maps `mapped_metric_type` variants found in `expected.json` files to the canonical names that `normalize_biomarker()` actually returns. This bridges minor name discrepancies (e.g. `hdl_cholesterol` → `hdl`, `triglycerides` → `triglyceride`) without touching any domain module.

2. **`_SynRowResult` / `_SynSampleResult` NamedTuples** — lightweight result containers for synthetic benchmark rows.

3. **`_normalize_expected_canonical(raw)`** — normalises `mapped_metric_type` from expected.json using `_CANONICAL_ALIASES`, returns `None` for explicitly unknown biomarkers (e.g. `calcium` not yet in BIOMARKERS).

4. **`_test_hospital_detection(hospital_id)`** — verifies `HospitalDetector` can identify a hospital using its own `header_patterns` / `hospital_name_variants`. No images needed.

5. **`_run_synthetic_sample(sample_path, hospital_id)`** — processes one `*.expected.json` file: runs `normalize_biomarker(original_test_name)` per row, compares with normalized expected canonical.

6. **`run_synthetic_benchmark(bench_dir, hospital_filter)`** — walks `bench_dir/<hospital>/expected/*.expected.json`, produces per-hospital table output, returns `True` iff all hospitals meet UER target.

7. **`--synthetic-mode` CLI flag** in `main()` — when set, calls `run_synthetic_benchmark()` instead of the real Azure benchmark. Default `--bench-dir` for this mode is `./ocr_dataset/benchmark`.

**File created:** `backend/tests/test_synthetic_benchmark.py`

34 tests covering:
- `_normalize_expected_canonical()` — alias mapping, passthrough, None inputs
- `_test_hospital_detection()` — parametrized over all 7 known hospitals, unknown hospital returns False
- `run_synthetic_benchmark()` — full integration with real benchmark dir, hospital filter, missing dir exits 1, hand-crafted expected.json
- `normalize_biomarker()` edge cases — all original_test_name values from expected.json

### Real benchmark path unchanged

The real Azure benchmark (no `--synthetic-mode`) is completely unchanged. All existing tests pass.

---

## Full Benchmark Output

```
============================================================
  SYNTHETIC BENCHMARK MODE — MetoCare OCR Phase C
  (no Azure credentials needed)
============================================================

HOSPITAL: bachmai
  Sample: 20260626_bachmai_001 | Rows: 10 | Mapped: 10/10 | Unmapped: 0
  Canonicalization accuracy: 100%
  Hospital detection: PASS (via pattern 'bach mai')
  Target UER: ≤20% | Actual UER: 0% | PASS

[bachmai108] No *.expected.json files — skipping.

[fv] No *.expected.json files — skipping.

[hoanmy] No *.expected.json files — skipping.

HOSPITAL: hongngoc
  Sample: 20260626_hongngoc_001 | Rows: 10 | Mapped: 10/10 | Unmapped: 0
  Canonicalization accuracy: 100%
  Hospital detection: PASS (via pattern 'hong ngoc')
  Target UER: ≤20% | Actual UER: 0% | PASS

HOSPITAL: medlatec
  Sample: 20260626_medlatec_001 | Rows: 12 | Mapped: 12/12 | Unmapped: 0
  Canonicalization accuracy: 100%
  Hospital detection: PASS (via pattern 'medlatec')
  Target UER: ≤15% | Actual UER: 0% | PASS

[other] No *.expected.json files — skipping.

HOSPITAL: tamanh
  Sample: 20260626_tamanh_001 | Rows: 10 | Mapped: 8/10 | Unmapped: 2
  Unmapped: ['Đường huyết lúc đói' → None, 'Urê' → None]
  Canonicalization accuracy: 80%
  Hospital detection: PASS (via pattern 'tam anh')
  Target UER: ≤20% | Actual UER: 20% | PASS

[thucuc] No *.expected.json files — skipping.

[vietduc] No *.expected.json files — skipping.

HOSPITAL: vinmec
  Sample: 20261224_vinmec_001 | Rows: 16 | Mapped: 15/16 | Unmapped: 1
  Unmapped: ['Canxi (Ca2+)' → None]
  Canonicalization accuracy: 94%
  Hospital detection: PASS (via pattern 'vinmec')
  Target UER: ≤10% | Actual UER: 6% | PASS

============================================================
  SYNTHETIC BENCHMARK SUMMARY
============================================================
  Total hospitals: 5 | Total rows: 58 | Mapped: 55/58 (94.8%)
  Passing hospitals (UER ≤ target): 5/5

  RESULT: PASS
============================================================
```

## Exit Code

```
Exit: 0
```

All 5 hospitals with expected data pass their UER targets.

---

## Test Results

```
# New synthetic benchmark tests
tests/test_synthetic_benchmark.py::34 tests — 34 passed in 0.08s

# Existing OCR tests (regression check)
tests/test_lab_interpreter.py
tests/test_lab_hospital_profiles.py
tests/test_lab_table_extractor.py
tests/test_ocr_dataset.py
→ 324 passed in 0.50s
```

**Total: 358 tests — 0 failures, 0 errors.**

Ruff lint: `All checks passed!`

---

## Gaps Found (Unmapped rows)

| Hospital | Test Name | Reason |
|----------|-----------|--------|
| tamanh | `Đường huyết lúc đói` | Accented Vietnamese form not in `BIOMARKERS` aliases |
| tamanh | `Urê` | Accented `ê` form not in `BIOMARKERS` aliases |
| vinmec | `Canxi (Ca2+)` | Calcium (`Ca2+`) not yet a supported biomarker in BIOMARKERS |

These are **real gaps** in `normalize_biomarker()` coverage, not benchmark bugs. The tamanh hospital profile has `"fasting_glucose": ("duong huyet luc doi", "glucose luc doi")` in `additional_aliases` but those are accent-stripped forms — the accented original `Đường huyết lúc đói` needs to be in the base `BIOMARKERS` aliases. Similarly `Urê` vs `ure`.

---

## Remaining Limitations (What synthetic mode does NOT cover)

1. **Azure DI output quality** — Synthetic mode only tests `normalize_biomarker()` on ground-truth names. It does not test whether Azure Document Intelligence correctly extracts those names from real lab images. OCR errors, column misalignment, garbled text, missing rows — none of these are measured.

2. **Value / unit / reference_range accuracy** — Synthetic mode ignores numeric values. It only checks whether the test name canonicalizes correctly, not whether the extracted value matches ground truth.

3. **Table extraction pipeline** — `extract_and_map()`, `OcrTableRow`, column-role detection, `UnitNormalizer` — none of these code paths are exercised. Bugs in the table extractor won't surface in synthetic mode.

4. **Multi-sample hospitals** — Currently each hospital has 1 `expected.json`. Synthetic UER is computed over all samples; a single outlier sample would hide per-sample variance.

5. **New biomarkers** — Biomarkers not yet in `BIOMARKERS` (e.g. `calcium`, accented Vietnamese forms) produce false negatives in synthetic mode. These register as gaps, which is the correct behavior, but they need to be added to `lab_interpreter.py` to improve coverage.

6. **Hospital detection confidence** — `_test_hospital_detection()` tests only binary pass/fail using the hospital's own pattern. Real-world OCR text may have different casing, extra characters, or noise that reduces confidence below threshold.

---

## Recommended Next Steps

1. **Add `Đường huyết lúc đói` and `Urê` to BIOMARKERS aliases** in `lab_interpreter.py` to close the 2 tamanh gaps (reduce UER to 0%).
2. **Add `calcium` as a BIOMARKER** for vinmec support.
3. **Add real lab images** to `ocr_dataset/benchmark/*/images/` and run full Azure benchmark once credentials are available.
4. **Add more expected.json samples** (target ≥3 per hospital) for statistically meaningful UER measurement.
