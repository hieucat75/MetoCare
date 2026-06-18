# T22 — Doctor Portal Summary API — Implementation Report

**Branch:** `feature/t22-doctor-portal`
**Commit:** `08c3103`
**Date:** 2026-06-18
**Author:** Claude Code (subagent)

---

## Summary

T22 adds two doctor-facing endpoints to the Metocare MVP:

1. **`GET /patients/{patient_id}/summary`** — Pre-visit patient summary (aggregated)
2. **`GET /doctors/me/appointments`** — Doctor's own upcoming appointments

---

## Files Changed

| File | Type | Description |
|------|------|-------------|
| `backend/app/services/patient_summary.py` | NEW | Aggregation service for pre-visit summary |
| `backend/tests/api/test_doctor_portal_api.py` | NEW | 10 test cases |
| `backend/app/schemas/patient.py` | MODIFIED | Added `PatientSummaryOut`, `VitalsSummary`, `MetabolicScoreSummary` |
| `backend/app/api/v1/routes/patients.py` | MODIFIED | Added `GET /{patient_id}/summary` route |
| `backend/app/api/v1/routes/booking.py` | MODIFIED | Added `GET /doctors/me/appointments` route |
| `backend/app/services/booking.py` | MODIFIED | Added `list_doctor_appointments()` |
| `docs/agent/T22_TASK_CARD.md` | NEW | Task card |
| `docs/agent/T22_IMPLEMENTATION_REPORT.md` | NEW | This file |

---

## Design Decisions

### 1. `PatientSummaryOut` as a flat pydantic model

Rather than using a generic `dict` return, the summary uses typed pydantic models
(`VitalsSummary`, `MetabolicScoreSummary`) to make the API contract explicit and
enable OpenAPI schema generation.

The inner `latest` / `medications` / etc. fields use `list[Any]` for flexibility —
each item is a plain dict with consistent keys. A future sprint could introduce
dedicated item schemas.

### 2. `PatientCompactOut` rename

The existing `PatientSummaryOut` was a compact admin-list view. It was renamed to
`PatientCompactOut` to avoid a naming collision with the new full summary schema.
No existing routes used `PatientSummaryOut` directly (it was only defined, not
imported anywhere else).

### 3. Consent gating for DOCTOR

The summary endpoint reuses the existing `require_access()` / `ConsentError` pattern
from the consent service. DOCTOR without consent → 403 (same as other clinical
data endpoints).

PATIENT and AI_SERVICE are blocked explicitly (403). INTERNAL_ADMIN and SUPER_ADMIN
bypass consent.

### 4. `list_doctor_appointments()` — separate from `list_appointments()`

Rather than overloading the existing `list_appointments()`, a dedicated
`list_doctor_appointments()` was added to the booking service. It JOINs on
`DoctorAvailability` to order by `slot_start ASC` (soonest first) and filters
to `pending` + `confirmed` statuses only.

### 5. DO NOT TOUCH compliance

- No model or migration files were created or modified.
- No existing test files were touched.
- Auth/consent/RBAC logic was not changed — only called.

---

## RBAC Matrix

| Role | Summary endpoint | Doctor appointments |
|------|-----------------|---------------------|
| DOCTOR (with consent) | ✅ 200 | ✅ 200 (own only) |
| DOCTOR (no consent) | ❌ 403 | ✅ 200 (own only) |
| INTERNAL_ADMIN | ✅ 200 | ❌ 403 |
| SUPER_ADMIN | ✅ 200 | ❌ 403 |
| PATIENT | ❌ 403 | ❌ 403 |
| AI_SERVICE | ❌ 403 | ❌ 403 |
| CLINIC_ADMIN | ❌ 403 | ❌ 403 |
| Unauthenticated | ❌ 401 | ❌ 401 |

---

## Test Results

```
Baseline: 475 passed, 1 skipped
After T22: 485 passed, 1 skipped (+10)
Ruff: PASS
```

### Test Cases

| # | Test | Expected |
|---|------|----------|
| 1 | `test_doctor_with_consent_gets_summary` | 200 + all 10 keys |
| 2 | `test_summary_vitals_is_list` | `vitals.latest` is list |
| 3 | `test_summary_medications_only_active` | deleted meds absent |
| 4 | `test_patient_cannot_access_summary` | 403 |
| 5 | `test_ai_service_cannot_access_summary` | 403 |
| 6 | `test_doctor_without_consent_gets_403` | 403 |
| 7 | `test_admin_gets_summary_without_consent` | 200 |
| 8 | `test_doctor_lists_own_appointments` | 200, list |
| 9 | `test_patient_cannot_list_doctor_appointments` | 403 |
| 10 | `test_unauthenticated_cannot_access_summary_or_appointments` | 401 |

---

## Codex Review Notes

- All changes are purely additive (no removals, no breakages).
- Service layer is stateless — no singletons, no background tasks.
- Consent check follows the exact same pattern as T15/T18/T19 routes.
- The `BookingAppointment.doctor_id` field maps to `users.id` (as per T21 model),
  so the DOCTOR auth check compares `appt.doctor_id == user.id` (correct).
- `utcnow()` from `app.core.clock` is used for `generated_at` timestamp
  (consistent with rest of codebase).

---

## Status

```
T22 — READY FOR CODEX REVIEW
Branch: feature/t22-doctor-portal
Tests: 485 passed (baseline 475 → +10)
Ruff: PASS
Files:
  NEW  backend/app/services/patient_summary.py
  NEW  backend/tests/api/test_doctor_portal_api.py
  NEW  docs/agent/T22_TASK_CARD.md
  NEW  docs/agent/T22_IMPLEMENTATION_REPORT.md
  MOD  backend/app/schemas/patient.py
  MOD  backend/app/api/v1/routes/patients.py
  MOD  backend/app/api/v1/routes/booking.py
  MOD  backend/app/services/booking.py
```
