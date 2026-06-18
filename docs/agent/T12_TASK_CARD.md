# T12 Task Card — Patient Profile API

**TASK_ID:** T12  
**LABEL:** Patient Profile API — GET + PATCH own profile + API Tests  
**Branch:** `feature/t12-patient-profile-api`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

There is no dedicated Patient Profile API. Patients cannot read or update their own profile via the API. This is a P0 MVP requirement. This sprint adds:

1. `GET /patients/{patient_id}/profile` — read own profile
2. `PATCH /patients/{patient_id}/profile` — update own profile (partial)
3. Comprehensive API tests

---

## Scope

### ALLOWED_FILES

- `backend/app/api/v1/routes/patients.py` — NEW route file
- `backend/app/api/v1/router.py` — register new router
- `backend/app/schemas/patient.py` — NEW: `PatientProfileOut`, `PatientProfileUpdate`
- `backend/app/schemas/__init__.py` — export new schemas
- `backend/app/services/patient_profile.py` — NEW: service functions
- `backend/tests/api/test_patient_profile_api.py` — NEW: tests
- `docs/agent/T12_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- `backend/app/models/patient.py`
- Any migration files
- Existing routes

---

## API Design

### `GET /patients/{patient_id}/profile`

**Response:** `PatientProfileOut`
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "full_name": "string or null",
  "dob": "string or null",
  "phone": "string or null",
  "gender": "string or null",
  "height_cm": 170.0,
  "weight_kg": 65.0,
  "waist_cm": null,
  "risk_segment": null,
  "known_conditions": "string or null",
  "allergies": "string or null"
}
```
**Note:** Do NOT include `address`, `family_history`, `lifestyle_profile` in default GET (reserved for extended profile endpoint in future sprint).

**RBAC:**
- PATIENT: own profile only (`patient_profile.user_id == user.id`)
- DOCTOR: any patient (consent-gated via `consent.require_access`)
- INTERNAL_ADMIN, SUPER_ADMIN: any patient (no consent gate needed)
- AI_SERVICE: blocked (403)
- CLINIC_ADMIN: blocked (403)

### `PATCH /patients/{patient_id}/profile`

**Request:** `PatientProfileUpdate` (all fields optional)
```json
{
  "full_name": "string",
  "dob": "string",
  "phone": "string",
  "gender": "string",
  "height_cm": 170.0,
  "weight_kg": 65.0,
  "waist_cm": 85.0,
  "known_conditions": "string",
  "allergies": "string"
}
```

**RBAC:**
- PATIENT: own profile only
- DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN: any patient
- AI_SERVICE: blocked
- CLINIC_ADMIN: blocked

**Audit:** `audit.record(action="update_profile")` on every successful PATCH.

---

## Service Layer

`backend/app/services/patient_profile.py`:

```python
def get_profile(db, *, patient_id: str, requester: CurrentUser) -> PatientProfile
def update_profile(db, *, patient_id: str, requester: CurrentUser, data: dict) -> PatientProfile
```

Both must:
- 404 if patient not found
- 403 via ownership/consent check
- audit on update

---

## Schemas

`backend/app/schemas/patient.py`:
- `PatientProfileOut` — fields listed above (from_attributes=True)
- `PatientProfileUpdate` — all Optional[...] fields

---

## Test Requirements (`tests/api/test_patient_profile_api.py`)

### Fixtures: `patient_setup`, `another_patient_setup`, `doctor_setup`, `admin_setup`

### Test cases (minimum 12):

**GET /patients/{id}/profile:**
1. `test_patient_reads_own_profile` → 200, has `id` field
2. `test_patient_cannot_read_another_patients_profile` → 403
3. `test_doctor_reads_patient_profile` → 200 (with consent)
4. `test_admin_reads_any_profile` → 200
5. `test_ai_service_cannot_read_profile` → 403
6. `test_unauthenticated_cannot_read_profile` → 401

**PATCH /patients/{id}/profile:**
7. `test_patient_updates_own_profile` → 200, fields updated
8. `test_patient_cannot_update_another_patients_profile` → 403
9. `test_doctor_updates_patient_profile` → 200
10. `test_ai_service_cannot_update_profile` → 403
11. `test_partial_update_preserves_other_fields` → 200, only changed fields updated
12. `test_update_profile_creates_audit_record` → audit record exists in db

---

## Acceptance Criteria

- [ ] `GET /patients/{id}/profile` implemented with correct RBAC
- [ ] `PATCH /patients/{id}/profile` implemented with correct RBAC
- [ ] Schemas in `app/schemas/patient.py`
- [ ] Service in `app/services/patient_profile.py`
- [ ] Router registered in `router.py`
- [ ] All 12 test cases pass
- [ ] Zero regressions (277 baseline → 289+ total)
- [ ] Audit record on PATCH
- [ ] Ruff clean

---

## Validation Commands

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
ruff check .
pytest tests/ --tb=short
```

---

## Required Final Status

```
READY FOR CODEX REVIEW
```

---

## Medical Safety Notes

- PHI fields (`full_name`, `dob`, `phone`, etc.) are field-level encrypted at rest via `EncryptedString` — do NOT change column types
- `address`, `family_history`, `lifestyle_profile` are intentionally excluded from `PatientProfileOut` in this sprint (deferred)
- No AI inference or recommendation in this endpoint

---

*Task Card issued: 2026-06-18 08:52 GMT+7 | Coordinator: OpenClaw*
