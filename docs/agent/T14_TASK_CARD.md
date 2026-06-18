# T14 Task Card — Lab Pipeline End-to-End Flow Tests

**TASK_ID:** T14  
**LABEL:** Lab Pipeline E2E Flow Tests — register → process → status → interpret  
**Branch:** `feature/t14-lab-pipeline-e2e-tests`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

`tests/test_lab_pipeline.py` has 10 unit tests for the pipeline service layer. `tests/api/test_lab_api.py` has 15 tests for RBAC only. There are NO API-level tests for the full flow:

```
POST /patients/{id}/lab-documents (register)
→ POST /lab-documents/{id}/process (enqueue)
→ GET  /lab-documents/{id} (status check)
→ POST /lab-documents/{id}/interpret (interpret)
```

This sprint adds `tests/api/test_lab_pipeline_e2e_api.py` covering the complete flow at the HTTP layer.

---

## Scope

### ALLOWED_FILES

- `backend/tests/api/test_lab_pipeline_e2e_api.py` — NEW: E2E tests
- `docs/agent/T14_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- Any production code (this is a pure test sprint)
- Existing tests

---

## Test Requirements (minimum 14 tests)

### Fixtures needed:
- `patient_setup` (patient user + patient_profile + headers)
- `doctor_setup` (doctor user + headers + consent for patient)
- `admin_setup` (admin user + headers)

### Full Flow Tests:
1. `test_register_document_as_patient` → 201, returns `LabDocumentOut` with `id`
2. `test_register_document_as_doctor` → 201 (with consent)
3. `test_register_document_ai_service_blocked` → 403
4. `test_enqueue_document_returns_202` → 202, `enqueued=True`
5. `test_enqueue_idempotent` → 202, second call `enqueued=False`
6. `test_document_status_after_enqueue` → 200, `status="uploaded"` or `"ocr_pending"`
7. `test_interpret_document_returns_biomarkers` → 200, `biomarkers` list not empty
8. `test_interpret_document_ai_service_blocked` → 403
9. `test_full_pipeline_flow` — register → enqueue → status → interpret in sequence, verify state transitions

### Ownership / RBAC Tests:
10. `test_patient_cannot_process_another_patients_document` → 403
11. `test_patient_cannot_read_another_patients_document_status` → 403
12. `test_clinic_admin_can_read_document_status` → 200 (with consent)
13. `test_unauthenticated_cannot_register_document` → 401

### Error / Edge Cases:
14. `test_process_nonexistent_document` → 404
15. `test_interpret_not_found` → 404

---

## Acceptance Criteria

- [ ] 15 new tests all pass
- [ ] Full pipeline flow (register → enqueue → status → interpret) verified at HTTP layer
- [ ] RBAC for each endpoint verified
- [ ] Consent fixture properly sets up `lab` scope access for doctor
- [ ] Worker mock/stub used to avoid real OCR calls in tests (check how `tests/test_lab_pipeline.py` does it)
- [ ] Zero regressions (300 baseline → 315+ total)
- [ ] Ruff clean

---

## Notes

- Check how existing `tests/test_lab_pipeline.py` and `tests/conftest.py` handle the worker — they use `worker.drain()` or mock OCR. Follow the same pattern.
- `interpret_document` may fail if OCR hasn't run; it might fall back to a mock interpreter. Check `app/services/lab.py` for the interpret logic.
- `LabDocumentCreate` payload: `{"storage_key": "s3://bucket/key.pdf", "file_type": "pdf", "lab_name": "Test Lab"}`

---

## Validation Commands

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
ruff check .
pytest tests/ --tb=short
```

---

## Required Final Status

```
READY FOR CODEX REVIEW
```

---

*Task Card issued: 2026-06-18 16:10 GMT+7 | Coordinator: OpenClaw*
