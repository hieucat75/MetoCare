# Codex Review — T17: Admin API Tests + AI Sessions Full Coverage

**Branch:** `feature/t17-admin-aisessions-tests`
**Repo:** `/Users/pth/Developer/Metocare`
**Reviewer:** Codex (read-only)
**Date:** 2026-06-18

---

**Result:** ✅ APPROVE

**P1 Blockers:** None

**P2 Warnings:**
- `doctor_user` fixture in `test_admin_api.py` mints token with `mfa=True` — this is cosmetically odd (doctors don't normally satisfy `require_mfa` in production flows), but it only matters for the 403 tests where MFA is irrelevant to the outcome (the role check fires first). No correctness impact.
- `test_doctor_reads_patient_session_with_consent` — test name says "with consent" but the implementation of `_check_session_read_access` allows any DOCTOR unconditionally (no consent check on reads). Name is slightly misleading. Not a test defect; the comment in `ai_sessions.py` acknowledges this is intentional simplification. Low severity.

**Security:** PASS

**Test Results:** 380/380 PASS (+ 1 skipped, pre-existing)

**Acceptance Criteria:** 12/12 met

---

## Detailed Findings

### AC1 — `GET /admin/audit-logs` role coverage ✅

- `test_admin_reads_audit_logs` → INTERNAL_ADMIN + MFA → 200 ✅
- `test_super_admin_reads_audit_logs` → SUPER_ADMIN + MFA → 200 ✅
- `test_patient_cannot_read_audit_logs` → PATIENT → 403 ✅
- `test_doctor_cannot_read_audit_logs` → DOCTOR → 403 ✅
- `test_unauthenticated_cannot_read_audit_logs` → no token → 401 ✅

Route `admin.py` uses `Depends(_admin_only)` which calls `require_roles(UserRole.INTERNAL_ADMIN, UserRole.SUPER_ADMIN)`. Patient/Doctor role strings `"patient"` / `"doctor"` are not in `allowed`, so 403 is deterministically produced by `require_roles`, not by MFA or any other check. Correct.

### AC2 — `POST /admin/unlock-account` role coverage ✅

- `test_admin_unlocks_account` → INTERNAL_ADMIN + MFA → 200, `message == "account unlocked"` ✅
- `test_patient_cannot_unlock_account` → PATIENT → 403 ✅
- `test_doctor_cannot_unlock_account` → DOCTOR → 403 ✅
- `test_unauthenticated_cannot_unlock_account` → no token → 401 ✅

### AC3 — MFA token construction ✅ (Priority Focus item — verified)

`require_mfa` in `deps.py` checks:
```python
def require_mfa(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.mfa:
        raise HTTPException(status_code=403, detail="MFA verification required...")
    return user
```

`current_user` populates `CurrentUser.mfa` directly from `payload.get("mfa", False)`.

`create_access_token` places `mfa=mfa` into the JWT payload unconditionally.

Both admin fixtures call:
```python
create_access_token(subject=user.id, role="internal_admin", mfa=True)
create_access_token(subject=user.id, role="super_admin",    mfa=True)
```

This produces a JWT with `"mfa": true`, which `current_user` maps to `CurrentUser(mfa=True)`, which passes `require_mfa`. The MFA chain is **correctly wired end-to-end**.

Note: Both `Depends(_admin_only)` and `Depends(require_mfa)` are declared as separate parameters on the route. FastAPI resolves both independently from the same request. Both call `current_user` internally; FastAPI's dependency deduplication means `current_user` is only executed once per request. RBAC check and MFA check are both satisfied before the handler body executes. Correct.

### AC4 — Limit query param ✅

`test_audit_log_limit_param` sends `?limit=5`, asserts 200 and `len(body) <= 5`.
Route defines `limit: int = Query(default=50, ge=1, le=500)` and applies `.limit(limit)` to the SQLAlchemy query. Correct enforcement.

### AC5 — Unlock nonexistent email is idempotent ✅

`test_unlock_nonexistent_account_succeeds` posts `nobody-ever-registered@example.com` → expects 200 with `message == "account unlocked"`.
Route calls `get_lockout().reset(payload.email.lower())` unconditionally (no existence check). `reset()` on an unknown key is a no-op in the lockout store. Returns `Message(message="account unlocked")` regardless. Idempotency confirmed.

### AC6 — AI_SERVICE-only create / PATIENT+DOCTOR → 403 ✅ (Priority Focus item — verified)

`test_ai_service_creates_session` → AI_SERVICE + consent + feature flag → 201 ✅

`test_patient_cannot_create_session_for_another_patient` → PATIENT A posting for Patient B's `patient_id` → 403 ✅

`test_doctor_cannot_create_session_without_consent` → DOCTOR without consent → 403 ✅

**Critical boundary analysis:** The `POST /ai_sessions` route uses `Depends(current_user)` (not `require_roles`). The 403 for PATIENT and DOCTOR is NOT enforced by `require_roles`. It is enforced by the **ConsentGuard**:

```python
guard.require(
    patient_id=payload.patient_id,
    consent_type="ai_use",
    data_scope="*",
    actor_id=user.id,
    actor_type=user.role,
)
```

- For Patient A posting for Patient B: Patient A's `user.id` has no `ai_use` consent record as `granted_to` for Patient B → `ConsentDenied` → 403. ✅
- For DOCTOR without consent: Doctor's `user.id` has no `ai_use` consent record for that patient → `ConsentDenied` → 403. ✅
- For AI_SERVICE with `consent_for_ai_service` fixture: `Consent(granted_to=ai_service_user["user_id"])` is seeded → ConsentGuard passes → 201. ✅

The tests correctly assert `"consent" in body["detail"].lower()` confirming the denial reason is consent-based, not role-based. The docstring in `test_ai_sessions_full.py` correctly documents this: "Patient creates session for another patient → denied (403)" and "Doctor without consent → denied (403)". Accurate.

### AC7 — `GET /ai-sessions/{id}` RBAC ✅

- `test_patient_reads_own_session` → Patient A reads own session → 200 ✅
- `test_patient_cannot_read_another_patients_session` → Patient A reads Patient B's session → 403 ✅
- `test_doctor_reads_patient_session_with_consent` → DOCTOR reads any session → 200 ✅
- `test_unauthenticated_cannot_read_session` → no token → 401 ✅

`_check_session_read_access` in `ai_sessions.py` correctly handles all cases.

### AC8 — `GET /ai-sessions` list ✅

- `test_patient_lists_own_sessions` → 200, own session appears in list ✅
- `test_doctor_lists_patient_sessions` → 200, both seeded sessions visible to doctor ✅

Patient list path auto-resolves `patient_id` from `PatientProfile.user_id`. Doctor has no `patient_id` filter → gets all sessions. Both verified.

### AC9 — Recommendations empty list ✅

`test_list_recommendations_empty` → flag on, no recs seeded → 200, `[] ` ✅

### AC10 — No duplication with `test_ai_sessions_api.py` ✅ (Priority Focus item — verified)

Test function names in `test_ai_sessions_full.py`:
```
test_ai_service_creates_session
test_patient_cannot_create_session_for_another_patient
test_doctor_cannot_create_session_without_consent
test_patient_reads_own_session
test_patient_cannot_read_another_patients_session
test_doctor_reads_patient_session_with_consent
test_unauthenticated_cannot_read_session
test_patient_lists_own_sessions
test_doctor_lists_patient_sessions
test_list_recommendations_empty
```

Test function names in `test_ai_sessions_api.py`:
```
test_create_ai_session_flag_enabled
test_create_ai_session_flag_disabled_returns_503
test_create_ai_session_no_consent_returns_403
test_patient_reads_own_ai_session
test_patient_cannot_read_other_ai_session
test_list_recommendations_scoped
```

**Zero name collisions.** Coverage is complementary: `test_ai_sessions_api.py` focuses on feature flags (503 when disabled) and self-consent; `test_ai_sessions_full.py` focuses on AI_SERVICE role, cross-patient isolation, DOCTOR read access, list endpoint, and unauthenticated access.

### AC11 — 21 new tests all pass, 0 regressions ✅

Confirmed by live run:
```
21 items collected → 21 passed
Full suite: 380 passed, 1 skipped, 0 failed
```

### AC12 — No production code modified ✅

`git diff main..feature/t17-admin-aisessions-tests --name-only` output:
```
backend/tests/api/test_admin_api.py        ← new test file
backend/tests/api/test_ai_sessions_full.py ← new test file
docs/agent/T17_IMPLEMENTATION_REPORT.md   ← docs only
```

Zero changes to `app/` or any production code.

---

## Summary

T17 delivers 21 well-targeted tests with 100% pass rate and zero regressions. The MFA token chain is correctly wired (`create_access_token(mfa=True)` → JWT claim → `require_mfa` dependency). The AI session creation boundary is correctly enforced by ConsentGuard (not `require_roles`), and tests accurately verify and document this mechanism. No test name duplication exists between the two AI session test files.
