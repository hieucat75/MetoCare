# T7 Task Card — Lab API RBAC Hardening + API Tests

**TASK_ID:** T7  
**LABEL:** Lab API RBAC Hardening + API-Level Tests  
**Branch:** `feature/t7-lab-api-rbac`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

Harden the existing Lab API routes with proper role-based access control (RBAC) and add comprehensive API-level tests. The domain code (`lab_interpreter`, `lab_pipeline`) and service layer (`lab.py`) already exist and are tested at unit level. This sprint wire the routes to use `require_roles` + `CurrentUser` (replacing bare `current_user_id`), enforce per-role access policies, and add `tests/api/test_lab_api.py`.

---

## Scope

### ALLOWED_FILES

- `backend/app/api/v1/routes/lab.py` — RBAC + CurrentUser migration
- `backend/app/services/lab.py` — accept `user: CurrentUser` pattern if needed for audit
- `backend/tests/api/test_lab_api.py` — NEW file, all API tests
- `docs/agent/T7_IMPLEMENTATION_REPORT.md` — NEW, final report

### DO NOT TOUCH

- `backend/app/domain/lab_interpreter.py`
- `backend/app/domain/triage.py`
- `backend/app/services/lab_pipeline.py`
- Any existing passing tests
- Any migration files
- `backend/app/models/`
- Auth / consent / RBAC core

---

## RBAC Requirements

### Current state (broken):
All 4 lab routes use `current_user_id` (bare string — no role check).

### Required RBAC per endpoint:

| Endpoint | Allowed Roles |
|----------|---------------|
| `POST /patients/{patient_id}/lab-documents` | PATIENT (own), DOCTOR (assigned/clinic), INTERNAL_ADMIN, SUPER_ADMIN |
| `POST /lab-documents/{id}/process` | PATIENT (own), DOCTOR (assigned/clinic), INTERNAL_ADMIN, SUPER_ADMIN |
| `GET /lab-documents/{id}` | PATIENT (own), DOCTOR (assigned/clinic), INTERNAL_ADMIN, SUPER_ADMIN |
| `POST /lab-documents/{id}/interpret` | PATIENT (own), DOCTOR (assigned/clinic), INTERNAL_ADMIN, SUPER_ADMIN |

**AI_SERVICE must NOT access lab documents directly.**
**CLINIC_ADMIN read-only: may read status only (GET), not upload/interpret.**

### Access logic (follow T5/T6 patterns):
- Use `CurrentUser` from `app.api.deps`
- Use `require_roles(UserRole.PATIENT, UserRole.DOCTOR, UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)` at route level
- For PATIENT: verify `patient_profile.user_id == user.id` (patient can only access own documents)
- For DOCTOR: check via existing consent gate in `lab.service` — `consent.require_access()` already handles this
- For INTERNAL_ADMIN/SUPER_ADMIN: bypass patient ownership check (admin can access any)
- Consent gate already in service layer: preserve it, do not remove

### Error responses:
- 403 when role not allowed
- 403 when patient tries to access another patient's document
- 404 when document not found (do not leak existence to unauthorized users)

---

## Test Requirements

Create `backend/tests/api/test_lab_api.py` with these test cases:

### Setup fixtures (follow T5/T6 conftest pattern):
- `patient_setup` — creates patient user + profile + JWT token
- `doctor_setup` — creates doctor user + doctor record + clinic + JWT token
- `admin_setup` — creates INTERNAL_ADMIN user + JWT token
- `ai_service_setup` — creates AI_SERVICE user + JWT token

### Test cases (minimum):

**Upload (POST /patients/{id}/lab-documents):**
1. `test_patient_uploads_own_lab_document` → 201
2. `test_doctor_uploads_lab_document_for_patient` → 201
3. `test_admin_uploads_lab_document` → 201
4. `test_patient_cannot_upload_for_another_patient` → 403
5. `test_ai_service_cannot_upload_lab_document` → 403

**Process (POST /lab-documents/{id}/process):**
6. `test_patient_enqueues_own_document` → 202
7. `test_doctor_enqueues_document` → 202
8. `test_unauthenticated_cannot_enqueue` → 401

**Status (GET /lab-documents/{id}):**
9. `test_patient_reads_own_document_status` → 200
10. `test_patient_cannot_read_another_patients_document` → 403 or 404
11. `test_admin_reads_any_document` → 200

**Interpret (POST /lab-documents/{id}/interpret):**
12. `test_patient_interprets_own_document` → 200, has `biomarkers` field
13. `test_interpret_returns_patient_explanation` → 200, `patient_explanation` not empty
14. `test_doctor_interprets_document` → 200
15. `test_ai_service_cannot_interpret` → 403

### Notes:
- Use `MCP_OCR_MODE=mock` (default) — no real OCR needed
- Follow conftest.py fixture patterns from existing `tests/api/` files
- Consent: for tests where consent is needed, add a `Consent` row as fixture (follow `test_doctor_review_api.py` pattern)

---

## Acceptance Criteria

- [ ] All 4 lab routes use `CurrentUser` (not bare `current_user_id`)
- [ ] `require_roles` applied at route level for appropriate roles
- [ ] Patient ownership enforced: patient cannot access other patient's documents
- [ ] AI_SERVICE blocked from all lab routes (403)
- [ ] Consent gate preserved in service layer (not removed)
- [ ] Audit records preserved for upload + interpret actions
- [ ] All 15 test cases pass
- [ ] Zero existing tests broken (221 baseline → 236+ total)
- [ ] Ruff clean
- [ ] `docs/agent/T7_IMPLEMENTATION_REPORT.md` written

---

## Validation Commands

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
ruff check .
pytest tests/ --tb=short
```

Report: `N passed, N skipped, N warnings in Xs`

---

## Required Final Status

```
READY FOR CODEX REVIEW
```

Do NOT say: APPROVED / MERGE READY / SAFE TO MERGE

---

## Medical Safety Reminders

- Lab interpretation results must NEVER be modified — `lab_interpreter.py` is read-only from this sprint
- Do not add any LLM calls to the lab pipeline in this sprint
- `interpret` output must include `patient_explanation` disclaimer (already in domain layer — do not strip it)
- Consent gate in `lab.service` is a legal requirement — do not remove or bypass

---

*Task Card issued: 2026-06-18 05:03 GMT+7 | Coordinator: OpenClaw*
