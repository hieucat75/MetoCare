# T15 Task Card — Symptom Log + Medication API

**TASK_ID:** T15  
**LABEL:** Symptom Log + Medication CRUD API  
**Branch:** `feature/t15-symptom-medication-api`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

`SymptomLog` and `Medication` models exist but have no API. Patients need to self-report symptoms and manage their medication list. This sprint adds:

1. `POST /patients/{patient_id}/symptoms` — log a symptom
2. `GET /patients/{patient_id}/symptoms` — list symptoms (paginated)
3. `POST /patients/{patient_id}/medications` — add medication
4. `GET /patients/{patient_id}/medications` — list medications (active only, paginated)
5. `DELETE /patients/{patient_id}/medications/{med_id}` — soft-delete medication

---

## Scope

### ALLOWED_FILES

- `backend/app/api/v1/routes/patients.py` — add 5 new endpoints
- `backend/app/services/symptom_log.py` — NEW
- `backend/app/services/medication.py` — NEW
- `backend/app/schemas/symptom.py` — NEW: `SymptomLogCreate`, `SymptomLogOut`
- `backend/app/schemas/medication.py` — NEW: `MedicationCreate`, `MedicationOut`
- `backend/app/schemas/__init__.py` — export new schemas
- `backend/tests/api/test_symptom_medication_api.py` — NEW: tests
- `docs/agent/T15_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- `backend/app/models/clinical.py`
- Any migration files
- Other routes

---

## API Design

### Symptom Log

**`POST /patients/{patient_id}/symptoms`**
- Request: `SymptomLogCreate` `{"description": "str", "severity": 0-10 (optional), "reported_at": "ISO datetime (optional, default now)"}`
- Response: `SymptomLogOut` 201
- RBAC: PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN, SUPER_ADMIN
- AI_SERVICE blocked (403), CLINIC_ADMIN blocked (403)
- Audit: `action="log_symptom"`

**`GET /patients/{patient_id}/symptoms`**
- Query: `limit=20` (max 100), `offset=0`
- Response: `{"patient_id": str, "total": int, "items": [SymptomLogOut]}`
- RBAC: same as above
- Order: newest first

### Medication

**`POST /patients/{patient_id}/medications`**
- Request: `MedicationCreate` `{"name": "str", "dose": "str (optional)", "note": "str (optional)"}`
- Response: `MedicationOut` 201
- RBAC: PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN, SUPER_ADMIN
- AI_SERVICE blocked (403)
- **SAFETY NOTE**: AI must NEVER add/modify medications — strictly blocked. This is enforced at the RBAC layer.
- Audit: `action="add_medication"`

**`GET /patients/{patient_id}/medications`**
- Query: `limit=20`, `offset=0`
- Response: `{"patient_id": str, "total": int, "items": [MedicationOut]}`
- Returns only non-deleted (soft-delete aware)
- RBAC: PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN, SUPER_ADMIN

**`DELETE /patients/{patient_id}/medications/{med_id}`**
- Response: 204
- Soft-delete only (set `deleted_at` timestamp)
- RBAC: PATIENT (own record only), INTERNAL_ADMIN, SUPER_ADMIN
- DOCTOR: blocked from deleting (clinical safety — doctor should not remove patient's medication history)
- Audit: `action="delete_medication"`

---

## Schemas

**`backend/app/schemas/symptom.py`:**
```python
class SymptomLogCreate(BaseModel):
    description: str
    severity: int | None = None  # 0-10
    reported_at: datetime | None = None  # default now

class SymptomLogOut(BaseModel):
    id: str
    patient_id: str
    description: str
    severity: int | None
    reported_at: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

**`backend/app/schemas/medication.py`:**
```python
class MedicationCreate(BaseModel):
    name: str
    dose: str | None = None
    note: str | None = None

class MedicationOut(BaseModel):
    id: str
    patient_id: str
    name: str
    dose: str | None
    note: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

---

## Service Layer

**`backend/app/services/symptom_log.py`:**
- `create_symptom(db, *, patient_id, data: dict) -> SymptomLog`
- `list_symptoms(db, *, patient_id, limit, offset) -> tuple[int, list[SymptomLog]]`

**`backend/app/services/medication.py`:**
- `add_medication(db, *, patient_id, data: dict) -> Medication`
- `list_medications(db, *, patient_id, limit, offset) -> tuple[int, list[Medication]]`
- `delete_medication(db, *, patient_id, med_id, requester_id) -> None` (soft-delete, 404 if not found)

---

## Test Requirements (minimum 16 tests)

**Symptom Log:**
1. `test_patient_creates_symptom_log` → 201
2. `test_patient_cannot_create_symptom_for_another_patient` → 403
3. `test_doctor_creates_symptom_with_consent` → 201
4. `test_ai_service_cannot_create_symptom` → 403
5. `test_patient_lists_own_symptoms` → 200, items list
6. `test_symptom_severity_validation` → 422 if severity > 10

**Medication:**
7. `test_patient_adds_medication` → 201
8. `test_patient_cannot_add_medication_for_another_patient` → 403
9. `test_ai_service_cannot_add_medication` → 403 (critical safety check)
10. `test_patient_lists_medications` → 200
11. `test_soft_delete_medication` → 204, record not in list after delete
12. `test_doctor_cannot_delete_medication` → 403
13. `test_delete_nonexistent_medication` → 404
14. `test_deleted_medication_not_in_list` → 200, deleted item absent
15. `test_doctor_lists_medications_with_consent` → 200
16. `test_unauthenticated_cannot_create_symptom` → 401

---

## Acceptance Criteria

- [ ] All 5 endpoints implemented with correct RBAC
- [ ] AI_SERVICE blocked from all write endpoints (critical safety)
- [ ] DOCTOR cannot delete medications
- [ ] Soft-delete: `deleted_at` set, record excluded from GET list
- [ ] Audit records on create/delete
- [ ] 16 tests pass
- [ ] Zero regressions (315 baseline → 331+ total)
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

*Task Card issued: 2026-06-18 18:20 GMT+7 | Coordinator: OpenClaw*
