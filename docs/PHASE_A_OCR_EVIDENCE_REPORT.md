# Phase A: OCR Evidence Foundation Report

**Date:** 2026-06-26
**Status:** Evidence-only. No parser code was modified.
**Pipeline:** Azure Document Intelligence → `hospital_profiles.py` (hospital detection) → `lab_table_extractor.py` (extraction) → `lab_interpreter.py` (canonicalization)
**Target accuracy:** ≥80% row-level (User Editing Rate ≤20%)

---

## 1. Benchmark Dataset Summary

### 1.1 Samples per Hospital (post Phase A)

| Hospital (folder) | profile hospital_id | Tier | Samples | Rows |
|---|---|---|---|---|
| vinmec | vinmec | benchmark | 1 | 16 |
| medlatec | medlatec | benchmark | 1 | 12 |
| tamanh | tam_anh | benchmark | 1 | 10 |
| hongngoc | hong_ngoc | benchmark | 1 | 10 |
| bachmai | bach_mai | benchmark | 1 | 10 |
| **TOTAL** | | | **5** | **58** |

All samples are synthetic (no PHI, no images). `ocr_dataset_validate.py` passes with **5/5 OK**.

### 1.2 What each sample covers

| Sample | Key clinical scenarios included |
|---|---|
| 20261224_vinmec_001 | All-normal baseline, wide panel (16 rows), full lipid + CMP + TSH + electrolytes |
| 20260626_medlatec_001 | HbA1c high (6.8%), LDL high, ALT high, Uric acid high — 4 abnormals |
| 20260626_tamanh_001 | HDL low (0.95), Cholesterol high, Triglycerides high — lipid triad; SGOT/SGPT naming |
| 20260626_hongngoc_001 | HbA1c high (7.2%), ALT borderline high; HDL-C/LDL-C short-form aliases |
| 20260626_bachmai_001 | Triple lipid elevation (Cholesterol + LDL + Triglycerid); LDL "(tính)" suffix |

---

## 2. Hospital Profile Inventory

### 2.1 All Hospital IDs in `hospital_profiles.py`

| profile hospital_id | benchmark folder | column_map set? | unit_system | Notes |
|---|---|---|---|---|
| vinmec | vinmec | ✅ Yes (6-col, skip_cols=(5,)) | SI | Most mature profile |
| medlatec | medlatec | ✅ Yes (6-col, skip_cols=(5,)) | SI | Method/machine col skip configured |
| tam_anh | tamanh | ❌ No | SI | **ID MISMATCH: profile uses underscore, folder does not** |
| hong_ngoc | hongngoc | ❌ No | mixed | **ID MISMATCH** + mixed units undocumented |
| hospital_108 | bachmai108 | ❌ No | conventional | Separate from Bach Mai main |
| bach_mai | bachmai | ❌ No | conventional | **ID MISMATCH** + may use mg/dL in older reports |
| fv | fv | ❌ No | SI | English-format reports |

**Profile IDs not covered by benchmark yet:** `hospital_108`, `fv`, `hoanmy`, `thucuc`, `vietduc`

### 2.2 Profiles with NO `additional_aliases`

All profiles currently have `additional_aliases = {}`. This means **zero hospital-specific biomarker alias overrides** are configured. Any test name variant not in `lab_interpreter.BIOMARKERS` aliases will silently fail to map.

---

## 3. Gap Analysis

### 3.1 Lab Interpreter Canonical Keys (all 26)

```
fasting_glucose, hba1c, ldl, hdl, triglyceride, total_cholesterol,
alt, ast, creatinine, egfr, urea, ggt, tsh, ft4, ft3,
hemoglobin, wbc, platelet, rbc, hematocrit,
sodium, potassium, chloride,
thyroglobulin, uric_acid, random_glucose, cortisol
```

### 3.2 Per-Hospital Alias Gap Trace

#### medlatec

| Test name on report | Parser alias match | Canonical | Risk |
|---|---|---|---|
| `Glucose` | ✅ `glucose` in aliases | `fasting_glucose` | None |
| `HbA1c` | ✅ `hba1c` in aliases | `hba1c` | None |
| `Cholesterol TP` | ✅ `chol tp` / `cholesterol tp` in aliases | `total_cholesterol` | None |
| `HDL-Cholesterol` | ✅ `hdl-cholesterol` in aliases | `hdl` | None |
| `LDL-Cholesterol` | ✅ `ldl-cholesterol` in aliases | `ldl` | None |
| `Triglycerid` | ✅ `triglycerid` in aliases | `triglyceride` | None |
| `Ure` | ✅ `ure` in aliases | `urea` | None |
| `Creatinine` | ✅ `creatinine` in aliases | `creatinine` | None |
| `AST` | ✅ `ast` in aliases | `ast` | None |
| `ALT` | ✅ `alt` in aliases | `alt` | None |
| `TSH` | ✅ `tsh` in aliases | `tsh` | None |
| `Acid Uric` | ✅ `acid uric` in aliases | `uric_acid` | None |
| **Col 5: "Cobas C502"** | ❌ Would mis-map if skip_cols not honoured | N/A | **HIGH: Machine ID as value if column_map fails** |

**Medlatec-specific gap:** The 6th column (instrument name) is the primary safety risk. `column_map` is set correctly but only works if `lab_table_extractor.py` respects `skip_cols=(5,)`. OCR errors in column boundaries can shift indices.

#### tam_anh (tamanh folder)

| Test name on report | Parser alias match | Canonical | Risk |
|---|---|---|---|
| `Đường huyết lúc đói` | ✅ `duong huyet luc doi` (accent-stripped) | `fasting_glucose` | Medium — accent stripping must work |
| `HbA1c` | ✅ | `hba1c` | None |
| `Cholesterol` | ✅ `cholesterol` contains-match | `total_cholesterol` | Low — loose contains match |
| `HDL Cholesterol` | ⚠️ `hdl-cholesterol` has hyphen; `HDL Cholesterol` (space) may miss | `hdl` | **MEDIUM: space vs hyphen** |
| `LDL Cholesterol` | ⚠️ Same space vs hyphen issue | `ldl` | **MEDIUM** |
| `Triglycerides` | ✅ `triglycerides` in aliases | `triglyceride` | None |
| `Urê` | ✅ `ure` after accent-strip | `urea` | Low |
| `Creatinine` | ✅ | `creatinine` | None |
| `SGOT (AST)` | ⚠️ `sgot` in aliases → `ast` but combined "SGOT (AST)" needs prefix match | `ast` | **MEDIUM: combined format** |
| `SGPT (ALT)` | ⚠️ Same as above | `alt` | **MEDIUM** |

**Tam Anh-specific gaps:**
1. `HDL Cholesterol` / `LDL Cholesterol` (space, no hyphen) — `lab_interpreter` has `hdl-cholesterol` with hyphen. Loose contains-match on `hdl` would catch it, but only if the contains branch is reached.
2. `SGOT (AST)` combined format — if prefix match (`sgot` in first 4 chars) works, alias catches it; if not, falls through to `unknown`.
3. **Profile ID mismatch**: `hospital_profiles.py` has `hospital_id="tam_anh"` but benchmark folder is `tamanh`. Hospital detection `detect_hospital()` returns `"tam_anh"` — but `ReportResult.hospital_id` compares against ground truth `hospital` field (`"tamanh"`), causing false hospital mismatch in benchmark.

#### hong_ngoc (hongngoc folder)

| Test name on report | Parser alias match | Canonical | Risk |
|---|---|---|---|
| `Glucose máu` | ⚠️ `glucose mau` NOT in aliases | `fasting_glucose` | **HIGH: loose contains on `glucose` only** |
| `HbA1c` | ✅ | `hba1c` | None |
| `Total Cholesterol` | ✅ `total cholesterol` in aliases | `total_cholesterol` | None |
| `HDL-C` | ✅ `hdl-c` in aliases | `hdl` | None |
| `LDL-C` | ✅ `ldl-c` in aliases | `ldl` | None |
| `Triglycerides` | ✅ | `triglyceride` | None |
| `Ure` | ✅ | `urea` | None |
| `Creatinine` | ✅ | `creatinine` | None |
| `AST (GOT)` | ⚠️ `ast` prefix match (4 chars) → OK; `got` also in aliases | `ast` | Low |
| `ALT (GPT)` | ⚠️ `alt` prefix + `gpt` alias | `alt` | Low |

**Hong Ngoc-specific gaps:**
1. `Glucose máu` — "máu" suffix not covered by any alias. Relies on loose contains-match on substring `glucose`. Medium-confidence match only.
2. `unit_system = "mixed"` — undocumented: which tests use SI vs conventional? No documentation in profile.
3. **Profile ID mismatch**: `hospital_id="hong_ngoc"` vs folder `hongngoc`.

#### bach_mai (bachmai folder)

| Test name on report | Parser alias match | Canonical | Risk |
|---|---|---|---|
| `Glucose` | ✅ | `fasting_glucose` | None |
| `HbA1c` | ✅ | `hba1c` | None |
| `Cholesterol` | ✅ contains-match | `total_cholesterol` | Low |
| `HDL-Cholesterol` | ✅ | `hdl` | None |
| `LDL-Cholesterol (tính)` | ❌ Full string not in aliases; `(tính)` suffix prevents match | `ldl` | **HIGH: normalization strips needed** |
| `Triglycerid` | ✅ | `triglyceride` | None |
| `Ure` | ✅ | `urea` | None |
| `Creatinine` | ✅ | `creatinine` | None |
| `AST` | ✅ | `ast` | None |
| `ALT` | ✅ | `alt` | None |

**Bach Mai-specific gaps:**
1. `LDL-Cholesterol (tính)` — "(tính)" suffix = calculated Friedewald value. Parser must strip parenthetical suffixes before alias lookup. Currently likely falls back to contains-match on `ldl` — may work by luck, but is fragile.
2. **Profile ID mismatch**: `hospital_id="bach_mai"` vs folder `bachmai`.
3. No `column_map` — heuristic column detection may mis-identify in complex report layouts.
4. `unit_system = "conventional"` — Bach Mai older reports use mg/dL for lipids; newer use mmol/L. No unit-detection logic per-report.

---

## 4. Known Hospital Name Variants & OCR Alias Issues

### 4.1 Hospital ID Mismatches (Profile vs Folder)

This is a **systemic issue** affecting 3 of 5 benchmarked hospitals:

| Profile `hospital_id` | Benchmark folder | Impact |
|---|---|---|
| `tam_anh` | `tamanh` | Benchmark script hospital match fails |
| `hong_ngoc` | `hongngoc` | Same |
| `bach_mai` | `bachmai` | Same |
| `vinmec` | `vinmec` | ✅ OK |
| `medlatec` | `medlatec` | ✅ OK |

**Consequence:** When `benchmark_ocr.py` runs `detect_hospital()` on a real Tam Anh report and gets `"tam_anh"`, then compares against `ground_truth["hospital_id"] == "tamanh"`, it records a false "hospital detected incorrectly" for every Tam Anh report.

### 4.2 Biomarker Name Variant Matrix

| Canonical | Medlatec form | Tam Anh form | Hong Ngoc form | Bach Mai form |
|---|---|---|---|---|
| `fasting_glucose` | `Glucose` | `Đường huyết lúc đói` | `Glucose máu` | `Glucose` |
| `total_cholesterol` | `Cholesterol TP` | `Cholesterol` | `Total Cholesterol` | `Cholesterol` |
| `hdl` | `HDL-Cholesterol` | `HDL Cholesterol` | `HDL-C` | `HDL-Cholesterol` |
| `ldl` | `LDL-Cholesterol` | `LDL Cholesterol` | `LDL-C` | `LDL-Cholesterol (tính)` |
| `triglyceride` | `Triglycerid` | `Triglycerides` | `Triglycerides` | `Triglycerid` |
| `ast` | `AST` | `SGOT (AST)` | `AST (GOT)` | `AST` |
| `alt` | `ALT` | `SGPT (ALT)` | `ALT (GPT)` | `ALT` |
| `urea` | `Ure` | `Urê` | `Ure` | `Ure` |

---

## 5. Gap Analysis: OCR Gap Module (`ocr_gap_analysis.py`)

`compute_gap(extracted_rows, corrected_rows)` computes per-row diffs using:
1. `mapped_metric_type` equality (canonical key match) — highest priority
2. `original_test_name` 4-character prefix match
3. `display_name_vi` exact match

### 5.1 Manual Gap Trace: If Parser Missed These

**Scenario A: HDL alias miss (space vs hyphen)**
- Extracted: `original_test_name="HDL Cholesterol"`, `mapped_metric_type=None` (unmapped)
- Corrected: `original_test_name="HDL Cholesterol"`, `mapped_metric_type="hdl"`
- Gap result: `biomarker_corrected=True`, `edit_type="biomarker"` → counted in `biomarker_mismatches`
- Impact: `biomarker_accuracy` decreases; `editing_rate` increases by 1/N

**Scenario B: Triglycerid vs Triglycerides spelling**
- Extracted: `original_test_name="Triglycerid"` from Medlatec, `mapped_metric_type="triglyceride"` ✅
- Extracted: `original_test_name="Triglycerides"` from Tam Anh, `mapped_metric_type="triglyceride"` ✅
- Both forms are in `lab_interpreter.py` aliases → **no gap** if parser uses aliases correctly
- BUT: if lab_table_extractor does exact-match instead of alias-lookup, "Triglycerid" ≠ "Triglycerides" → gap

**Scenario C: SGOT vs AST naming (Tam Anh)**
- Extracted: `original_test_name="SGOT (AST)"`, parser does 4-char prefix `"sgot"` → matches `sgot` alias → `ast` ✅
- If prefix match fails (e.g. parser normalizes to `"sgot (ast)"` and checks full string): miss
- Gap result: `test_name_matched=False`, `edit_type="added"` for corrected row + `edit_type="deleted"` for extracted
- Both `missing_rows` and `false_positive_rows` increment → severe impact on `row_accuracy`

**Scenario D: LDL-Cholesterol (tính) — Bach Mai**
- Extracted: `original_test_name="LDL-Cholesterol (tính)"`, loose contains-match on `ldl` → `ldl` ✅ (maybe)
- If contains-match hits `ldl` substring: `mapped_metric_type="ldl"` → no gap
- If exact-match fails and contains-match also fails: `mapped_metric_type=None` → biomarker gap
- Fragility: relies on `normalize_biomarker` contains-branch, not explicit alias

---

## 6. Recommended Fixes for Phase B (Ranked by Impact)

### Priority 1 — CRITICAL (blocks accurate benchmarking)

**P1.1: Resolve profile ID vs folder name mismatch**
- Files: `hospital_profiles.py` OR rename benchmark folders (prefer fix in profiles)
- Change: `"tam_anh"` → `"tamanh"`, `"hong_ngoc"` → `"hongngoc"`, `"bach_mai"` → `"bachmai"`
- OR: add a `folder_id` field to `HospitalProfile` for benchmark mapping
- Impact: 3 hospitals currently report 0% hospital detection accuracy in benchmark

**P1.2: Add `additional_aliases` for hospital-specific biomarker name variants**
- `tam_anh`: `fasting_glucose → ("đường huyết lúc đói", "duong huyet luc doi")`
- `hong_ngoc`: `fasting_glucose → ("glucose máu", "glucose mau")`
- All profiles: `hdl → ("hdl cholesterol",)` (space, no hyphen)
- All profiles: `ldl → ("ldl cholesterol",)` (space, no hyphen)

**P1.3: Add parenthetical suffix stripping in `normalize_biomarker()`**
- Strip `(tính)`, `(calculated)`, `(GOT)`, `(GPT)`, `(AST)`, `(ALT)` before alias lookup
- Affects: Bach Mai `LDL-Cholesterol (tính)`, Hong Ngoc `AST (GOT)` / `ALT (GPT)`, Tam Anh `SGOT (AST)` / `SGPT (ALT)`

### Priority 2 — HIGH (parser correctness)

**P2.1: Add `column_map` for `bach_mai`, `tam_anh`, `hong_ngoc`**
- Current: all three use heuristic column detection
- Risk: "Ghi chú" or method columns mis-identified as value columns
- Need: real report samples to determine correct column indices

**P2.2: Document and validate `unit_system="mixed"` for Hong Ngoc**
- Which biomarkers use SI vs conventional at Hong Ngoc?
- Add per-biomarker unit conversion hints to profile

**P2.3: Add `footer_patterns` for hospitals with signature/disclaimer rows**
- Bach Mai reports include footer rows ("Bác sĩ ký tên:", disclaimers)
- These may be parsed as data rows if not excluded

### Priority 3 — MEDIUM (robustness)

**P3.1: Add `benchmark_ocr.py --synthetic-mode` flag**
- Current: script requires real Azure DI (no synthetic execution path)
- Need: mode that reads `_azure_result.json` cache or generates synthetic OCR from `.expected.json`
- Would allow CI-runnable accuracy regression tests without Azure credentials

**P3.2: Expand benchmark to 3+ samples per hospital**
- Current: 1 synthetic sample per hospital (n=5 total, 58 rows)
- Phase B target: 3-5 samples per hospital including real anonymized images
- Priority hospitals for real samples: medlatec, tamanh (highest patient volume)

**P3.3: Add `hospital_name_variants` OCR corrections for space/punctuation variants**
- `"hong ngoc"` pattern vs `"hongngoc"` (no space) — header detection may fail on some scans

---

## 7. Benchmark Script: Run Instructions

### 7.1 Validate dataset (synthetic, no Azure required)

```bash
cd /Users/pth/Developer/Metocare/backend
uv run python scripts/ocr_dataset_validate.py
# Expected: 5 passed, 0 failed
```

### 7.2 Full benchmark (requires Azure DI credentials)

```bash
cd /Users/pth/Developer/Metocare/backend
export AZURE_DOC_INTEL_ENDPOINT="https://your-resource.cognitiveservices.azure.com"
export AZURE_DOC_INTEL_KEY="your-key"

# First run: calls Azure DI, caches results in _azure_result.json
uv run python scripts/benchmark_ocr.py --bench-dir ./bench_data

# Subsequent runs: uses cached results (no API call)
uv run python scripts/benchmark_ocr.py --bench-dir ./bench_data

# Force re-call Azure DI
uv run python scripts/benchmark_ocr.py --bench-dir ./bench_data --no-cache

# Single hospital only
uv run python scripts/benchmark_ocr.py --bench-dir ./bench_data --hospital vinmec
```

### 7.3 Notes on benchmark_ocr.py synthetic support

`benchmark_ocr.py` does NOT currently support running against synthetic `.expected.json` samples.
It requires:
1. An image/PDF file under `bench_data/<hospital>/<report_id>/`
2. A `ground_truth.json` file (different schema from `expected.json`)
3. Either Azure DI credentials or a pre-existing `_azure_result.json` cache

**Phase B action required:** Add a `--synthetic-mode` that reads `ocr_dataset/benchmark/` `.expected.json` files and simulates extraction to enable CI benchmarking.

---

## 8. Appendix: Lab Interpreter Canonical Key → Alias Coverage

Key aliases relevant to Vietnamese hospital OCR (accent-stripped, lowercase):

| Canonical | Critical aliases for VN hospitals |
|---|---|
| `fasting_glucose` | `glucose`, `duong huyet`, `duong huyet luc doi`, `glucose mau` (missing for hong_ngoc) |
| `hba1c` | `hba1c`, `a1c` — well covered |
| `total_cholesterol` | `cholesterol`, `chol tp`, `cholesterol tp`, `total cholesterol` — well covered |
| `hdl` | `hdl-cholesterol`, `hdl-c`, `hdl` — **missing: `hdl cholesterol` (space)** |
| `ldl` | `ldl-cholesterol`, `ldl-c`, `ldl` — **missing: `ldl cholesterol` (space)** |
| `triglyceride` | `triglycerid`, `triglycerides`, `tg` — well covered |
| `ast` | `ast`, `sgot`, `got` — covered; parenthetical `SGOT (AST)` form needs strip |
| `alt` | `alt`, `sgpt`, `gpt` — covered; parenthetical form needs strip |
| `urea` | `ure`, `bun`, `urea` — well covered |
| `creatinine` | `creatinine`, `creatinin`, `crea` — well covered |
| `tsh` | `tsh` — only 3 aliases; Vietnamese "TSH" is same → OK |
| `uric_acid` | `acid uric`, `uric acid`, `axit uric` — well covered |
