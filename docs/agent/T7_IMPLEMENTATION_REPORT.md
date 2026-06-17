# T7 Implementation Report — Lab API RBAC Hardening + API Tests

**TASK_ID:** T7  
**Branch:** `feature/t7-lab-api-rbac`  
**Implementer:** Antigravity (Claude Code subagent)  
**Date:** 2026-06-18 GMT+7  
**Status:** READY FOR CODEX REVIEW

---

## Summary

All 4 lab API routes have been migrated from bare `current_user_id` to `CurrentUser` + `require_roles`. Patient ownership enforcement and role-based blocking are now active at the route level. 15 API test cases were added covering the full RBAC matrix.

---

## Changes Made

### `backend/app/api/v1/routes/lab.py` (modified)

**Before:** All 4 routes used `requester_id: str = Depends(current_user_id)` — no role check whatsoever.

**After:**
- Replaced `current_user_id` import with `CurrentUser`, `require_roles`
- Added `_require_patient_ownership()` helper function:
  - INTERNAL_ADMIN + SUPER_ADMIN: bypass (can access any patient's documents)
  - PATIENT: verifies `patient_profile.user_id == user.id`; raises HTTP 403 if mismatch
  - DOCTOR: passes through; consent gate in service layer handles authorization
- Applied `require_roles(...)` at route level for all 4 endpoints:

| Endpoint | Allowed Roles |
|---|---|
| `POST /patients/{id}/lab-documents` | PATIENT, DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN |
| `POST /lab-documents/{id}/process` | PATIENT, DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN |
| `GET /lab-documents/{id}` | PATIENT, DOCTOR, **CLINIC_ADMIN**, INTERNAL_ADMIN, SUPER_ADMIN |
| `POST /lab-documents/{id}/interpret` | PATIENT, DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN |

- AI_SERVICE is NOT in any allowed set → automatic 403 from `require_roles`
- CLINIC_ADMIN added to GET (read-only status) per task card requirement
- Consent gate calls in `enqueue_document` and `document_status` preserved
- Service layer calls pass `user.id` as `requester_id`

### `backend/tests/api/test_lab_api.py` (new file, 394 lines)

15 test cases covering all RBAC scenarios:

**Upload (POST /patients/{id}/lab-documents):**
- T7-01: `test_patient_uploads_own_lab_document` → 201 ✅
- T7-02: `test_doctor_uploads_lab_document_for_patient` → 201 ✅
- T7-03: `test_admin_uploads_lab_document` → 201 ✅
- T7-04: `test_patient_cannot_upload_for_another_patient` → 403 ✅
- T7-05: `test_ai_service_cannot_upload_lab_document` → 403 ✅

**Process (POST /lab-documents/{id}/process):**
- T7-06: `test_patient_enqueues_own_document` → 202 ✅
- T7-07: `test_doctor_enqueues_document` → 202 ✅
- T7-08: `test_unauthenticated_cannot_enqueue` → 401 ✅

**Status (GET /lab-documents/{id}):**
- T7-09: `test_patient_reads_own_document_status` → 200 ✅
- T7-10: `test_patient_cannot_read_another_patients_document` → 403/404 ✅
- T7-11: `test_admin_reads_any_document` → 200 ✅

**Interpret (POST /lab-documents/{id}/interpret):**
- T7-12: `test_patient_interprets_own_document` → 200, has `biomarkers` ✅
- T7-13: `test_interpret_returns_patient_explanation` → 200, non-empty `patient_explanation` ✅
- T7-14: `test_doctor_interprets_document` → 200 ✅
- T7-15: `test_ai_service_cannot_interpret` → 403 ✅

---

## Test Results

```
236 passed, 1 skipped, 14 warnings in 5.42s
```

Baseline: 221. New tests add 15 → 236 total. Zero regressions.

---

## Acceptance Criteria Check

- [x] All 4 lab routes use `CurrentUser` (not bare `current_user_id`)
- [x] `require_roles` applied at route level for appropriate roles
- [x] Patient ownership enforced: patient cannot access other patient's documents
- [x] AI_SERVICE blocked from all lab routes (403)
- [x] Consent gate preserved in service layer (not removed)
- [x] Audit records preserved for upload + interpret actions
- [x] All 15 test cases pass
- [x] Zero existing tests broken (221 baseline → 236 total)
- [x] Ruff clean
- [x] `docs/agent/T7_IMPLEMENTATION_REPORT.md` written

---

## Design Decisions

1. **`_require_patient_ownership` at route layer, consent gate at service layer** — route layer handles role/ownership, service layer handles consent. This layered approach keeps concerns separated and matches T5/T6 patterns.

2. **CLINIC_ADMIN read-only** — Only added to `GET /lab-documents/{id}` (status read). Not added to upload/process/interpret per task card ("CLINIC_ADMIN read-only: may read status only (GET), not upload/interpret").

3. **Admin consent fixture in tests** — `INTERNAL_ADMIN` bypasses the route-level ownership check but still goes through `consent.require_access()` in the service layer. Tests explicitly grant a consent record for admin to satisfy the service layer gate (which only auto-passes for patient's own `user_id`).

4. **No changes to domain layer** — `lab_interpreter.py`, `lab_pipeline.py`, and `services/lab.py` were not modified. All changes are confined to the allowed files.

---

## Files Changed

```
M  backend/app/api/v1/routes/lab.py
A  backend/tests/api/test_lab_api.py
A  docs/agent/T7_IMPLEMENTATION_REPORT.md
```

---

## Validation Commands

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
ruff check .          # All checks passed!
pytest tests/ --tb=short  # 236 passed, 1 skipped in 5.42s
```

---

## Commit

```
feat(t7): lab API RBAC hardening + 15 API tests (7506fd0)
```

---

*Report generated: 2026-06-18 GMT+7 | Status: READY FOR CODEX REVIEW*
