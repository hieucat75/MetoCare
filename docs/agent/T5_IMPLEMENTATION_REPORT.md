# T5 Implementation Report — Medical API Endpoints + C3 Feature Flags + C4 RBAC

## Branch
`feature/t5-medical-api-rbac` (branched from `main` @ `94f51cf`)

---

## Files Created

| Path | Description |
|------|-------------|
| `backend/app/core/rbac.py` | Centralized RBAC helpers (C4) |
| `backend/app/api/v1/routes/encounters.py` | Encounter CRUD endpoints |
| `backend/app/api/v1/routes/care_plans.py` | CarePlan CRUD endpoints |
| `backend/app/api/v1/routes/ai_sessions.py` | AISession create/read/list endpoints |
| `backend/tests/api/__init__.py` | Test package marker |
| `backend/tests/api/test_encounters_api.py` | 7 encounter API tests |
| `backend/tests/api/test_care_plans_api.py` | 4 care plan API tests |
| `backend/tests/api/test_ai_sessions_api.py` | 6 AI session API tests |
| `backend/tests/unit/test_rbac.py` | 8 RBAC unit tests |

## Files Modified

| Path | Change |
|------|--------|
| `backend/app/core/feature_flags.py` | Added `AI_SESSION_ENABLED`, `AI_CLINICAL_RECS_ENABLED`, `AI_ESCALATION_ENABLED` flags (all default=False) |
| `backend/app/api/v1/router.py` | Registered 3 new routers (encounters, care_plans, ai_sessions) |

---

## Endpoint Table

### Encounter API (`/api/v1/encounters`)

| Method | Path | Allowed Roles | RBAC Notes |
|--------|------|---------------|------------|
| `POST` | `/encounters` | DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN | Patient not allowed |
| `GET` | `/encounters/{encounter_id}` | All authenticated | Patient: own only; Doctor: assigned clinic/doctor |
| `GET` | `/encounters` | All authenticated | Patient: own patient_id forced; Doctor: own encounters |
| `PATCH` | `/encounters/{encounter_id}` | DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN | Doctor must be assigned |

### CarePlan API (`/api/v1/care_plans`)

| Method | Path | Allowed Roles | RBAC Notes |
|--------|------|---------------|------------|
| `POST` | `/care_plans` | DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN | C2: AI cannot approve |
| `GET` | `/care_plans/{care_plan_id}` | All authenticated | Patient: own only |
| `GET` | `/care_plans` | All authenticated | Filters: patient_id, encounter_id |
| `PATCH` | `/care_plans/{care_plan_id}` | DOCTOR, INTERNAL_ADMIN, SUPER_ADMIN | AI_SERVICE blocked; status guard enforced |

### AISession API (`/api/v1/ai_sessions`)

| Method | Path | Allowed Roles | Guards |
|--------|------|---------------|--------|
| `POST` | `/ai_sessions` | All authenticated | C3: `AI_SESSION_ENABLED` flag (503 when off); ConsentGuard (403 when no consent) |
| `GET` | `/ai_sessions/{session_id}` | All authenticated | Patient: own only |
| `GET` | `/ai_sessions` | All authenticated | Patient: own patient_id forced |
| `GET` | `/ai_sessions/{session_id}/recommendations` | All authenticated | C3: `AI_CLINICAL_RECS_ENABLED` flag (503 when off) |

---

## C3 Feature Flags Added

| Flag | Enum Value | Default | Purpose |
|------|-----------|---------|---------|
| `AI_SESSION_ENABLED` | `ai_session_enabled` | `False` | Gates AISession creation (HTTP 503 when off) |
| `AI_CLINICAL_RECS_ENABLED` | `ai_clinical_recs_enabled` | `False` | Gates viewing AI recommendations |
| `AI_ESCALATION_ENABLED` | `ai_escalation_enabled` | `False` | Gates escalation workflows (reserved) |

All flags are fail-closed by default. Override via environment: `FEATURE_AI_SESSION_ENABLED=true`.

---

## C4 RBAC Helpers (`app/core/rbac.py`)

| Helper | Behavior |
|--------|----------|
| `assert_patient_owns(user_id, patient_id, role)` | 403 unless `user_id == patient_id` or role is ADMIN/REVIEWER |
| `assert_doctor_assigned(db, user_id, clinic_id, role, ...)` | 403 unless DoctorClinic link exists or direct assignment matches |
| `assert_clinic_scope(user_id, clinic_id, role)` | 403 unless ADMIN or CLINIC_ADMIN |

Admin bypass roles: `INTERNAL_ADMIN`, `SUPER_ADMIN`, `MEDICAL_REVIEWER` (read bypass).

---

## Safety Invariants Preserved

- **PHI encrypted:** `Encounter.notes` and `CarePlan.content` use `EncryptedString`.
- **AI cannot approve CarePlan:** `AI_SERVICE` role is blocked from PATCH `/care_plans` entirely.
- **AI cannot write diagnosis or Medication:** No such endpoints exist; AI is blocked from CarePlan write path.
- **ConsentGuard wired:** `POST /ai_sessions` calls `ConsentGuard.require()` before session creation; same path for AI_SERVICE and human callers.
- **No hard deletes:** Soft-delete fields (`deleted_at`) checked in all GET/PATCH endpoints.
- **AuditLog append-only:** Audit records written on create/read/update with no FK.
- **No migrations:** T5 is API-layer only; all models were pre-existing.

---

## Test Results

| Category | Count |
|----------|-------|
| Pre-existing tests (main) | 177 passed, 1 skipped |
| T5 new tests | 25 new |
| **Total** | **202 passed, 1 skipped** |

### New Tests

- `tests/api/test_encounters_api.py` — 7 tests
- `tests/api/test_care_plans_api.py` — 4 tests
- `tests/api/test_ai_sessions_api.py` — 6 tests
- `tests/unit/test_rbac.py` — 8 tests

---

## Ruff Status

**Clean** — `All checks passed!` (ruff v0.x, line-length=100, py311 target)

---

## Verification Commands

```bash
cd /Users/pth/Developer/metocare/backend
source /Users/pth/Developer/metocare/.venv/bin/activate
ruff check .
python -m pytest tests/ -q 2>&1 | tail -3
```

Expected output:
```
All checks passed!
202 passed, 1 skipped, N warnings in X.XXs
```

---

## Deferred Items

1. **CLINIC_ADMIN scope via DoctorClinic:** Currently CLINIC_ADMIN is allowed if role matches; full
   lookup against a `ClinicAdmin` model or explicit `clinic_id` claim in the JWT would be more
   robust. Deferred pending ClinicAdmin model definition.

2. **AI_ESCALATION_ENABLED wiring:** Flag is registered and defaults off, but no endpoint uses it
   yet. Escalation workflow endpoints are out of T5 scope.

3. **Pagination:** List endpoints return all matching records; cursor-based pagination deferred to T6.

4. **Metrics/rate-limiting on new endpoints:** Not applied (consistent with other non-auth endpoints
   in the codebase). Can be added alongside a rate-limit refactor.
