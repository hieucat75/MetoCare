## Codex Review — T25 Admin Portal User Management

**Branch:** `feature/t25-admin-user-management`
**Reviewed:** 2026-06-18
**Reviewer:** Codex (read-only)

**Result:** REQUEST_CHANGES

**P0 Blockers:** 1
**P1 Blockers:** 0
**P2 Warnings:** 2
**Security:** PASS
**Test Results:** 508 passed (T25 tests: 13/13), 1 skipped — *excluding 7 T24 PDF failures (branch contamination)*
**Acceptance Criteria:** 9/10 met

---

## P0 Blockers

### P0-1 — Branch contamination: T24 PDF files break 7 tests

The T25 commit (`d47e85f`) includes files from T24 (PDF export feature) that have **not yet been merged to `main`** and are incomplete:

- `backend/app/services/pdf_report.py` — T24 service, unregistered route
- `backend/tests/api/test_pdf_export_api.py` — 7 T24 tests, all failing with 404

Running `python -m pytest tests/ -p no:warnings` yields:

```
7 failed, 508 passed, 1 skipped
```

AC10 specifies full suite pass (`506+ passed`). The 7 failures are caused by T24 test file asserting routes that do not exist on this branch, meaning the route registration (`pdf_report.py` service exists but no route was registered). **The suite must not regress.** These failures block merge.

**Fix:** Either remove `pdf_report.py` and `test_pdf_export_api.py` from the T25 branch (they belong in a dedicated T24 branch), or register and complete the PDF route so those 7 tests pass.

---

## P2 Warnings

### P2-1 — `UserAuditLogOut` field name diverges from task card spec

The task card (`T25_TASK_CARD.md`) specifies `UserAuditLogOut.created_at`, but the implementation uses `timestamp` (line 45 of `admin.py`). This is actually **correct** since the `AuditLog` model column is `timestamp`, not `created_at` — however it's an undocumented deviation from the written spec. The implementation choice is right; the spec should be updated to match.

### P2-2 — `get_user_audit_log` queries by `actor_id`, not `resource_id`

In `admin_users.get_user_audit_log`, the query filters by `AuditLog.actor_id == user_id`. This returns entries where the target user was the **actor** (i.e., things they did), not entries where they were the **subject** (e.g., role changes, deactivations done *to* them). For a user management audit view, operators likely want both. This is a design choice rather than a bug, but could create a confusing UX where "audit log for user X" shows nothing when user X was the target of admin actions.

---

## Acceptance Criteria Evaluation

| AC | Description | Result | Notes |
|----|-------------|--------|-------|
| AC1 | List users RBAC: SA/IA → 200; DOCTOR/PATIENT/AI → 403 | ✅ PASS | Tests 1–4, 11 confirm |
| AC2 | Get user detail: SA/IA → 200; others → 403 | ✅ PASS | Test 5, covered by AI_SERVICE test 11 |
| AC3 | Update role gated to SUPER_ADMIN; IA → 403 | ✅ PASS | Tests 6–7 confirm |
| AC4 | Deactivation safety: self → 400; other SA → 403 | ✅ PASS | Tests 9, 12 confirm |
| AC5 | Deactivate sets is_active=False in response | ✅ PASS | Test 8 asserts `is_active is False` |
| AC6 | Audit log endpoint: SA → 200, returns list | ✅ PASS | Test 10 confirms |
| AC7 | Service: checks requester_id ≠ target; target role ≠ SUPER_ADMIN | ✅ PASS | `deactivate_user` service verified |
| AC8 | No unauthorized data exposure (no password_hash, no secrets) | ✅ PASS | `UserAdminOut` excludes `password_hash`, `mfa_secret` |
| AC9 | Ruff clean | ✅ PASS | `ruff check .` → All checks passed |
| AC10 | Full suite: 506+ passed | ❌ FAIL | 7 T24 test failures (branch contamination); T25-only subset passes cleanly |

---

## Summary

T25 implementation is **functionally sound**. The service layer, route RBAC, schema safety, and all 13 dedicated tests are correct and pass cleanly. The code quality is high: proper `PermissionError`/`ValueError` separation in service, correct HTTP status mapping in routes (400 vs 403), no secret field exposure.

**The sole blocker is branch hygiene**: T24 PDF export work was accidentally included in the T25 commit. This causes 7 test failures in `test_pdf_export_api.py`, which is not a T25 file but is present on the branch. Removing these two T24 files (or completing the PDF route) will bring the full suite to a clean pass and unblock merge.

**Recommended action:** Strip `pdf_report.py` and `test_pdf_export_api.py` from this branch (move/save them for the T24 branch), then the suite runs at **508 passed, 1 skipped — merge-ready**.
