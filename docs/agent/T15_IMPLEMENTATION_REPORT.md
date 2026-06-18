# T15 Implementation Report — Symptom Log + Medication CRUD API

**TASK_ID:** T15  
**Branch:** `feature/t15-symptom-medication-api`  
**Status:** READY FOR CODEX REVIEW  
**Implemented:** 2026-06-18 GMT+7  
**Implementer:** Claude Code (subagent)

---

## Summary

Implemented 5 new REST endpoints for symptom logging and medication management, with full RBAC enforcement including the critical AI_SERVICE block on all write operations and the DOCTOR block on medication deletion.

---

## Files Created

| File | Purpose |
|------|---------|
| `backend/app/schemas/symptom.py` | `SymptomLogCreate`, `SymptomLogOut` (with `created_at`) |
| `backend/app/schemas/medication.py` | `MedicationCreate`, `MedicationOut` (with `created_at`) |
| `backend/app/services/symptom_log.py` | `create_symptom()`, `list_symptoms()` |
| `backend/app/services/medication.py` | `add_medication()`, `list_medications()`, `delete_medication()` |
| `backend/tests/api/test_symptom_medication_api.py` | 16 API tests |
| `docs/agent/T15_IMPLEMENTATION_REPORT.md` | This file |

---

## Files Modified

| File | Change |
|------|--------|
| `backend/app/api/v1/routes/patients.py` | Added 5 new endpoints + RBAC helpers |
| `backend/app/schemas/__init__.py` | Updated imports to use new schema modules |

---

## Endpoints Implemented

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| `POST` | `/patients/{patient_id}/symptoms` | 201 | Log symptom |
| `GET` | `/patients/{patient_id}/symptoms` | 200 | List symptoms (paginated, newest first) |
| `POST` | `/patients/{patient_id}/medications` | 201 | Add medication |
| `GET` | `/patients/{patient_id}/medications` | 200 | List active medications (paginated) |
| `DELETE` | `/patients/{patient_id}/medications/{med_id}` | 204 | Soft-delete medication |

---

## RBAC Matrix

| Role | POST symptom | GET symptoms | POST medication | GET medications | DELETE medication |
|------|-------------|-------------|----------------|----------------|-------------------|
| PATIENT (own) | ✅ | ✅ | ✅ | ✅ | ✅ |
| PATIENT (other) | ❌ 403 | ❌ 403 | ❌ 403 | ❌ 403 | ❌ 403 |
| DOCTOR (w/ consent) | ✅ | ✅ | ✅ | ✅ | ❌ 403 (clinical safety) |
| INTERNAL_ADMIN | ✅ | ✅ | ✅ | ✅ | ✅ |
| SUPER_ADMIN | ✅ | ✅ | ✅ | ✅ | ✅ |
| AI_SERVICE | ❌ 403 | ❌ 403 | ❌ 403 (CRITICAL) | ❌ 403 | ❌ 403 |
| CLINIC_ADMIN | ❌ 403 | ❌ 403 | ❌ 403 | ❌ 403 | ❌ 403 |
| Unauthenticated | ❌ 401 | ❌ 401 | ❌ 401 | ❌ 401 | ❌ 401 |

---

## Key Design Decisions

### 1. New Schema Files vs. Extending `clinical.py`
Created separate `symptom.py` and `medication.py` schema files as specified in the task card. The new `*Out` schemas include `created_at` (absent from the existing `clinical.py` versions). `schemas/__init__.py` updated to import from the new files.

### 2. RBAC Helper (`_check_write_access`)
Extracted shared RBAC logic into a route-level helper function. The DELETE endpoint applies an additional doctor-specific check *before* calling the general helper, making the clinical safety intent explicit and readable.

### 3. Soft-Delete
`delete_medication()` sets `deleted_at = utcnow()`. The `list_medications()` query filters on `deleted_at IS NULL`. Idempotent (repeated deletes on already-deleted records are no-ops).

### 4. Audit Logging
All write operations (`log_symptom`, `add_medication`, `delete_medication`) produce `AuditLog` entries. Audit `flush()` happens inside the service commit flow.

---

## Test Results

```
tests/api/test_symptom_medication_api.py ................  [100%]
16 passed in 0.18s
```

Full suite:
```
331 passed, 1 skipped in 7.02s
```

Baseline: 315 → 331 (+16, zero regressions).

---

## Validation

```
ruff check .: All checks passed!
pytest tests/: 331 passed, 1 skipped
```

---

## Status

```
READY FOR CODEX REVIEW
```
