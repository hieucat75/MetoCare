# PA-03 Implementation Report — Patient App MVP Backend

**Date:** 2026-06-18
**Branch:** `feature/pa03-patient-mvp-backend`
**Commit:** `0fc4be4`
**Author:** Claude Code (subagent)

---

## Summary

PA-03 successfully closes two critical gaps identified in the deploy smoke test:

1. **No way for patients to discover their `patient_profile_id`** — solved via `/auth/me` extension
2. **First-launch profile PATCH fails with 404** — solved via upsert behaviour

8 new tests added. All 523 tests pass (baseline 515, +8). Ruff clean.

---

## Changes Made

### `backend/app/schemas/auth.py`

Added `patient_profile_id: str | None = None` to `UserOut`. Defaults to `None` so existing callers (non-patient roles) are unaffected.

### `backend/app/api/v1/routes/auth.py`

- Added `from app.models.patient import PatientProfile` import at module level
- Extended `me()` handler: for `PATIENT` role, executes a `SELECT` on `PatientProfile` filtered by `user_id` FK, sets `out.patient_profile_id` to the profile's UUID (or `None` if no profile yet)
- Non-patient roles: `patient_profile_id` stays `None` (Pydantic default)

### `backend/app/api/v1/routes/patients.py`

- Added top-level imports: `PatientProfile as _PatientProfile`, `User as _UserModel`
- `patch_patient_profile()` handler: new PATIENT upsert branch before the existing `svc.update_profile()` call:
  1. Check if a PatientProfile exists for `patient_id`
  2. If not, verify `patient_id` matches the caller's `User.id` (ownership)
  3. Auto-create `PatientProfile(user_id=caller.id)`, flush to get UUID PK
  4. Apply supplied fields, audit, commit, return 200
  5. All other roles and second-call (profile already exists) fall through to existing service

### `backend/tests/api/test_patient_mvp_api.py` (NEW)

8 test cases covering the PA-03 gaps plus notification smoke tests:

| Test | Assertion |
|------|-----------|
| `test_me_patient_no_profile` | 200, `patient_profile_id: null` |
| `test_me_patient_with_profile` | 200, `patient_profile_id` == known UUID |
| `test_me_doctor_no_patient_profile_id` | 200, `patient_profile_id: null` |
| `test_patient_profile_upsert_creates_on_first_patch` | 200, profile row in DB |
| `test_patient_profile_upsert_updates_on_second_patch` | 200, fields updated |
| `test_notifications_list_patient` | 200, list returned |
| `test_notifications_mark_read` | 200, `is_read: true`, `read_at` set |
| `test_notifications_unauthenticated` | 401 |

---

## Quality Gate Results

```
Ruff:    PASS (0 violations)
New tests:  8 passed
Full suite: 523 passed, 1 skipped, 0 failed
Baseline:   515 → 523 (net +8)
```

---

## Existing Endpoint Coverage Verified

All 12 Patient App MVP endpoints confirmed present in routers and covered by existing tests. No missing routes found.

---

## Design Decisions

- **Upsert scope limited to PATIENT role**: Doctors/admins call `svc.update_profile()` which requires the profile to already exist — no change to their flow.
- **`patient_id` as `User.id` alias**: When no `PatientProfile` exists, the caller passes their `user_id` (from JWT) as the `patient_id` URL param. This is the natural onboarding flow: register → call PATCH with `user_id` → profile auto-created.
- **Top-level imports for models in patients.py**: Avoids ruff I001 isort violation. Private-aliased (`_PatientProfile`, `_UserModel`) to signal they are internal to the module and not re-exported.
- **No migration needed**: `PatientProfile.user_id` FK already exists (added in T12). Pure service/schema change.
