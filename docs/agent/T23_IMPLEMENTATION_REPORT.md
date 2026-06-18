# T23 Implementation Report — Notification Scaffold

**Date:** 2026-06-18
**Branch:** `feature/t23-notification-scaffold`
**Agent:** Claude Code

---

## Summary

T23 delivers the in-app notification scaffold for MetoCare MVP. A new `Notification`
model, Alembic migration, CRUD service, FastAPI routes, and 10 API tests were
implemented following existing T21/T18 patterns.

---

## Design Decisions

### 1. `metadata_` as Text (JSON string) — not `sa.JSON`

The codebase stores all JSON blobs as `Text` (see `ai.py`, `triage_log.py`).
Using `Text` for `metadata_` keeps consistent with this pattern and avoids
SQLite vs PostgreSQL dialect differences with the `JSON` column type. Callers
use `json.dumps()` / `json.loads()` explicitly.

### 2. `server_default=text("CURRENT_TIMESTAMP")`

This is the established pattern from `_mixins.py` — a portable SQL literal
that works on both SQLite (test env) and PostgreSQL (prod). The plain string
`"CURRENT_TIMESTAMP"` passed to `server_default` is **not** wrapped in `text()`
by SQLAlchemy automatically, which causes a `ValueError` when the ORM fetches
back the inserted row via RETURNING. Fixed by importing `text` from SQLAlchemy.

### 3. Route ordering: `POST /read-all` before `POST /`

FastAPI / Starlette route matching is first-match. `POST /notifications/read-all`
must be registered before `POST /notifications` (which captures the empty suffix)
to avoid the `POST /notifications` handler matching `/notifications/read-all` as
an invalid body. With prefix in the `APIRouter` constructor, both routes use
relative paths (`/read-all` and `""`) which FastAPI handles correctly.

### 4. RBAC

- All 4 endpoints return 403 for `AI_SERVICE` and `CLINIC_ADMIN`.
- Creation (`POST /notifications`) is restricted to `INTERNAL_ADMIN` / `SUPER_ADMIN`.
- Read operations are permitted for `PATIENT`, `DOCTOR`, `INTERNAL_ADMIN`, `SUPER_ADMIN`, `MEDICAL_REVIEWER`.
- Ownership is enforced at the service layer for `mark_read`.

### 5. `mark_all_read` uses SQLAlchemy `update()` bulk statement

Rather than loading all rows into memory, `mark_all_read` issues a single
`UPDATE ... WHERE user_id = ? AND is_read = false` via `connection.execute`.
Returns `result.rowcount` — the number of affected rows.

---

## Test Coverage

| # | Test | Status |
|---|------|--------|
| 1 | Admin creates notification for patient → 201 | ✅ |
| 2 | Patient lists own notifications → 200 | ✅ |
| 3 | Patient lists unread only (`?unread_only=true`) → filtered | ✅ |
| 4 | Patient marks notification as read → 200, `is_read=True` | ✅ |
| 5 | Patient cannot mark another user's notification → 403 | ✅ |
| 6 | Patient marks all as read → 200, count returned | ✅ |
| 7 | Doctor lists own notifications → 200 | ✅ |
| 8 | Non-admin cannot create notification → 403 | ✅ |
| 9 | AI_SERVICE → 403 on all 4 notification endpoints | ✅ |
| 10 | Unauthenticated → 401 | ✅ |

**Total:** 10/10 passed

---

## Validation

```
$ cd backend && source ../.venv/bin/activate
$ alembic upgrade head
INFO ... Running upgrade t21_add_booking -> t23_add_notifications ...

$ ruff check .
All checks passed!

$ python -m pytest tests/ --tb=short
487 passed, 1 skipped in 7.09s
```

Baseline: 475 passed → **+12 new tests** (10 notification + 2 carried from T22 work on branch)

---

## Files Delivered

```
NEW:
  backend/app/models/notification.py
  backend/alembic/versions/t23_add_notifications.py
  backend/app/schemas/notification.py
  backend/app/services/notification.py
  backend/app/api/v1/routes/notifications.py
  backend/tests/api/test_notifications_api.py
  docs/agent/T23_TASK_CARD.md
  docs/agent/T23_IMPLEMENTATION_REPORT.md

MODIFIED:
  backend/app/models/__init__.py
  backend/app/schemas/__init__.py
  backend/app/api/v1/router.py
```
