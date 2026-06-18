# T12 Implementation Report — Patient Profile API

**TASK_ID:** T12  
**Branch:** `feature/t12-patient-profile-api`  
**Status:** READY FOR CODEX REVIEW  
**Implementer:** Antigravity (subagent)  
**Completed:** 2026-06-18 GMT+7

---

## Summary

Implemented the Patient Profile API (GET + PATCH) with full RBAC, consent-gating for doctors, audit logging, and 12 API tests.

---

## Files Changed

| File | Action |
|------|--------|
| `backend/app/api/v1/routes/patients.py` | NEW — route handlers |
| `backend/app/api/v1/router.py` | MODIFIED — register `patients` router |
| `backend/app/schemas/patient.py` | MODIFIED — `PatientProfileOut` & `PatientProfileUpdate` scoped per T12 |
| `backend/app/services/patient_profile.py` | NEW — `get_profile()` + `update_profile()` |
| `backend/tests/api/test_patient_profile_api.py` | NEW — 12 tests |

---

## Endpoints Implemented

### `GET /api/v1/patients/{patient_id}/profile`
- Returns `PatientProfileOut` (excludes `address`, `family_history`, `lifestyle_profile`)
- RBAC: PATIENT (own), DOCTOR (consent-gated via `scope='profile'`), INTERNAL_ADMIN, SUPER_ADMIN
- Blocked: AI_SERVICE (403), CLINIC_ADMIN (403)
- Unauthenticated: 401

### `PATCH /api/v1/patients/{patient_id}/profile`
- Partial update (`exclude_unset=True`) — only supplied fields written
- RBAC: PATIENT (own), DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN
- Blocked: AI_SERVICE (403), CLINIC_ADMIN (403)
- Audit: `AuditLog(action='update_profile', resource_type='patient_profile')` on every success

---

## Schema Changes

`PatientProfileOut` (T12 scope — PHI limited):
- Fields: `id`, `user_id`, `full_name`, `dob`, `phone`, `gender`, `height_cm`, `weight_kg`, `waist_cm`, `risk_segment`, `known_conditions`, `allergies`
- Excludes: `address`, `family_history`, `lifestyle_profile` (deferred per medical safety notes)

`PatientProfileUpdate` (T12 scope):
- All same fields as `PatientProfileOut` minus `id`, `user_id`, `risk_segment` (all Optional)
- Excludes: `address`, `family_history`, `lifestyle_profile`

---

## Test Results

```
tests/api/test_patient_profile_api.py::test_patient_reads_own_profile PASSED
tests/api/test_patient_profile_api.py::test_patient_cannot_read_another_patients_profile PASSED
tests/api/test_patient_profile_api.py::test_doctor_reads_patient_profile PASSED
tests/api/test_patient_profile_api.py::test_admin_reads_any_profile PASSED
tests/api/test_patient_profile_api.py::test_ai_service_cannot_read_profile PASSED
tests/api/test_patient_profile_api.py::test_unauthenticated_cannot_read_profile PASSED
tests/api/test_patient_profile_api.py::test_patient_updates_own_profile PASSED
tests/api/test_patient_profile_api.py::test_patient_cannot_update_another_patients_profile PASSED
tests/api/test_patient_profile_api.py::test_doctor_updates_patient_profile PASSED
tests/api/test_patient_profile_api.py::test_ai_service_cannot_update_profile PASSED
tests/api/test_patient_profile_api.py::test_partial_update_preserves_other_fields PASSED
tests/api/test_patient_profile_api.py::test_update_profile_creates_audit_record PASSED

12 passed in 0.13s
```

**Full suite:** 289 passed, 1 skipped (baseline was 277 → +12 new, 0 regressions)

---

## Validation

```
ruff check .       → All checks passed!
pytest tests/      → 289 passed, 1 skipped
```

---

## Acceptance Criteria — Status

| Criteria | Status |
|----------|--------|
| GET /patients/{id}/profile with correct RBAC | ✅ |
| PATCH /patients/{id}/profile with correct RBAC | ✅ |
| Schemas in app/schemas/patient.py | ✅ |
| Service in app/services/patient_profile.py | ✅ |
| Router registered in router.py | ✅ |
| All 12 test cases pass | ✅ |
| Zero regressions (277 → 289+) | ✅ 289 |
| Audit record on PATCH | ✅ |
| Ruff clean | ✅ |

---

## READY FOR CODEX REVIEW
