# Auto-classify at Creation — Report

## STATUS: PASS

**Date:** 2026-06-27  
**Commit:** `014b1363341e08365de590f955bbf5deb351be4d`  
**Staging Deploy:** GitHub Actions run #28287188005 — ✅ 5m6s

---

### Creation Paths Covered

| Path | Covered | Notes |
|------|---------|-------|
| Manual entry (`create_manual_entry`) | ✅ | `normalize_and_classify()` called before DB save; sets `normalized_value_si`, `normalized_unit_si`, `status` |
| OCR confirm (`interpret_document`) | ✅ | Same helper wired in; falls back to interpreter status if canonical classification unavailable |
| Background OCR pipeline (`lab_pipeline.process_document`) | ✅ | Same helper wired in; `normalize_and_classify` imported from `lab.py` |
| File upload/import | N/A | No separate file-import path exists; upload goes through OCR pipeline covered above |
| Hospital link sync | N/A | Not implemented in codebase (no hospital sync service found) |

---

### Update Path (user correction)

- Reclassify on correction: ✅ — `correct_lab_result()` service + `PATCH /patients/{id}/lab-results/{id}/correct` endpoint added
- Correction history/provenance: ✅ — appends to `correction_history_json` before overwriting value
- Provenance fields saved: `old_value`, `old_unit`, `timestamp`, `corrected_by: "user"`

---

### Files Changed

| File | Change |
|------|--------|
| `backend/app/services/lab.py` | Added `normalize_and_classify()` helper; wired into `create_manual_entry()`; wired into `interpret_document()`; added `correct_lab_result()` service |
| `backend/app/services/lab_pipeline.py` | Wired `normalize_and_classify()` into `process_document()` OCR pipeline |
| `backend/app/api/v1/routes/lab.py` | Added `PATCH /patients/{patient_id}/lab-results/{result_id}/correct` endpoint; added `LabResultCorrectionIn` import |
| `backend/app/schemas/lab.py` | Added `LabResultCorrectionIn` schema |
| `backend/tests/test_auto_classify.py` | New test file — 27 tests |

---

### normalize_and_classify() Helper — Design

```python
def normalize_and_classify(canonical_name: str | None, value, unit: str) -> dict:
    # Returns:
    #   {} if canonical_name is None or value is None
    #   {"normalized_value_si": ..., "normalized_unit_si": ..., "status": None} for unknown biomarkers
    #   {"normalized_value_si": ..., "normalized_unit_si": ..., "status": "high"|"normal"|...} for known
```

Key properties:
- **NO OCR confidence** in classification logic
- **NEVER modifies** `original_value`/`original_unit`
- Returns `status=None` for unsupported biomarkers (not `"unknown"`)
- Handles null value gracefully (empty dict)

---

### Tests

- **New test file:** `backend/tests/test_auto_classify.py`
- **Total new tests:** 27 / **Passed:** 27 / **Failed:** 0
- **Full regression suite:** 1440 passed / 1 skipped (pre-existing) / 0 failed

Test coverage:
- `TestNormalizeAndClassify` (7 tests) — unit tests for the helper
- `TestManualEntryAutoClassify` (9 tests) — creation path; glucose mmol/L, mg/dL; LDL; TG; creatinine; normal; unsupported; null value
- `TestUserCorrectionReclassify` (4 tests) — reclassify on correction; provenance; normalized value update; not-found error
- `TestOCRPathAutoClassify` (1 test) — interpret_document path
- `TestBackfillRegression` (4 tests) — reclassify backfill still works; classify-on-read fallback preserved

---

### Staging Smoke Test

Backend: `https://ca-metocare-backend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io`

| Test | Result | Details |
|------|--------|---------|
| Glucose 5.7 mmol/L → classified at creation | ✅ | `status=high`, `normalized_value_si=102.7026 mg/dL`, `original_value=5.7`, `original_unit=mmol/L` |
| LDL 4.5 mmol/L → classified at creation | ✅ | `status=high`, `normalized_value_si=174.015 mg/dL` |
| TG 502 mg/dL → classified at creation | ✅ | `status=critical`, `normalized_value_si=502.0 mg/dL` |
| No backfill required for new records | ✅ | All 3 records returned `status != null` immediately from API without running backfill |
| Health check | ✅ | `/health` → `{"status":"ok"}` |
| Frontend | ✅ | Dashboard accessible at staging URL |

**Staging deploy:** All steps passed — Alembic migration ✅, backend deploy ✅, frontend deploy ✅, health gate ✅.

---

### Architecture Notes

- `classify-on-read fallback` in `get_results_by_batch()` is preserved as a safety net for legacy rows
- `reclassify_lab_results()` backfill is preserved (handles rows created before this change)
- No changes to `clinical_rules.py` or `lab_interpreter.py` classification logic
- No changes to clinical thresholds or conversion factors
- `lab_pipeline` imports `normalize_and_classify` from `lab.py` at module level (no circular import — `lab.py` does not import `lab_pipeline`)

---

### Remaining Risk

| Risk | Severity | Mitigation |
|------|----------|------------|
| OCR pipeline path (`interpret_document`) uses interpreter status as fallback when `normalize_and_classify` returns `status=None` for unknown biomarkers. Unknown biomarkers will get `status=None`. | Low | Correct behavior; classify-on-read fallback acts as extra safety net |
| `correct_lab_result()` updates `value`/`unit` fields to canonical normalized values — if a user corrects to mmol/L, the `value` field becomes mg/dL. | Low | `original_value`/`original_unit` preserve the user's input; `value`/`unit` are the canonical fields used for clinical logic |
| Hospital link sync: if implemented in future, must call `normalize_and_classify()` at creation | N/A now | Note for future implementation |

---

### Commits

- `014b1363` — `feat(labs): auto-classify LabResult at creation and correction time`
