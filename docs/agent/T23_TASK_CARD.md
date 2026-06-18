# T23 — Notification Scaffold

**Sprint:** MVP P0 — Notifications (nhắc / cảnh báo)
**Branch:** `feature/t23-notification-scaffold`
**Owner:** Claude Code
**Status:** READY FOR CODEX REVIEW
**Created:** 2026-06-18

---

## Context

Currently no notification system exists in the platform. This sprint creates:
- A persistent `Notification` data model
- In-app notification CRUD via REST API
- Scaffold for future push/email transport (out of scope for this sprint)

---

## Scope

### Files Created

| File | Purpose |
|------|---------|
| `backend/app/models/notification.py` | `Notification` ORM model |
| `backend/alembic/versions/t23_add_notifications.py` | DB migration |
| `backend/app/schemas/notification.py` | Pydantic schemas |
| `backend/app/services/notification.py` | Business logic |
| `backend/app/api/v1/routes/notifications.py` | API routes |
| `backend/tests/api/test_notifications_api.py` | 10 API tests |
| `docs/agent/T23_TASK_CARD.md` | This file |
| `docs/agent/T23_IMPLEMENTATION_REPORT.md` | Implementation notes |

### Files Modified

| File | Change |
|------|--------|
| `backend/app/models/__init__.py` | Register `Notification` model |
| `backend/app/schemas/__init__.py` | Export `NotificationCreate`, `NotificationOut` |
| `backend/app/api/v1/router.py` | Include `notifications.router` |

---

## API Endpoints

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| `GET` | `/api/v1/notifications` | PATIENT, DOCTOR, ADMIN, MEDICAL_REVIEWER | List own notifications |
| `PATCH` | `/api/v1/notifications/{id}/read` | PATIENT, DOCTOR, ADMIN, MEDICAL_REVIEWER | Mark single as read |
| `POST` | `/api/v1/notifications/read-all` | PATIENT, DOCTOR, ADMIN, MEDICAL_REVIEWER | Mark all own as read |
| `POST` | `/api/v1/notifications` | INTERNAL_ADMIN, SUPER_ADMIN only | Create for any user |

**Blocked roles:** `AI_SERVICE`, `CLINIC_ADMIN` → 403 on all endpoints.

---

## Data Model

```
notifications
  id          String(36) PK (UUID)
  user_id     String(36) FK → users.id (CASCADE, indexed)
  type        String(64)  — appointment_reminder | health_alert | lab_ready | care_plan_update | system
  title       String(256)
  body        Text
  is_read     Boolean     default False
  read_at     DateTime    nullable
  created_at  DateTime    server_default CURRENT_TIMESTAMP
  metadata_   Text        nullable  (JSON string)
```

---

## Validation Results

```
Ruff:  PASS (0 errors in new files)
Tests: 487 passed, 1 skipped  (baseline 475 → +12)
Migration: t21_add_booking → t23_add_notifications ✓
```

---

## Out of Scope

- Push notifications (FCM/APNs)
- Email notifications
- WebSocket real-time delivery
- Notification preferences / opt-out
- Notification expiry / cleanup
