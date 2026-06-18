# T22 — Doctor Portal Summary API

**Branch:** `feature/t22-doctor-portal`
**Sprint:** MVP P0 Use Case #8
**Owner:** Claude Code
**Status:** IN PROGRESS

---

## Context

MVP P0 use case #8: "Bác sĩ xem summary + ghi tư vấn + care plan đơn giản + chat follow-up."

Currently DOCTOR can:
- Create/update care plans
- Create encounters
- Review AI recommendations
- View lab docs (with consent)

DOCTOR CANNOT (pre-T22):
- Get a consolidated pre-visit summary of a patient
- List their own upcoming appointments

---

## Scope

### 1. Pre-Visit Patient Summary

**`GET /patients/{patient_id}/summary`**

RBAC:
- DOCTOR → consent-gated (scope=`profile`)
- INTERNAL_ADMIN / SUPER_ADMIN → any patient, no consent needed
- PATIENT → 403
- AI_SERVICE → 403

Response schema: `PatientSummaryOut` (see `backend/app/schemas/patient.py`)

Service: `backend/app/services/patient_summary.py`

### 2. Doctor Appointment List

**`GET /doctors/me/appointments`**

RBAC: DOCTOR only (own appointments)

Returns list of `AppointmentOut` from `app.schemas.booking` filtered to
`doctor_id = current_user.id`, ordered by slot_start ASC, only `pending` or
`confirmed` status by default.

Route: `backend/app/api/v1/routes/booking.py`

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/schemas/patient.py` | Add `PatientSummaryOut` (full pre-visit schema) |
| `backend/app/services/patient_summary.py` | NEW — summary aggregation service |
| `backend/app/api/v1/routes/patients.py` | Add `GET /{patient_id}/summary` route |
| `backend/app/api/v1/routes/booking.py` | Add `GET /doctors/me/appointments` route |
| `backend/tests/api/test_doctor_portal_api.py` | NEW — 10 test cases |
| `docs/agent/T22_TASK_CARD.md` | This file |
| `docs/agent/T22_IMPLEMENTATION_REPORT.md` | Implementation notes |

## DO NOT TOUCH
- Model / migration files
- Existing test files
- Auth/consent/RBAC logic

---

## Tests (10 minimum)

1. `GET /patients/{id}/summary` → DOCTOR with consent → 200 with all keys
2. Summary `vitals.latest` → list (may be empty, not error)
3. Summary `medications` → only active (no deleted)
4. PATIENT → 403 on summary endpoint
5. AI_SERVICE → 403 on summary endpoint
6. DOCTOR without consent → 403 on summary
7. ADMIN → 200 on summary (no consent needed)
8. `GET /doctors/me/appointments` → DOCTOR → 200, list
9. PATIENT → 403 on doctor appointments
10. Unauthenticated → 401

---

## Validation Command

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
alembic upgrade head
ruff check .
python -m pytest tests/ --tb=short
```

Baseline: 475 passed, 1 skipped → target: ≥485 passed
