# PA-03 Task Card — Patient App MVP Backend

**Branch:** `feature/pa03-patient-mvp-backend`
**Base commit:** `8c8ac71`
**Owner:** Claude Code
**Status:** READY FOR CODEX REVIEW

---

## Objectives

1. Extend `GET /auth/me` to return `patient_profile_id` for PATIENT callers
2. Change `PATCH /patients/{id}/profile` to upsert (create on first use)
3. Write 8 new tests for the Patient App MVP flows
4. Verify all existing Patient App MVP endpoints are wired and tested

---

## Scope

### 1. GET /auth/me — `patient_profile_id`

**Problem:** After login, a patient has `user_id` from JWT but no way to resolve their `patient_profile_id` without a separate lookup.

**Solution:** Added `patient_profile_id: str | None` to `UserOut` schema. The `/auth/me` handler queries `PatientProfile` by `user_id` FK and populates the field for PATIENT role callers. Non-patient roles always receive `null`.

### 2. PATCH /patients/{id}/profile — upsert

**Problem:** First-launch onboarding fails with 404 because no `PatientProfile` exists.

**Solution:** For PATIENT callers, if `db.get(PatientProfile, patient_id)` returns None, the handler checks if `patient_id` matches the caller's `User.id`. If so, it auto-creates a `PatientProfile` with `user_id=caller.id`, applies the supplied fields, audits, and returns 200. All other callers fall through to the existing `svc.update_profile()` path unchanged.

### 3. Tests

8 new tests in `tests/api/test_patient_mvp_api.py`:
- `test_me_patient_no_profile`
- `test_me_patient_with_profile`
- `test_me_doctor_no_patient_profile_id`
- `test_patient_profile_upsert_creates_on_first_patch`
- `test_patient_profile_upsert_updates_on_second_patch`
- `test_notifications_list_patient`
- `test_notifications_mark_read`
- `test_notifications_unauthenticated`

### 4. Endpoint Verification

All Patient App MVP endpoints were verified as present and wired:

| Endpoint | Route File | Tests |
|----------|-----------|-------|
| POST/GET /patients/{id}/metrics | lab.py | test_lab_api.py |
| GET /patients/{id}/metrics/trend | lab.py | test_metabolic_score_history_api.py |
| POST/GET /patients/{id}/lab-documents | lab.py | test_lab_api.py |
| GET /patients/{id}/metabolic-scores | patients.py | test_metabolic_score_history_api.py |
| POST/GET /patients/{id}/symptoms | patients.py | test_symptom_medication_api.py |
| POST/GET /patients/{id}/medications | patients.py | test_symptom_medication_api.py |
| DELETE /patients/{id}/medications/{mid} | patients.py | test_symptom_medication_api.py |
| POST/GET /patients/{id}/nutrition | patients.py | test_nutrition_log_api.py |
| POST/GET/DELETE /patients/{id}/consents | consent.py | test_consent_api.py |
| GET/PATCH /patients/{id}/profile | patients.py | test_patient_profile_api.py + PA03 |
| GET /patients/{id}/triage-history | patients.py | test_triage_log_api.py |
| GET/PATCH /notifications | notifications.py | test_notifications_api.py + PA03 |

---

## Files Changed

- `backend/app/schemas/auth.py` — added `patient_profile_id: str | None = None` to `UserOut`
- `backend/app/api/v1/routes/auth.py` — `/auth/me` resolves and returns `patient_profile_id`
- `backend/app/api/v1/routes/patients.py` — PATCH profile upsert for PATIENT first-launch
- `backend/tests/api/test_patient_mvp_api.py` — NEW: 8 PA-03 MVP tests
