# CODEX REVIEW: MetoCare OCR Provider Architecture — feat/ocr-provider-profiles

**Date:** 2026-06-26  
**Branch:** `feat/ocr-provider-profiles`  
**Commits reviewed:** `ed7569f`, `0ab65d8`, `8ad3e97`  
**Reviewer:** Codex (read-only)

---

## VERDICT: APPROVE_WITH_NOTES

---

## P0 ISSUES: NONE

No blocking issues found. The core bug (Cobas C502 machine ID leaking as value `502`) is correctly fixed. Production safety gates are intact.

---

## P1 ISSUES

1. **`"(Cobas C 502)"` with space between letter and digit is NOT stripped.**
   - Regex: `\(\s*Cobas\s+[A-Za-z0-9]+\s*\)` requires `C502` as a single alphanumeric token.
   - `"Cobas C 502"` (letter + space + digits) does not match — tested and confirmed.
   - Impact: if real Medlatec PDFs contain this spacing variant, the P0 bug resurfaces for that row (alias lookup fails → row skipped or fallback value extracted). The aliased row would simply not map — it would not erroneously extract 502 as a value, because the `suspect_machine_id` guard is on a separate layer. However, the biomarker would be silently missed.
   - **Action required:** Validate at least 2–3 real Medlatec PDFs before merge. If space-variant occurs, widen pattern to `Cobas\s+[A-Za-z]+\s*[0-9]+`.

2. **Pre-existing failure `test_interpret_document_promotes_metrics` on main is now fixed by `8ad3e97`.**
   - Baseline on `main`: 950 passed, **1 failed** (`test_interpret_document_promotes_metrics`), 2 skipped.
   - Branch result: **1012 passed, 0 failed, 1 skipped** — the pre-existing failure is gone.
   - Commit `8ad3e97` (the `verified_by_user` gate fix) implicitly heals this test.
   - This is a **positive side-effect** but should be noted: the test that was previously failing is now passing because `interpret_document()` was fixed. PTH should confirm whether the old test expectations were stale vs whether the new behavior is intended.
   - Net test delta: +62 tests, -1 failure = clean improvement.

---

## NOTES

### Minor / Non-Blocking

3. **`raw = next(...)` lookup in `lab.py` line 198:** The lookup `v.test_name == b.raw_name` is correct because `RawLabValue.test_name` stores the canonical name (e.g. `"ast"`) and `InterpretedBiomarker.raw_name` stores the same canonical (traced through `interpret_value()`). Verified by code inspection. Not a bug.

4. **Cortisol test value 2.50 nmol/L will trigger `requires_review=True`** at clinical layer because it is below the reference low (138 nmol/L). This is correct medical behavior. The fixture fixture comment says "best-effort" — this is appropriate.

5. **`_get_full_text()` ordering is critical:** The report documents why top-level `content` is placed first (hospital header must fall within line 30 for `detect_hospital()`). This ordering is fragile if the Azure DI response structure changes (e.g., no top-level `content` key). Low probability but worth a defensive check in `_get_full_text()`.

6. **`hospital_id` parameter signature on `clean_test_name()`** is `# noqa: ARG001` — intentionally unused but reserved for future per-provider overrides. This is clean design. No issue.

7. **Skipped test count differs from report:** Report says "1 skipped" on branch, observed "1 skipped" (`test_migrations.py` — TimescaleDB infrastructure dependency). Consistent.

8. **`"Cobas e411"` (Elecsys immunoassay) IS stripped by the generic `Cobas\s+[A-Za-z0-9]+` pattern** (tested: `TSH (Cobas e411)` → `TSH`). Good coverage.

---

## CHECKLIST RESULTS

| Check | Status | Detail |
|-------|--------|--------|
| `clean_test_name()` strips `(Cobas C502)`, `(Cobas Pro)`, `(C702)` | **CORRECT** | All 8 test cases verified live |
| `display_test_name` used for alias matching | **CONFIRMED** | `map_table_rows_to_raw_values()` uses `row.display_test_name` exclusively |
| `price`/`note`/`device`/`procedure` column roles | **CORRECT** | All 4 roles in `_NON_VALUE_ROLES`; safety fallback covers all |
| `hospital_id` passed through full pipeline | **THREADED** | `extract_and_map()` → `extract_table_rows(hospital_id=)` → `map_table_rows_to_raw_values(hospital_id=)` |
| Unknown provider gate: `requires_review=True`, confidence ≤ 0.5 | **EFFECTIVE** | Code confirmed + 5 dedicated tests pass |
| `interpret_document()` `verified_by_user` gate | **CORRECT** | Mock path trusted; real OCR gated on suspect/requires_review/confidence/needs_verification |
| Vinmec golden fixture | **16/16** | `test_golden_fixture_per_biomarker_vinmec` — 16 parametrized tests all pass, `original_value` + `original_unit` verified |
| Medlatec golden fixture | **11/11** | `test_golden_fixture_per_biomarker_medlatec` — 11 parametrized tests all pass, `original_value` + `original_unit` verified |
| `502` never in any result | **CONFIRMED** | `test_cobas_c502_inline_never_becomes_result_502` passes; live check shows no 502 in values |
| All prior tests still green | **CONFIRMED** | Main: 950 passed / 1 failed. Branch: 1012 passed / 0 failed / 1 skipped (infra) |

---

## DETAILED FINDINGS

### `clean_test_name()` — CORRECT
- Patterns 1–5 cover Cobas (with letter-prefix), C-series, QX-series, AU-series, Sysmex.
- Pattern 6 strips trailing `*` (abnormal flag).
- `"ALT (GPT)"` correctly preserved — parenthesized abbreviation, not a machine model.
- `"Glucose (máu)"` sample-type preserved — `(máu)` does not match any strip pattern.
- **Gap:** `"(Cobas C 502)"` with space is not stripped — documented P1 above.

### `display_test_name` alias match — CONFIRMED
- `OcrTableRow.display_test_name` populated at extraction time via `clean_test_name()`.
- `map_table_rows_to_raw_values()` calls `_strip_accents_lower(row.display_test_name)` (not `original_test_name`).
- `raw_test_name` on `RawLabValue` carries `original_test_name` (full as-printed), preserving audit trail.

### Column roles — CORRECT
- `_COL_ROLE_KEYWORDS` extended with `price`, `note`, `procedure`, `device`.
- `_NON_VALUE_ROLES = frozenset({"method", "price", "note", "procedure", "device", "stt"})`.
- Safety fallback in `_detect_column_roles()` now guards against ALL non-value roles (was previously method-only).
- Live test: `test_price_column_never_result` and `test_thiet_bi_column_never_becomes_result` both pass.

### `hospital_id` pipeline — THREADED
- `extract_and_map()` → `_get_full_text()` → `_detect_hospital()` → `extract_table_rows(hospital_id=hospital_id)` → `map_table_rows_to_raw_values(table_rows, ocr_conf=ocr_conf, hospital_id=hospital_id)`.
- Full chain confirmed in diff and tests.

### Unknown provider gate — EFFECTIVE
- When `hospital_id is None`: `overall = min(overall, 0.5)`, `requires_review = True`.
- `5` dedicated tests in `TestUnknownProviderGate` — all pass.
- `verified_by_user=False` on resulting `LabResult` rows → `promote_lab_rows_to_metrics()` receives empty list for unknown provider OCR.

### `interpret_document()` gate — CORRECT
- `is_mock_path` correctly checks `storage_key.startswith("manual:")` OR `ocr_mode == "mock"`.
- `auto_save_blocked` is `False` (trusted) for mock path; requires all 4 conditions to be False for real OCR.
- `verified_by_user=not auto_save_blocked` — clean inversion.
- `verified_rows = [r for r in new_rows if r.verified_by_user]` before promotion.
- The pre-existing `test_interpret_document_promotes_metrics` failure on `main` is now fixed by this commit. This is net-positive.

### Test results
- **Branch:** 1012 passed, 0 failed, 1 skipped (TimescaleDB infra)
- **Main baseline:** 950 passed, 1 failed (`test_interpret_document_promotes_metrics`), 2 skipped
- **New tests added:** 62 (61 new + 1 display_test_name fixture update)
- **Ruff:** Not re-run in this review session; report states "all checks passed"

---

## RECOMMENDATION

**APPROVE WITH NOTES — merge after completing:**

1. **[Required before merge]** Validate against 2–3 real Medlatec lab PDFs (not just mocks) to confirm `clean_test_name()` handles the actual spacing in production reports. Pay specific attention to whether `"Cobas C 502"` (with space) appears in real documents.

2. **[Required before merge]** If space-variant confirmed in real PDFs, widen pattern:
   ```python
   re.compile(r"\(\s*Cobas\s+[A-Za-z]+\s*[0-9]+\s*\)", re.IGNORECASE)
   ```
   This would match both `C502` and `C 502`.

3. **[Recommended]** Add a regression test with `"Glucose (máu) (Cobas C 502)"` (space variant) to `TestTestNameCleaner` — regardless of whether the pattern is widened, the test documents the known gap.

4. **[Inform PTH]** Commit `8ad3e97` heals the pre-existing `test_interpret_document_promotes_metrics` failure. Confirm this is intentional behavior (it is, based on code review) before closing out that test as resolved.

5. **[Low priority / separate PR]** `_get_full_text()` assumes `analyze_result["content"]` exists. A defensive `or ""` guard is already present (`if analyze_result.get("content")`), so this is fine. No action needed now.

---

*Review performed on: 2026-06-26. Branch HEAD: `8ad3e97`. Tests run locally on Python 3.11.15.*
