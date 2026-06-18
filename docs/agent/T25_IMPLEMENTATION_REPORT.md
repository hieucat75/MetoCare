# T25 — Admin Portal: User Management Endpoints — Implementation Report

**Branch:** `feature/t25-admin-user-management`
**Base commit:** `04884d0`
**T25 commit:** `d47e85f`
**Status:** ✅ READY FOR CODEX REVIEW

---

## Summary

Implemented full user management for the MVP admin portal: list users, get user detail, update user role (SUPER_ADMIN only), soft-delete/deactivate a user, and per-user audit log retrieval. All endpoints are restricted to INTERNAL_ADMIN / SUPER_ADMIN with tight RBAC guards.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/admin_users.py` | NEW — 5 service functions |
| `backend/app/schemas/admin.py` | Extended — `UserAdminOut` + `created_at`, `UserRoleUpdate` uses enum, new `UserAuditLogOut` |
| `backend/app/schemas/__init__.py` | Export `UserAuditLogOut` |
| `backend/app/api/v1/routes/admin.py` | 5 new routes added |
| `backend/tests/api/test_admin_users_api.py` | NEW — 13 tests |
| `docs/agent/T25_TASK_CARD.md` | Task card |
| `docs/agent/T25_IMPLEMENTATION_REPORT.md` | This file |

---

## Routes Implemented

| Method | Path | RBAC |
|--------|------|------|
| GET | `/api/v1/admin/users` | INTERNAL_ADMIN, SUPER_ADMIN |
| GET | `/api/v1/admin/users/{user_id}` | INTERNAL_ADMIN, SUPER_ADMIN |
| PATCH | `/api/v1/admin/users/{user_id}/role` | SUPER_ADMIN only |
| DELETE | `/api/v1/admin/users/{user_id}` | INTERNAL_ADMIN, SUPER_ADMIN |
| GET | `/api/v1/admin/users/{user_id}/audit-log` | INTERNAL_ADMIN, SUPER_ADMIN |

---

## RBAC Rules Enforced

- **DOCTOR, PATIENT, AI_SERVICE, CLINIC_ADMIN** → 403 on all user endpoints
- **INTERNAL_ADMIN** → can list / get / deactivate, **cannot** update role (403)
- **SUPER_ADMIN** → full access
- **Self-deactivation** → 400 Bad Request
- **Deactivate another SUPER_ADMIN** → 403 Forbidden

---

## Service Design (`admin_users.py`)

Service layer is clean and separated from HTTP concerns:

- `list_users(db, skip, limit, role_filter)` — paginated, optional role filter
- `get_user(db, user_id)` — direct db.get, returns None on miss
- `update_user_role(db, user_id, new_role, requester_id)` — raises `ValueError` on not found
- `deactivate_user(db, user_id, requester_id)` — raises `PermissionError` for self-deactivation or SUPER_ADMIN target, `ValueError` for not found
- `get_user_audit_log(db, user_id, limit)` — queries AuditLog by actor_id

Error types map cleanly to HTTP status codes in the route layer (ValueError → 404, PermissionError → 400 for self, 403 for SUPER_ADMIN).

---

## Schema Changes

- `UserAdminOut`: added `created_at: dt.datetime | None` (populated by `TimestampMixin`)
- `UserRoleUpdate.role`: changed from `str` to `UserRole` enum (safer validation)
- `UserAuditLogOut` (NEW): id, action, resource_type, resource_id, timestamp — maps directly to `AuditLog` model

---

## Tests

**13 tests total** (11 required + 2 bonus):

| # | Test | Result |
|---|------|--------|
| 1 | SUPER_ADMIN lists users → 200 | ✅ |
| 2 | INTERNAL_ADMIN lists users → 200 | ✅ |
| 3 | DOCTOR lists users → 403 | ✅ |
| 4 | PATIENT lists users → 403 | ✅ |
| 5 | SUPER_ADMIN gets user detail → 200 | ✅ |
| 6 | SUPER_ADMIN updates user role → 200, new role reflected | ✅ |
| 7 | INTERNAL_ADMIN cannot update role → 403 | ✅ |
| 8 | SUPER_ADMIN deactivates user → 200, is_active=False | ✅ |
| 9 | SUPER_ADMIN cannot deactivate self → 400 | ✅ |
| 10 | SUPER_ADMIN gets user audit log → 200, list | ✅ |
| 11 | AI_SERVICE → 403 on all admin endpoints | ✅ |
| 12 | SUPER_ADMIN cannot deactivate another SUPER_ADMIN → 403 (bonus) | ✅ |
| 13 | GET non-existent user → 404 (bonus) | ✅ |

---

## Validation Results

```
Ruff check (T25 files): All checks passed!
Tests (T25 only):       13 passed in 0.14s
Tests (full suite, excl. pre-existing T24 failures): 508 passed, 1 skipped
Delta vs baseline 04884d0: +13 tests
```

---

## Audit Trail

All user management actions are audit-logged via `app.services.audit.record()`:
- `admin_read` / `user_list` — list users
- `admin_read` / `user` — get user detail  
- `admin_action` / `user_role` — role change
- `admin_action` / `user_deactivate` — deactivation
- `admin_read` / `user_audit_log` — reading audit log

---

## Notes for Codex Review

1. **No MFA required** on user management routes (unlike audit-logs and unlock-account). This matches the task spec which doesn't mention MFA for these endpoints. If needed, `require_mfa` can be added as a dependency.
2. **AuditLog uses `timestamp` field** (not `created_at`). The `UserAuditLogOut` schema correctly maps to `timestamp`.
3. **`list_users` is not paginated with cursor** — uses offset/limit. Sufficient for MVP.
4. **`deactivate_user` checks happen in the service layer** — cleaner separation than inline route logic.
