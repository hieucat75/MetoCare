# Codex Review — T14 Lab Pipeline E2E Flow Tests

**Reviewer:** Codex (read-only subagent)  
**Branch:** `feature/t14-lab-pipeline-e2e-tests`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Reviewed:** 2026-06-18  
**Files reviewed:**
- `backend/tests/api/test_lab_pipeline_e2e_api.py`
- `docs/agent/T14_IMPLEMENTATION_REPORT.md`
- `backend/app/api/v1/routes/lab.py` (production route — cross-checked)
- `backend/tests/conftest.py` (cross-checked)
- `backend/app/services/lab_pipeline.py` (worker — cross-checked)
- `backend/app/services/consent.py` (consent service — cross-checked)

---

## Result: ✅ APPROVE

**P1 Blockers:** None  
**P2 Warnings:** 1 (minor coverage gap — see below)  
**Security:** PASS  
**Test Results:** 15/15 PASS (315 total, 1 skipped, 0 failures reported)  
**Acceptance Criteria:** 11/11 met

---

## Acceptance Criteria Verification

### AC1 — Full pipeline flow tested at HTTP layer ✅
`test_full_pipeline_flow` (T14-09) exercises all four stages in sequence:
`POST /patients/{id}/lab-documents` → `POST /lab-documents/{id}/process` →
`GET /lab-documents/{id}` → `POST /lab-documents/{id}/interpret`.
State transitions are explicitly asserted at each step.

### AC2 — Happy path status codes ✅
- `POST /patients/{id}/lab-documents` → **201** verified in T14-01, T14-02, T14-09
- `POST /lab-documents/{id}/process` → **202** verified in T14-04, T14-09
- `GET /lab-documents/{id}` → **200** verified in T14-06, T14-09
- `POST /lab-documents/{id}/interpret` → **200** verified in T14-07, T14-09

### AC3 — Idempotent enqueue ✅
`test_enqueue_idempotent` (T14-05): first call returns `enqueued=True`, second call returns
`enqueued=False`. Both calls assert 202.

### AC4 — AI_SERVICE blocked (403) on register + interpret ✅ (CRITICAL PHI)
- `test_register_document_ai_service_blocked` (T14-03): 403 on register
- `test_interpret_document_ai_service_blocked` (T14-08): 403 on interpret
- Cross-check: `require_roles()` on both routes does **not** include `UserRole.AI_SERVICE`,
  confirming the 403 is enforced at the FastAPI dependency level, not just asserted in tests.

### AC5 — Ownership: patient cannot process/read another patient's document ✅
- `test_patient_cannot_process_another_patients_document` (T14-10): 403 on process
- `test_patient_cannot_read_another_patients_document_status` (T14-11): 403 or 404 on GET
- Cross-check: `_require_patient_ownership()` in `lab.py` raises 403 when `profile.user_id != user.id`

### AC6 — CLINIC_ADMIN can read document status (200) ✅
`test_clinic_admin_can_read_document_status` (T14-12): grants lab consent to admin,
then asserts 200 on `GET /lab-documents/{id}`. Cross-check: `CLINIC_ADMIN` is listed
in `require_roles()` for the GET route.

### AC7 — Unauthenticated → 401 ✅
`test_unauthenticated_cannot_register_document` (T14-13): no Authorization header
→ 401 asserted.

### AC8 — 404 on nonexistent document_id for process + interpret ✅
- `test_process_nonexistent_document` (T14-14): 404 on process
- `test_interpret_not_found` (T14-15): 404 on interpret

### AC9 — Doctor consent with `lab` scope ✅
`test_register_document_as_doctor` (T14-02) calls `_grant_lab_consent()` with
`data_scope="lab"` before the doctor hits the register endpoint. The helper sets
`consent_type="lab_access"` and `data_scope="lab"` on the `Consent` model, which
`consent.has_access()` checks via `consent.is_active(now, scope, requester_id)`.
Consent is flushed and committed before the HTTP call.

**Note:** The enqueue endpoint (`process`) and GET status endpoint both call
`consent.require_access(...)`. For the patient's own document, the consent service
correctly bypasses the consent DB query (`profile.user_id == requester_id → True`),
so patient-only tests work without a consent record.

### AC10 — No real OCR calls; worker mock/drain used correctly ✅
`conftest.py` sets:
```
MCP_OCR_MODE=mock
MCP_AI_MODE=mock
MCP_OCR_WORKER_ENABLED=false
```
The `_reset_llm` fixture calls `get_worker().reset()` before every test, ensuring no
queue bleed between tests. The only test that calls `get_worker().drain()` is
`test_full_pipeline_flow` (T14-09), which is the one test that explicitly verifies
post-OCR state (`status == "interpreted"`). All other tests do not need to drain
because they check intermediate states (`ocr_pending`, `uploaded`) or mock responses.
No async OCR worker is running (background worker is disabled).

### AC11 — 15 tests pass, 0 regressions ✅
Reported: 315 passed, 1 skipped, 0 failed (baseline 300 → +15). No production code
was modified; the 1 skipped test is pre-existing.

---

## Findings

### ✅ Strengths

1. **Clean fixture isolation**: Each fixture uses `os.urandom(4).hex()` in email fields to
   prevent cross-test collisions. `db.commit()` is called after all relationships are wired,
   not just `flush()`.

2. **Worker pattern is correct**: `drain()` is called only in the one test that verifies
   post-OCR state. Other tests correctly do not drain, avoiding over-coupling to async behavior.

3. **Consent setup is robust**: `_grant_lab_consent()` sets `valid_from` 1 hour in the past
   and `valid_until` 24 hours in the future, eliminating any clock-edge failures.

4. **RBAC tested at route layer**: AI_SERVICE blocking is verified via the HTTP 403 response,
   confirmed to be enforced by `require_roles()` in the production route — not just a test
   assertion without production backing.

5. **`_register_doc()` helper**: Centralizes setup, keeps individual tests focused on the
   behavior under test.

6. **No dead imports**: All imports (`get_worker`, `Consent`, `Doctor`, etc.) are used.

### ⚠️ P2 Warnings

**W1 — Doctor enqueue/interpret consent not explicitly tested**  
T14-02 tests doctor _register_ with lab consent. However, no test exercises a doctor
calling `POST /lab-documents/{id}/process` or `POST /lab-documents/{id}/interpret` with
an active lab consent. The production route calls `consent.require_access()` on both.
While the consent helper and consent service are validated for the GET case (T14-12),
a doctor process/interpret test would give fuller coverage of the consent gate.
**Impact:** Low — consent service is exercised indirectly; this is a coverage gap, not
a correctness gap.

**W2 — T14-11 accepts 403 OR 404**  
`test_patient_cannot_read_another_patients_document_status` asserts `status_code in (403, 404)`.
This is pragmatic but slightly loose — the current production code returns 403 (ownership
check runs before 404). If the check order ever changes, a 404 could mask a security
regression. A comment documenting the expected code would improve clarity.
**Impact:** Informational — does not affect pass/fail logic today.

### 🔒 Security Assessment: PASS

- AI_SERVICE is blocked on both write-path endpoints (register, interpret) ✅
- Cross-patient ownership enforced at route layer, confirmed in production code ✅
- Consent gate verified for third-party (doctor, admin) access ✅
- Auth guard covers unauthenticated requests ✅
- No real patient data or PHI used; synthetic data only ✅
- Worker mock prevents any external OCR/AI calls ✅

---

## Summary

All 15 tests are well-structured, cover the full pipeline at the HTTP layer, and correctly
verify the critical RBAC/ownership/consent requirements. No P1 blockers found. Two minor
P2 observations (missing doctor process/interpret consent test; loose 403/404 assertion)
do not warrant blocking. The PHI protection surface (AI_SERVICE blocked, cross-patient
ownership, consent gates) is solid and validated against production route code.
**Approved to merge.**
