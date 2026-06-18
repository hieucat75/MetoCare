# T21 — Implementation Report: Booking Scaffold

**Branch:** `feature/t21-booking-scaffold`  
**Status:** READY FOR CODEX REVIEW  
**Date:** 2026-06-18  
**Author:** Claude Code  

---

## Summary

Implemented the minimal booking scaffold for MVP P0 use case #7: "Đặt lịch bác sĩ + gửi hồ sơ trước khám".

Two new models, a migration, schemas, service layer, routes, and 12 tests — all within the allowed file list.

---

## Test Results

```
474 → 467 passed, 1 skipped  (branch baseline: 455 from main HEAD f1c0e4c)
New T21 tests: +12
Ruff: PASS (0 violations)
Migration: alembic upgrade head → OK
```

Note: 467 = 455 (main baseline) + 12 (T21 new). Full suite 474 figure was on the t20 branch which also has +19 tests.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/models/availability.py` | NEW — DoctorAvailability model |
| `backend/app/models/appointment.py` | NEW — BookingAppointment model |
| `backend/app/models/__init__.py` | Register new models |
| `backend/alembic/versions/t21_add_booking.py` | NEW — migration |
| `backend/app/schemas/booking.py` | NEW — Pydantic schemas |
| `backend/app/schemas/__init__.py` | Export booking schemas |
| `backend/app/services/booking.py` | NEW — service functions |
| `backend/app/api/v1/routes/booking.py` | NEW — API routes |
| `backend/app/api/v1/router.py` | Register booking router |
| `backend/tests/api/test_booking_api.py` | NEW — 12 tests |
| `docs/agent/T21_TASK_CARD.md` | Task card |
| `docs/agent/T21_IMPLEMENTATION_REPORT.md` | This file |

---

## Design Notes

### Model Naming

The existing `care.py` already has an `Appointment` model (table: `appointments`) used for the doctor handoff / encounter flow. The new T21 booking appointment model uses:
- Class: `BookingAppointment`
- Table: `booking_appointments`

This avoids any collision with the existing model.

### Doctor ID via `users.id`

Per the task spec, `doctor_id` FK points to `users.id` (not `doctors.id`). The DOCTOR role check at the route level uses `user.id` (from the JWT), which is the same `users.id`. This means a doctor's `user_id` and their booking availability `doctor_id` are the same value — consistent with the spec.

### Double-Booking Prevention

The `BookingAppointment.availability_id` column has a `unique=True` constraint at the DB level. Additionally, the service layer checks `is_booked` before creating the appointment and sets it to True atomically. This provides defense-in-depth.

### RBAC Summary

| Endpoint | DOCTOR | PATIENT | ADMIN | CLINIC_ADMIN | AI_SERVICE |
|----------|--------|---------|-------|--------------|------------|
| POST availability | ✅ own | ❌ 403 | ❌ 403 | ❌ 403 | ❌ 403 |
| GET availability | ✅ | ✅ | ✅ | ❌ 403 | ❌ 403 |
| POST appointment | ❌ 403 | ✅ | ❌ 403 | ❌ 403 | ❌ 403 |
| GET appointments | ✅ own | ✅ own | ✅ | ❌ 403 | ❌ 403 |
| PATCH appointment | ✅ confirm/cancel | ✅ cancel pending | ❌ 403 | ❌ 403 | ❌ 403 |

### Out of Scope (Future Sprints)

- Payment / fee collection
- Video consultation links
- SMS/push reminders
- Slot overlap detection (doctor creating conflicting slots)
- Cancellation notification emails

---

## Test Coverage (12 tests)

1. `test_doctor_can_add_availability_slot` — 201 + correct fields
2. `test_patient_can_list_available_slots` — 200 + list
3. `test_non_doctor_cannot_add_availability` — 403
4. `test_patient_can_book_slot` — 201 + correct fields
5. `test_booking_marks_slot_as_booked` — is_booked=True in DB
6. `test_cannot_double_book_same_slot` — 409
7. `test_patient_can_view_own_appointments` — 200 + list
8. `test_patient_cannot_view_other_patients_appointments` — 403
9. `test_doctor_can_view_appointment_queue` — 200 + filtered by doctor
10. `test_doctor_can_confirm_appointment` — 200 + status=confirmed
11. `test_patient_can_cancel_own_pending_appointment` — 200 + status=cancelled
12. `test_unauthenticated_returns_401` — 401
