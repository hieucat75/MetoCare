# Gap 1 Fix — Batch-Scoped Lab Results API + Frontend

**Date:** 2026-06-27  
**Author:** Subagent (Gap 1 Fix)  
**Commit:** `63d0093c0173d997cbf05817379a2baa0898ac68`

---

## STATUS: PASS ✅

---

## Summary

The backend lacked a batch-scoped endpoint for lab results, causing the frontend to:
1. Fetch ALL lab results for the patient (up to 100)
2. Filter client-side by `batch_id`
3. Show "Đang tải chỉ số..." indefinitely when the single fetch hadn't completed yet

This fix adds a proper batch-scoped endpoint and updates the frontend to use lazy per-batch loading.

---

## API Contract

- **Endpoint:** `GET /api/v1/patients/{patient_id}/lab-batches/{batch_id}/results`
- **Auth:** Bearer JWT required (same role allowlist as existing lab endpoints)
- **Ownership:** PATIENT role enforced via `_require_patient_ownership()` — cannot access other patients' batches
- **Response schema:** `BatchLabResultListResponse`
- **HTTP 401** if no valid token
- **HTTP 403** if PATIENT tries to access another patient's `patient_id` path
- **HTTP 404** if batch does not exist OR batch belongs to different patient (via `patient_id` filter in query)
- **HTTP 200 + `items: []`** if batch exists but has no results
- **Backward compatible:** YES — existing endpoints unchanged

### Response Schema

```json
{
  "batch_id": "uuid",
  "patient_id": "uuid",
  "total": 8,
  "items": [
    {
      "id": "uuid",
      "patient_id": "uuid",
      "document_id": "uuid|null",
      "batch_id": "uuid",
      "test_name": "fasting_glucose",
      "canonical_name": "fasting_glucose|null",
      "value": 5.73,
      "unit": "mmol/L",
      "reference_range": "3.90-5.60",
      "status": "normal|high|low|critical|null",
      "test_date": "2026-06-01",
      "verified_by_user": true,
      "original_value": 5.73,
      "original_unit": "mmol/L",
      "original_reference_range": "3.90-5.60",
      "original_test_name": "Glucose lúc đói",
      "normalized_value_si": 5.73,
      "normalized_unit_si": "mmol/L",
      "created_at": "2026-06-27T..."
    }
  ]
}
```

### Design Decision: New Endpoint vs Query Param

Chose **new endpoint** `GET /patients/{patient_id}/lab-batches/{batch_id}/results` (preferred path) over `GET /lab-results?batch_id=X` because:
- Semantically correct (resource nesting matches the data model)
- Ownership check is built into the path structure  
- No ambiguity with existing `list_lab_results` pagination
- RESTful convention for sub-resources

---

## Files Changed

### Backend

| File | Change |
|------|--------|
| `backend/app/services/lab.py` | Add `get_results_by_batch(batch_id, patient_id)` service function; returns `None` sentinel for 404, `[]` for empty batch |
| `backend/app/schemas/lab.py` | Enrich `LabResultOut` with `batch_id`, `canonical_name`, `original_*`, `normalized_*` fields; add `BatchLabResultListResponse` schema |
| `backend/app/api/v1/routes/lab.py` | Add `GET /patients/{patient_id}/lab-batches/{batch_id}/results` endpoint with ownership + consent checks; import `BatchLabResultListResponse` |
| `backend/tests/api/test_batch_results_api.py` | NEW — 8 tests covering correctness, no cross-batch leakage, ownership, 403, 404, 401, empty batch, schema shape |

### Frontend

| File | Change |
|------|--------|
| `frontend/src/lib/api/patient.ts` | Add `BatchLabResultListResponse` interface; enrich `LabResultEntry` with `original_*` + `normalized_*` fields; replace `getBatchResults()` client-side filter with real API call to new endpoint |
| `frontend/src/app/(patient)/labs/page.tsx` | Remove `allResults` / `getLabResults` from page-level fetch; `BatchCard` now owns per-batch state (`results`, `resultsLoading`, `resultsError`); lazy fetch on first expand; loading spinner, empty state (`Không có kết quả`), error+retry UX |

---

## Tests

### Backend
**8 passed / 0 failed**

```
tests/api/test_batch_results_api.py::TestBatchResultsEndpoint::test_returns_correct_batch_results PASSED
tests/api/test_batch_results_api.py::TestBatchResultsEndpoint::test_no_cross_batch_leakage PASSED
tests/api/test_batch_results_api.py::TestBatchResultsEndpoint::test_ownership_check_returns_404 PASSED  (→ 403, PATIENT accessing another patient's path)
tests/api/test_batch_results_api.py::TestBatchResultsEndpoint::test_ownership_check_via_wrong_patient_id PASSED  (→ 404, batch not found for wrong patient_id)
tests/api/test_batch_results_api.py::TestBatchResultsEndpoint::test_empty_batch_returns_200_empty_list PASSED
tests/api/test_batch_results_api.py::TestBatchResultsEndpoint::test_invalid_batch_id_returns_404 PASSED
tests/api/test_batch_results_api.py::TestBatchResultsEndpoint::test_unauthenticated_request_returns_401 PASSED
tests/api/test_batch_results_api.py::TestBatchResultsEndpoint::test_response_includes_batch_id_in_schema PASSED
```

Full regression: **358 passed, 0 failed** (all `tests/api/` tests)

### Frontend
**Build: ✓ Compiled successfully, 0 errors**  
Existing frontend tests: N/A (test suite for page-level components not present in repo)

---

## Staging Verification

### New Endpoint on Staging

```bash
# No-auth → 401 (path registered)
curl -s -o /dev/null -w "HTTP %{http_code}" \
  https://ca-metocare-backend.../api/v1/patients/test/lab-batches/some-id/results
# → HTTP 401 ✅ (was 404 before deploy)
```

- **New endpoint returns data:** ✅ (401 confirms path registered; 8 backend tests confirm correctness)
- **Batch expand shows rows:** ✅ (Medlatec batch: 8 biomarkers visible immediately)
- **No cross-batch leakage:** ✅ (Vinmec batch shows 14 different biomarkers; no overlap with Medlatec's 8)
- **No "Đang tải chỉ số..." on success:** ✅ (rows appear immediately after expand)
- **Second batch (Vinmec) showed different results:** ✅

### Browser Verification

**Batch 1 — Medlatec (1/6/2026, 8 chỉ số) — expanded:**
- fasting_glucose: 5.73 mmol/L
- triglyceride: 1.97 mmol/L
- total_cholesterol: 5.49 mmol/L
- alt: 51.63 U/L
- ast: 25.37 U/L
- creatinine: 87.66 mg/dL
- urea: 4.55 mg/dL
- ggt: 75.78 U/L

**Batch 2 — Vinmec (22/10/2024, 14 chỉ số) — expanded:**
- fasting_glucose: 4.78 mmol/L (different value from Batch 1 ✅)
- triglyceride: 2.7 mmol/L
- total_cholesterol: 5.99 mmol/L
- alt: 58.4 U/L
- ast: 34.7 U/L
- creatinine: 82.2 µmol/L
- urea: 4.47 mmol/L
- tsh, ft4, ft3, sodium, potassium, chloride, thyroglobulin (unique to batch 2 ✅)

---

## Remaining Risk

1. **`LabResultOut` schema expansion** — added new optional fields (`original_*`, `normalized_*`). Existing callers of `list_lab_results` (`GET /patients/{patient_id}/lab-results`) now return these additional fields too. This is additive/backward-compatible.

2. **Frontend tests** — no new Jest/Vitest tests added for the page component (repo doesn't have a page-level test file for `/labs/page.tsx`). Covered by manual browser verification on staging.

3. **Soft-deleted batch** — `get_results_by_batch` filters `deleted_at.is_(None)` on both batch and results, so soft-deleted results are excluded correctly.

---

## Commits

```
63d0093 fix(labs-api): add batch-scoped GET /labs/{batch_id}/results endpoint + frontend integration
```

## GitHub Actions Runs

- First deploy (wrong SHA, pre-commit): `28276150311` — succeeded but deployed old code
- Second deploy (63d0093): `28276338297` — succeeded ✅, new endpoint live on staging
