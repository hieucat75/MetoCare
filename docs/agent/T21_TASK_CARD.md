# T21 — Booking Scaffold: Doctor Availability + Appointment Slot API

**Sprint:** T21  
**Branch:** `feature/t21-booking-scaffold`  
**Owner:** Claude Code  
**Status:** IN PROGRESS → READY FOR CODEX REVIEW  
**Created:** 2026-06-18  

---

## Purpose

MVP P0 use case #7: "Đặt lịch bác sĩ + gửi hồ sơ trước khám".

Currently NO booking API exists. This sprint creates the minimal scaffold for:
1. Doctor creates availability slots
2. Patient books a slot → appointment created
3. Patient views their appointments
4. Doctor views their appointment queue

**Out of scope:** Payment integration, video consultation links, SMS/push reminders.

---

## Scope

### New Models
- `DoctorAvailability` → `backend/app/models/availability.py`
- `BookingAppointment` → `backend/app/models/appointment.py`

### Migration
- `backend/alembic/versions/t21_add_booking.py`
- `down_revision`: `t19_add_triage_log`

### API Routes (`backend/app/api/v1/routes/booking.py`)
```
POST   /doctors/{doctor_id}/availability      # DOCTOR only (own)
GET    /doctors/{doctor_id}/availability      # PATIENT / DOCTOR / ADMIN
POST   /appointments                          # PATIENT only
GET    /patients/{patient_id}/appointments    # PATIENT(own) / DOCTOR(own patients) / ADMIN
PATCH  /appointments/{appointment_id}         # DOCTOR(confirm/cancel) / PATIENT(cancel own pending)
```

### RBAC
| Endpoint | PATIENT | DOCTOR | ADMIN | CLINIC_ADMIN | AI_SERVICE |
|----------|---------|--------|-------|--------------|------------|
| POST availability | ❌ | ✅ own | ✅ | ❌ | ❌ |
| GET availability | ✅ | ✅ | ✅ | ❌ | ❌ |
| POST appointment | ✅ | ❌ | ❌ | ❌ | ❌ |
| GET appointments | ✅ own | ✅ own | ✅ | ❌ | ❌ |
| PATCH appointment | ❌ | ✅ confirm/cancel | ❌ | ❌ | ❌ |
| PATCH appointment | ✅ cancel pending | ❌ | ❌ | ❌ | ❌ |

---

## Acceptance Criteria

- [ ] Migration runs cleanly with `alembic upgrade head`
- [ ] Ruff passes with zero violations
- [ ] 12+ new tests pass (baseline: 455 passed, 1 skipped)
- [ ] All RBAC rules enforced
- [ ] Double-booking returns 409
- [ ] Unauthenticated returns 401

---

## Files Changed

- `backend/app/models/availability.py` (NEW)
- `backend/app/models/appointment.py` (NEW)
- `backend/app/models/__init__.py` (add imports)
- `backend/alembic/versions/t21_add_booking.py` (NEW)
- `backend/app/schemas/booking.py` (NEW)
- `backend/app/schemas/__init__.py` (export)
- `backend/app/services/booking.py` (NEW)
- `backend/app/api/v1/routes/booking.py` (NEW)
- `backend/app/api/v1/router.py` (register booking router)
- `backend/tests/api/test_booking_api.py` (NEW)
- `docs/agent/T21_TASK_CARD.md` (this file)
- `docs/agent/T21_IMPLEMENTATION_REPORT.md`
