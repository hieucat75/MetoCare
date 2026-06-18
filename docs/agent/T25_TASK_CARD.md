# T25 — Admin Portal: User Management Endpoints

**Branch:** `feature/t25-admin-user-management`
**Base:** `04884d0` (main HEAD)
**Owner:** Claude Code
**Status:** IN PROGRESS

---

## Context

MVP admin portal needs user management: list users, get user detail, update user role, deactivate (soft delete) user. SUPER_ADMIN and INTERNAL_ADMIN only.

---

## Scope

### Routes (`backend/app/api/v1/routes/admin.py`)

| Method | Path | Access |
|--------|------|--------|
| GET | `/admin/users` | INTERNAL_ADMIN, SUPER_ADMIN |
| GET | `/admin/users/{user_id}` | INTERNAL_ADMIN, SUPER_ADMIN |
| PATCH | `/admin/users/{user_id}/role` | SUPER_ADMIN only |
| DELETE | `/admin/users/{user_id}` | INTERNAL_ADMIN, SUPER_ADMIN |
| GET | `/admin/users/{user_id}/audit-log` | INTERNAL_ADMIN, SUPER_ADMIN |

### RBAC Rules
- All user routes: INTERNAL_ADMIN or SUPER_ADMIN → others 403
- PATCH /role: SUPER_ADMIN only (INTERNAL_ADMIN → 403)
- Cannot deactivate self → 400
- Cannot deactivate another SUPER_ADMIN → 403

### Service (`backend/app/services/admin_users.py` — NEW)
- `list_users(db, skip, limit, role_filter=None) → list[User]`
- `get_user(db, user_id) → User | None`
- `update_user_role(db, user_id, new_role, requester_id) → User`
- `deactivate_user(db, user_id, requester_id) → User`
- `get_user_audit_log(db, user_id, limit=20) → list[AuditLog]`

### Schemas (`backend/app/schemas/admin.py` — extend existing)
- `UserAdminOut`: id, email, role, is_active, created_at, full_name (nullable)
- `UserRoleUpdate`: role (UserRole enum)
- `UserAuditLogOut`: id, action, resource_type, resource_id, created_at

### Tests (`backend/tests/api/test_admin_users_api.py` — NEW)
Minimum 11 tests covering all RBAC scenarios.

---

## Files Changed
- `backend/app/services/admin_users.py` (NEW)
- `backend/app/schemas/admin.py` (extended)
- `backend/app/schemas/__init__.py` (export new schemas)
- `backend/app/api/v1/routes/admin.py` (routes added)
- `backend/tests/api/test_admin_users_api.py` (NEW)
- `docs/agent/T25_TASK_CARD.md`
- `docs/agent/T25_IMPLEMENTATION_REPORT.md`
