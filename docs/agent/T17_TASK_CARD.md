# T17 Task Card — Admin API Tests + AI Sessions Full Coverage

**TASK_ID:** T17  
**LABEL:** Admin Routes API Tests + AI Sessions Full RBAC Coverage  
**Branch:** `feature/t17-admin-aisessions-tests`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

Two test gaps remain:

1. **Admin routes** (`/admin/audit-logs`, `/admin/unlock-account`) — zero API test file exists
2. **AI Sessions** (`/ai-sessions`) — 4 endpoints, only 6 tests (list + full RBAC missing)

---

## Scope

### ALLOWED_FILES

- `backend/tests/api/test_admin_api.py` — NEW (admin route tests)
- `backend/tests/api/test_ai_sessions_full.py` — NEW (AI sessions full coverage)
- `docs/agent/T17_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- Any production code (pure test sprint)
- Existing `tests/api/test_ai_sessions_api.py`

---

## Admin Route Tests (minimum 10 tests)

From `app/api/v1/routes/admin.py`:
- `GET /admin/audit-logs` — requires INTERNAL_ADMIN or SUPER_ADMIN + MFA
- `POST /admin/unlock-account` — requires INTERNAL_ADMIN or SUPER_ADMIN + MFA

**Note:** `require_mfa` dependency checks for MFA-verified token. In tests, admin tokens must have `mfa=True` in JWT payload to pass MFA gate.

Tests:
1. `test_admin_reads_audit_logs` → 200, list
2. `test_patient_cannot_read_audit_logs` → 403
3. `test_doctor_cannot_read_audit_logs` → 403
4. `test_unauthenticated_cannot_read_audit_logs` → 401
5. `test_audit_log_limit_param` → 200, respects limit query param
6. `test_admin_unlocks_account` → 200, `{"message": "account unlocked"}`
7. `test_patient_cannot_unlock_account` → 403
8. `test_doctor_cannot_unlock_account` → 403
9. `test_unlock_nonexistent_account_succeeds` → 200 (unlock is idempotent — no-op if not locked)
10. `test_unauthenticated_cannot_unlock_account` → 401

---

## AI Sessions Full Coverage Tests (minimum 10 tests)

From `app/api/v1/routes/ai_sessions.py`:
- `POST /ai-sessions` — create session (AI_SERVICE only)
- `GET /ai-sessions/{id}` — read one session
- `GET /ai-sessions` — list sessions
- `GET /ai-sessions/{id}/recommendations` — list recommendations

Tests (extending existing 6, do NOT duplicate):
1. `test_ai_service_creates_session` → 201
2. `test_patient_cannot_create_session` → 403 (only AI_SERVICE can create)
3. `test_doctor_cannot_create_session` → 403
4. `test_patient_reads_own_session` → 200
5. `test_patient_cannot_read_another_patients_session` → 403
6. `test_doctor_reads_patient_session_with_consent` → 200
7. `test_patient_lists_own_sessions` → 200, list
8. `test_doctor_lists_patient_sessions` → 200
9. `test_unauthenticated_cannot_read_session` → 401
10. `test_list_recommendations_empty` → 200, empty list

---

## Acceptance Criteria

- [ ] 10 admin tests pass
- [ ] 10 AI session tests pass
- [ ] MFA requirement on admin routes properly handled in test tokens
- [ ] AI_SERVICE-only create session enforced
- [ ] Zero regressions (359 baseline → 379+ total)
- [ ] Ruff clean

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

*Task Card issued: 2026-06-18 19:00 GMT+7 | Coordinator: OpenClaw*
