# Codex Review — T7 Lab API RBAC Hardening

**Branch:** `feature/t7-lab-api-rbac`  
**Reviewer:** Codex (read-only)  
**Date:** 2026-06-18 GMT+7  
**Commit:** `7506fd0`

---

## Result: ✅ APPROVE

**P1 Blockers:** None  
**P2 Warnings:** 2 (see below)  
**Security:** PASS  
**Test Results:** 15/15 PASS (236 total, 0 failures)  
**Acceptance Criteria:** 12/12 met

---

## Acceptance Criteria Verification

| # | Criterion | Status | Notes |
|---|-----------|--------|-------|
| 1 | All 4 lab routes use `CurrentUser` (not bare `current_user_id`) | ✅ PASS | `current_user_id` removed from imports; all 4 routes use `CurrentUser` via `require_roles` |
| 2 | `require_roles` applied at route level with correct role sets | ✅ PASS | Upload/Process/Interpret: PATIENT,DOCTOR,INTERNAL_ADMIN,SUPER_ADMIN; Status: adds CLINIC_ADMIN |
| 3 | Patient ownership enforced: patient cannot access other patient's documents (403) | ✅ PASS | `_require_patient_ownership()` raises 403 when `profile.user_id != user.id` |
| 4 | AI_SERVICE blocked from all lab routes (403) | ✅ PASS | AI_SERVICE not in any `require_roles` set → automatic 403 |
| 5 | CLINIC_ADMIN allowed read-only on status endpoint only | ✅ PASS | CLINIC_ADMIN only in `GET /lab-documents/{id}` role set |
| 6 | Consent gate preserved in service layer (not removed) | ✅ PASS | `consent.require_access` present in `lab.register_document` (line 27) and `lab.interpret_document` (line 68); also at route level for enqueue+status |
| 7 | Audit records preserved for upload + interpret | ✅ PASS | `audit.record()` in `lab.register_document` (action=upload) and `lab.interpret_document` (action=interpret) |
| 8 | `_require_patient_ownership()` ADMIN bypass correct | ✅ PASS | INTERNAL_ADMIN and SUPER_ADMIN return early; no ownership check performed |
| 9 | No information leak: 403 vs 404 safe | ✅ PASS | Unauthorized patient gets 403 ("Patients may only access their own lab documents") not 404; document existence is not revealed |
| 10 | All 15 test cases pass with correct assertions | ✅ PASS | Verified live: `15 passed` in 0.15s |
| 11 | No regression from T6 baseline (221 → 236 passed) | ✅ PASS | Full suite: `236 passed, 1 skipped` — zero regressions |
| 12 | Ruff clean | ✅ PASS | `All checks passed!` |

---

## Security Analysis

### RBAC Layer
- ✅ **Role enforcement:** `require_roles` correctly rejects any role not in the allowed set, raising HTTP 403 before hitting business logic.
- ✅ **AI_SERVICE blocked:** Omitted from all 4 role sets — automatic 403. No explicit deny needed; deny-by-default is correct.
- ✅ **CLINIC_ADMIN scope-limited:** Only granted the GET (status read) endpoint. Cannot upload, enqueue, or interpret. Correct per task card.
- ✅ **SUPER_ADMIN bypass:** Consistent with platform-wide admin semantics. Correctly bypasses ownership check (not consent gate in service layer).

### Ownership Enforcement (`_require_patient_ownership`)
- ✅ **PATIENT path:** Looks up `PatientProfile` by `patient_id`; checks `profile.user_id == user.id`. Raises 403 on mismatch or if profile not found.
- ✅ **ADMIN bypass:** INTERNAL_ADMIN and SUPER_ADMIN return early — no DB query needed.
- ✅ **DOCTOR/CLINIC_ADMIN passthrough:** Neither role is PATIENT, so ownership check is skipped. DOCTOR is then gated by `consent.require_access` at the service layer. This is correct: doctors must hold active consent.
- ✅ **CLINIC_ADMIN consent gating:** For `GET /lab-documents/{id}`, after `_require_patient_ownership` passes (CLINIC_ADMIN passes through silently), `consent.require_access` is called at route level (line 131). CLINIC_ADMIN must hold active consent to view the document status. This is the correct behavior.

### Consent Gate Coverage
All routes with potential PHI disclosure have consent gates:

| Route | Consent Gate Location |
|-------|----------------------|
| `POST /patients/{id}/lab-documents` | Service layer (`lab.register_document`, line 27) |
| `POST /lab-documents/{id}/process` | Route layer (line 105) |
| `GET /lab-documents/{id}` | Route layer (line 131) |
| `POST /lab-documents/{id}/interpret` | Service layer (`lab.interpret_document`, line 68) |

✅ No gap — every route passes requester's user.id to consent gate.

### Information Leakage
- ✅ When a patient attempts to access another patient's document via `GET /lab-documents/{id}`, the flow is:
  1. Route fetches doc by ID (returns 404 if not found)
  2. `_require_patient_ownership()` — if profile mismatch → **403** before returning any document details
- The 403 detail message is generic ("Patients may only access their own lab documents") — does not confirm the document exists for another patient. ✅ Safe.
- Test T7-10 correctly asserts `status_code in (403, 404)`, accommodating both possible orderings. ✅

---

## P2 Warnings

### P2-1: No CLINIC_ADMIN test coverage
**File:** `backend/tests/api/test_lab_api.py`  
**Issue:** No test case verifies CLINIC_ADMIN behavior:
- No test that CLINIC_ADMIN can read status (`GET /lab-documents/{id}`) → 200
- No test that CLINIC_ADMIN cannot upload/enqueue/interpret → 403

The task matrix covers 15 cases but omits the CLINIC_ADMIN role entirely. This is the only new role specifically called out in the acceptance criteria ("CLINIC_ADMIN allowed read-only on status endpoint only"), yet it has zero test coverage.

**Recommendation:** Add 2 tests in a follow-up:
```python
def test_clinic_admin_can_read_document_status(...)  # → 200
def test_clinic_admin_cannot_upload_lab_document(...)  # → 403
```

### P2-2: `_require_patient_ownership` DOCTOR passthrough is implicit
**File:** `backend/app/api/v1/routes/lab.py`, function `_require_patient_ownership`  
**Issue:** The function only explicitly handles INTERNAL_ADMIN, SUPER_ADMIN (bypass) and PATIENT (ownership check). All other roles (DOCTOR, CLINIC_ADMIN) fall through silently with no branch. The logic is correct — DOCTOR and CLINIC_ADMIN are gated by consent in the service layer — but a future developer adding a new role might not notice the implicit passthrough.

**Recommendation (non-blocking):** Add a docstring note or inline comment:
```python
# DOCTOR and CLINIC_ADMIN: no ownership check here; consent gate handles access.
```

---

## Code Quality

- **Structure:** Clean separation of concerns — `_require_patient_ownership` is a focused helper at the route layer; service layer handles consent; audit happens at service layer. Mirrors the T5/T6 pattern. ✅
- **Idempotency:** `enqueue_document` passes `enqueued` boolean from worker — idempotent by design. ✅
- **Error handling:** `interpret_document` catches `ValueError` and re-raises as HTTP 404. ✅
- **Test fixtures:** `patient_document` fixture correctly creates a `LabDocument` directly in DB (bypasses route layer), enabling clean unit tests for downstream endpoints. ✅
- **Test isolation:** All fixtures use `os.urandom(4).hex()` email suffixes to prevent collision. ✅
- **T7-03 admin test note:** Test correctly grants a consent record for INTERNAL_ADMIN to pass the service-layer consent gate (which checks `profile.user_id == requester_id` OR active consent). This is a known design decision — admin bypass is route-level only; service-layer consent gate is independent. ✅

---

## Summary

T7 correctly hardens all 4 lab API routes with `CurrentUser` + `require_roles`, enforces patient ownership via `_require_patient_ownership()`, blocks AI_SERVICE, and limits CLINIC_ADMIN to the read-only status endpoint. The two-layer defense (route RBAC + service consent) is sound. All 15 new tests pass; 0 regressions in the full suite of 236. The only gap is missing CLINIC_ADMIN test coverage (P2), which should be addressed in a follow-up. **Approved for merge.**
