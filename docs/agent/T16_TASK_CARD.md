# T16 Task Card — Care Plan + Encounter Full RBAC Test Coverage

**TASK_ID:** T16  
**LABEL:** Care Plan + Encounter — Complete RBAC Test Coverage  
**Branch:** `feature/t16-care-plan-encounter-tests`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

Care Plan and Encounter APIs have partial test coverage (9 + 7 tests). This sprint completes the coverage:

**Care Plans** (`/encounters/{id}/care-plans`): 5 endpoints → full RBAC + flow tests  
**Encounters** (`/encounters`): 4 endpoints → full RBAC + flow tests

---

## Scope

### ALLOWED_FILES

- `backend/tests/api/test_care_plans_full.py` — NEW (replaces/extends existing partial test)
- `backend/tests/api/test_encounters_full.py` — NEW (replaces/extends existing partial test)
- `docs/agent/T16_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- Any production code (pure test sprint)
- Existing test files (`test_care_plans_api.py`, `test_encounters_api.py`, `test_care_plan_approve.py`)

---

## Care Plan Endpoints to Cover

From `app/api/v1/routes/care_plans.py`:
1. `POST /encounters/{id}/care-plans` — create care plan
2. `GET /encounters/{id}/care-plans/{plan_id}` — get one
3. `GET /encounters/{id}/care-plans` — list all
4. `PATCH /encounters/{id}/care-plans/{plan_id}` — update
5. `POST /encounters/{id}/care-plans/{plan_id}/approve` — approve

### Care Plan Tests (minimum 14):

1. `test_doctor_creates_care_plan` → 201
2. `test_patient_cannot_create_care_plan` → 403
3. `test_ai_service_cannot_create_care_plan` → 403
4. `test_clinic_admin_cannot_create_care_plan` → 403
5. `test_doctor_reads_care_plan` → 200
6. `test_patient_reads_own_care_plan` → 200
7. `test_patient_cannot_read_other_patients_care_plan` → 403
8. `test_doctor_lists_care_plans` → 200, list
9. `test_doctor_updates_care_plan` → 200
10. `test_patient_cannot_update_care_plan` → 403
11. `test_doctor_approves_care_plan` → 200
12. `test_patient_cannot_approve_care_plan` → 403
13. `test_ai_cannot_approve_care_plan` → 403
14. `test_approve_nonexistent_plan` → 404
15. `test_unauthenticated_cannot_access_care_plan` → 401

---

## Encounter Endpoints to Cover

From `app/api/v1/routes/encounters.py`:
1. `POST /encounters` — create
2. `GET /encounters/{id}` — get one
3. `GET /encounters` — list
4. `PATCH /encounters/{id}` — update

### Encounter Tests (minimum 12):

1. `test_doctor_creates_encounter` → 201
2. `test_patient_cannot_create_encounter` → 403
3. `test_ai_service_cannot_create_encounter` → 403
4. `test_doctor_reads_own_encounter` → 200
5. `test_patient_reads_own_encounter` → 200
6. `test_patient_cannot_read_another_patients_encounter` → 403
7. `test_admin_reads_any_encounter` → 200
8. `test_doctor_lists_encounters` → 200
9. `test_patient_lists_own_encounters` → 200
10. `test_doctor_updates_encounter` → 200
11. `test_patient_cannot_update_encounter` → 403
12. `test_unauthenticated_cannot_access_encounter` → 401
13. `test_encounter_create_with_all_fields` → 201 (notes, diagnosis, etc.)

---

## Acceptance Criteria

- [ ] 15 care plan tests pass
- [ ] 13 encounter tests pass
- [ ] All endpoints covered: create, read, list, update, approve
- [ ] All RBAC roles tested: PATIENT, DOCTOR, AI_SERVICE, CLINIC_ADMIN, ADMIN, unauth
- [ ] Zero regressions (331 baseline → 359+ total)
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

*Task Card issued: 2026-06-18 18:45 GMT+7 | Coordinator: OpenClaw*
