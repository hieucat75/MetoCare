## Gap 2 — Status Backfill Report

### STATUS: PASS ✅

**Date:** 2026-06-27
**Environment:** Azure Staging (Southeast Asia)
**Commit:** 820c414d209b9e14c8339478a81bca10a155259e

---

### Backfill Method
- **Script:** `backend/scripts/backfill_status.py` (idempotent, dry-run, batch-scoped)
- **Admin endpoint:** `POST /api/v1/admin/labs/reclassify` (INTERNAL_ADMIN / SUPER_ADMIN only) ✅ Added
- **Classify-on-read fallback:** YES — `get_results_by_batch()` computes status in-memory for display when `status=NULL` but `normalized_value_si` is set. No DB write.
- **Execution method:** Azure Container Apps Job (`caj-metocare-migrate`) with command override

---

### Records (Staging DB)
- **Total LabResult records processed:** ~291 (updated + skipped)
- **Updated:** 231
- **Skipped (null value or unsupported biomarker):** 60
- **Errors:** 0

Sample backfill log entries observed:
```
reclassify bb9fa628 (fasting_glucose): None → high  (value=140.0000)
reclassify 89309b0c (hba1c): None → high  (value=7.2000)
reclassify 7d1d6cde (triglyceride): None → high  (value=280.0000)
reclassify a462361f (fasting_glucose): None → high  (value=140.0000)
reclassify deef2713 (hba1c): None → high  (value=7.2000)
reclassify 527219f2 (fasting_glucose): None → high  (value=140.0000)
```
Idempotent updates (already had status, confirmed unchanged):
```
reclassify 59937e65 (fasting_glucose): high → high  (value=110.0000)
reclassify 9573106b (triglyceride): high → high  (value=220.0000)
reclassify 4b19eec7 (hdl): low → low  (value=38.0000)
```

---

### Files Changed
**Backend:**
- `backend/app/services/lab.py` — Added `reclassify_lab_results()` function + classify-on-read fallback in `get_results_by_batch()`
- `backend/app/api/v1/routes/lab.py` — Added `POST /api/v1/admin/labs/reclassify` endpoint
- `backend/scripts/backfill_status.py` — New CLI backfill script (created)
- `backend/tests/test_status_backfill.py` — New test suite (created)

---

### Tests
- **Total:** 17 / **Passed:** 17 / **Failed:** 0
- **Full suite regression:** 1054 passed, 0 failed
- Test cases covered:
  - Glucose 5.7 mmol/L → high ✅
  - Glucose 510 mg/dL → critical ✅
  - LDL 160 mg/dL → high ✅
  - HDL 35 mg/dL → low ✅
  - Triglyceride 502 mg/dL → critical ✅
  - Creatinine 0.9 mg/dL → normal ✅
  - Idempotency double-run (0 updates on second run) ✅
  - Original fields preserved (original_value, original_unit, original_test_name) ✅
  - Null value skipped, no crash ✅
  - Unsupported biomarker skipped, no crash ✅
  - Null canonical_name skipped ✅
  - Batch-scoped filter works correctly ✅
  - Dry-run: no DB writes ✅
  - Classify-on-read fallback works, no DB write ✅
  - Normalization from original_value + original_unit ✅

---

### Staging Verification (Browser)

**Medlatec batch (Jun 2026, 8 biomarkers):**
- ggt → **Cao** ✅
- alt → **Bình thường** ✅
- triglyceride → **Cao** ✅
- urea → **Thấp** ✅
- fasting_glucose (5.73 mmol/L) → **Cao** ✅
- total_cholesterol → **Cao** ✅
- ast → **Bình thường** ✅
- creatinine → **Nguy hiểm** (critical) ✅

**Vinmec batch (Oct 2024, 14 biomarkers):**
- triglyceride (2.7 mmol/L) → **Cao** ✅
- fasting_glucose (4.78 mmol/L) → **Bình thường** ✅
- tsh → **Bình thường** ✅
- creatinine → **Bình thường** ✅
- potassium → **Bình thường** ✅
- alt (58.4 U/L) → **Cao** ✅
- total_cholesterol → **Cao** ✅
- sodium → **Bình thường** ✅
- ft3 → **Bình thường** ✅
- thyroglobulin → **Thấp** ✅
- chloride → **Bình thường** ✅
- ft4 → **Bình thường** ✅
- urea → **Bình thường** ✅
- ast → **Bình thường** ✅

**Result:** No "Chưa rõ" badges for supported biomarkers with valid values ✅

---

### Backfill Method Details

**Classification logic:**
1. Skip if `canonical_name` is null → counted as skipped
2. Skip if `original_value`, `value`, and `normalized_value_si` are all null → counted as skipped
3. If `normalized_value_si` is null → compute from `original_value + original_unit` using `normalize_value_to_si()`
4. Classify using `classify_value(canonical_name, normalized_value_si)` from `lab_interpreter`
5. Skip if `classify_value` returns `UNKNOWN` (unsupported biomarker)
6. Update `status`, optionally fill `normalized_value_si` + `normalized_unit_si` if missing
7. NEVER touch: `original_value`, `original_unit`, `original_test_name`, `original_reference_range`
8. Commit once after all updates (not per-record)

**Classify-on-read fallback:**
- In `get_results_by_batch()`: if `result.status is None` and `result.normalized_value_si is not None` and `result.canonical_name` is set → compute status using `classify_value()` in memory
- Does NOT commit to DB (read-only display fix for records not yet backfilled)

---

### Original Fields Preserved
- `original_value`: ✅ Never touched
- `original_unit`: ✅ Never touched
- `original_test_name`: ✅ Never touched
- `original_reference_range`: ✅ Never touched
- `ocr_confidence`: ✅ Never touched

---

### Idempotency Verified
- Backfill ran once with 231 updates, 60 skipped, 0 errors
- Second run (if run again) will show 0 updates for already-classified records (same value → same status → skipped)
- Test `test_idempotent_double_run` confirms this behavior: ✅

---

### Deploy
- GitHub Actions: `azure-staging.yml` run #28277566396 — SUCCESS in 5m5s
- All Alembic migrations passed
- Health gate passed
- Backfill run via Container Apps Job execution `caj-metocare-migrate-pgce5qv`

---

### Remaining Risk
1. **Records with null `normalized_value_si` and `original_unit=null`:** These are classified using the canonical unit assumption. If the original unit was non-canonical and not stored, the classification may be off. These are 60 "skipped" records.
2. **Admin API endpoint needs MFA:** The `POST /api/v1/admin/labs/reclassify` endpoint requires MFA-enrolled admin account. Currently, admin accounts must be seeded via `seed_admin.py` on the staging DB before this endpoint can be used directly.
3. **Log Analytics ingestion lag:** Backfill logs appear 2-5 minutes after execution.

---

### Commits
- `820c414d` — "fix(labs): backfill status reclassification + classify-on-read fallback"
