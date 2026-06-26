# TASK REPORT — MetoCare OCR: Provider-Specific Lab Extraction Architecture

**DATE:** 2026-06-26  
**BRANCH:** `feat/ocr-provider-profiles`  
**COMMIT:** `ed7569f`  
**ASSIGNED_TO:** Claude Code  
**STATUS:** ✅ COMPLETE — awaiting Codex review + PTH approval before merge

---

## STATUS

All acceptance criteria met. Pre-existing test failure (`test_interpret_document_promotes_metrics`) is unchanged from main baseline and is NOT caused by this PR.

---

## Provider Detection

**Implementation:** `extract_and_map()` now runs `detect_hospital()` on the full document text before table extraction (Layer 2 before Layer 1).

**Key fix:** `_get_full_text()` places the top-level `content` string and page lines FIRST, ensuring hospital name patterns fall within the first 30 lines that `detect_hospital()` inspects. Without this ordering, cell text from tables would push the hospital header beyond line 30.

**Confirmed working:**
- Vinmec: detected via "BỆNH VIỆN ĐA KHOA QUỐC TẾ VINMEC" → `hospital_id=vinmec`
- Medlatec: detected via "HỆ THỐNG Y TẾ MEDLATEC" → `hospital_id=medlatec`
- Unknown content: returns `None` → unknown provider gate activates

---

## Parser Changes

### `OcrTableRow.display_test_name` (new field)

```python
@dataclass
class OcrTableRow:
    original_test_name: str   # raw as printed: "Glucose (máu) (Cobas C502)"
    display_test_name: str    # cleaned for alias matching: "Glucose (máu)"
    ...
```

`map_table_rows_to_raw_values()` now uses `display_test_name` (not `original_test_name`) for alias lookup. The `raw_test_name` field in `RawLabValue` still carries `original_test_name`.

### `_COL_ROLE_KEYWORDS` extended

Added 4 new non-value column roles:
- `price`: "don gia", "gia tien", "phi", "thanh tien" — Medlatec "Đơn giá"
- `note`: "ghi chu", "nhan xet", "tang", "giam" — Medlatec "Ghi chú"  
- `procedure`: "quy trinh", "procedure" — Vinmec "Quy trình"
- `device`: "thiet bi", "device", "cobas pro" — Vinmec "Thiết bị"

All four roles → `_NON_VALUE_ROLES` → explicitly blocked from `value_col`.

### `_NON_VALUE_ROLES` safety set

```python
_NON_VALUE_ROLES: frozenset[str] = frozenset({
    "method", "price", "note", "procedure", "device", "stt",
})
```

Replaces the old method-only check. The safety fallback logic in `_detect_column_roles()` now guards against ALL non-value roles.

### Test name keyword improvements

- Added `"chi đinh"`, `"chi dinh"` to `test_name` (for "Chỉ định" — Vinmec header)
- Added `"danh muc kham"`, `"danh muc"` to `test_name` (for "Danh mục khám" — Medlatec)
- Added `"đon vi"` to `unit` (for "Đơn vị" — "đ" is U+0111, not decomposable under NFD)
- Removed `"ten ket qua"` from `test_name` (caused "Kết quả" header to incorrectly match test_name via bidirectional substring check)
- Removed `"ket qua xet nghiem"` from `test_name` (same issue; "ket qua" in "ket qua xet nghiem" was True)

### Signature updates

- `extract_table_rows(analyze_result, hospital_id=None)` — passes hospital_id to `clean_test_name()`
- `map_table_rows_to_raw_values(table_rows, ocr_conf=0.95, hospital_id=None)` — unknown provider gate

### Cortisol added

Added `cortisol` to `lab_interpreter.BIOMARKERS` and `lab_reference.json` (category: `adrenal`) to support the Medlatec 11/11 golden fixture requirement.

---

## Test Name Cleaner

Function: `clean_test_name(name: str, hospital_id: str | None = None) -> str`

Strip patterns (`_TEST_NAME_STRIP_PATTERNS`):
1. `\(\s*Cobas\s+[A-Za-z0-9]+\s*\)` — "(Cobas C502)", "(Cobas Pro)", "(Cobas 8000)"
2. `\(\s*C\d{3,4}\s*\)` — "(C502)", "(C702)"
3. `\(\s*QX[\.\w]*\s*\)` — QX series
4. `\(\s*AU\d{3,4}\s*\)` — "(AU480)", "(AU680)"
5. `\(\s*Sysmex\s+[A-Za-z0-9]+\s*\)` — "(Sysmex XN1000)"
6. `\*\s*$` — trailing asterisk (Medlatec abnormal flag)

**Sample results:**
| Input | Output |
|-------|--------|
| `"Glucose (máu) (Cobas C502)"` | `"Glucose (máu)"` |
| `"Triglyceride (Cobas C502)"` | `"Triglyceride"` |
| `"Cholesterol toàn phần (Cobas C502)*"` | `"Cholesterol toàn phần"` |
| `"ALT (GPT)"` | `"ALT (GPT)"` (unchanged) |
| `"Glucose lúc đói"` | `"Glucose lúc đói"` (unchanged) |

Sample types like `"(máu)"` are intentionally preserved.

---

## Vinmec Fixture (expected vs actual)

**Fixture:** `backend/tests/fixtures/vinmec_mock_table.py`  
**Result: 16/16** ✅

| Biomarker | Expected value | Expected unit | Actual value | Actual unit | Match |
|-----------|---------------|---------------|-------------|-------------|-------|
| urea | 4.47 | mmol/L | 4.47 | mmol/L | ✅ |
| creatinine | 82.2 | µmol/L | 82.2 | µmol/L | ✅ |
| fasting_glucose | 4.78 | mmol/L | 4.78 | mmol/L | ✅ |
| ast | 34.7 | U/L | 34.7 | U/L | ✅ |
| alt | 58.4 | U/L | 58.4 | U/L | ✅ |
| total_cholesterol | 5.99 | mmol/L | 5.99 | mmol/L | ✅ |
| triglyceride | 2.7 | mmol/L | 2.7 | mmol/L | ✅ |
| hdl | 1.08 | mmol/L | 1.08 | mmol/L | ✅ |
| ldl | 4.24 | mmol/L | 4.24 | mmol/L | ✅ |
| sodium | 140 | mmol/L | 140.0 | mmol/L | ✅ |
| potassium | 3.95 | mmol/L | 3.95 | mmol/L | ✅ |
| chloride | 100.7 | mmol/L | 100.7 | mmol/L | ✅ |
| ft3 | 4.64 | pmol/L | 4.64 | pmol/L | ✅ |
| ft4 | 18 | pmol/L | 18.0 | pmol/L | ✅ |
| tsh | 1.26 | µIU/mL | 1.26 | µIU/mL | ✅ |
| thyroglobulin | 0.118 | ng/mL | 0.118 | ng/mL | ✅ |

**"Thiết bị" / "Quy trình" columns:** Never appear as result values ✅

---

## Medlatec Fixture (expected vs actual)

**Fixture:** `backend/tests/fixtures/medlatec_inline_mock_table.py`  
**Result: 11/11** ✅

| Biomarker | Expected value | Expected unit | Actual value | Actual unit | Match |
|-----------|---------------|---------------|-------------|-------------|-------|
| ast | 25.37 | U/L | 25.37 | U/L | ✅ |
| alt | 51.63 | U/L | 51.63 | U/L | ✅ |
| ggt | 75.78 | U/L | 75.78 | U/L | ✅ |
| fasting_glucose | 5.73 | mmol/L | 5.73 | mmol/L | ✅ |
| urea | 4.55 | mmol/L | 4.55 | mmol/L | ✅ |
| creatinine | 87.66 | µmol/L | 87.66 | µmol/L | ✅ |
| triglyceride | 1.97 | mmol/L | 1.97 | mmol/L | ✅ |
| total_cholesterol | 5.49 | mmol/L | 5.49 | mmol/L | ✅ |
| hdl | 1.01 | mmol/L | 1.01 | mmol/L | ✅ |
| ldl | 3.59 | mmol/L | 3.59 | mmol/L | ✅ |
| cortisol | 2.50 | nmol/L | 2.50 | nmol/L | ✅ |

**Value 502:** Never appears in any result ✅  
**"Đơn giá" price column:** Never appears as result ✅  
**display_test_name:** All "(Cobas C502)" suffixes stripped ✅  
**original_test_name:** Full as-printed text preserved ✅

---

## Safety Gates

### Unknown Provider Gate
- When `hospital_id is None`: all rows → `requires_review=True`, `ocr_confidence = min(conf, 0.5)`
- No unknown-provider rows auto-promoted to patient metrics
- Frontend can show: "Nhà cung cấp không xác định — vui lòng xác nhận thủ công"

### Existing Guards (unchanged)
- `suspect_machine_id=True` rows blocked from mapped output (layer 3)
- `verified_by_user=False` rows blocked from metric promotion (lab.py _promote_row)

---

## Test Results

| Metric | Value |
|--------|-------|
| Tests on main (baseline) | 950 passed, 1 failed (pre-existing), 2 skipped |
| Tests on feat/ocr-provider-profiles | 1011 passed, 1 failed (same pre-existing), 1 skipped |
| New tests added | 61 tests across 5 new test classes |
| Pre-existing failure | `test_interpret_document_promotes_metrics` — unchanged, NOT caused by this PR |
| Ruff check | All checks passed |

### New Test Classes

| Class | Tests | Coverage |
|-------|-------|---------|
| `TestProviderDetection` | 7 | hospital detection, extract_and_map integration |
| `TestVinmecGoldenFixture` | 22 | 16 parametrized + 6 structural |
| `TestMedlatecInlineGoldenFixture` | 18 | 11 parametrized + 7 structural |
| `TestTestNameCleaner` | 10 | clean_test_name() unit tests |
| `TestUnknownProviderGate` | 5 | requires_review + confidence cap |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/domain/lab_table_extractor.py` | Primary implementation (+170 lines) |
| `backend/app/domain/lab_interpreter.py` | cortisol BiomarkerSpec added (+8 lines) |
| `backend/app/domain/lab_reference.json` | cortisol catalog entry + adrenal category (+26 lines) |
| `backend/tests/test_lab_table_extractor.py` | 5 new test classes (+423 lines) |
| `backend/tests/fixtures/vinmec_mock_table.py` | New fixture file (+103 lines) |
| `backend/tests/fixtures/medlatec_inline_mock_table.py` | New fixture file (+101 lines) |
| `backend/tests/fixtures/__init__.py` | Empty init (new) |

---

## Remaining Risks

1. **Real Medlatec reports** may embed machine name differently from the mock (e.g. `"Cobas C 502"` with space between letter and digits). The regex `r"\(\s*Cobas\s+[A-Za-z0-9]+\s*\)"` handles `C502` as a single token but would fail `"Cobas C 502"`. Recommend validating against 2–3 real Medlatec PDFs before merge.

2. **Cortisol reference range** in the fixture (138–635 nmol/L) represents the AM morning reference. The test value 2.50 nmol/L is below the reference low — this will result in `requires_review=True` which is correct medical behaviour. The physiological range (0.1–5000) is intentionally wide.

3. **"chi đinh" vs "chi dinh"** — the "đ" normalization fix relies on adding both `"chi đinh"` and `"chi dinh"` to the keyword set. If ruff introduces an encoding issue in the future, the accented form may not match. The test `TestProviderDetection::test_extract_and_map_detects_vinmec_provider` catches this regression.

4. **`test_interpret_document_promotes_metrics`** — pre-existing failure on main. The test expects unverified OCR rows to be auto-promoted (old behaviour), but the FU-1 gate blocks them. This test needs to be updated separately to use `verified_by_user=True` lab results.

---

## Recommendation

**READY FOR CODEX REVIEW.** Do not merge until:
1. Codex read-only review complete
2. PTH approves after reviewing Codex findings
3. Validation against 2–3 real Medlatec lab PDFs confirms the fix holds
4. `test_interpret_document_promotes_metrics` addressed (separate PR or approved skip)
