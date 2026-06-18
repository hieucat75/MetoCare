# T19 Implementation Report — Triage Log Persistence + History API

**TASK_ID:** T19  
**Branch:** `feature/t19-triage-log-api`  
**Implementer:** Antigravity  
**Date:** 2026-06-18 GMT+7  
**Status:** READY FOR CODEX REVIEW

---

## Summary

Added triage result persistence and a history endpoint to MetoCare. When a PATIENT caller POSTs to `/ai/triage`, the result is now saved to a new `triage_logs` table. A new `GET /patients/{id}/triage-history` endpoint returns paginated history with RBAC enforcement.

---

## Files Changed

### New Files

| File | Purpose |
|------|---------|
| `backend/app/models/triage_log.py` | `TriageLog` ORM model (FK → patient_profiles) |
| `backend/alembic/versions/t19_add_triage_log.py` | Migration: create `triage_logs` table |
| `backend/app/schemas/triage_log.py` | `TriageLogOut`, `TriageLogHistoryResponse` |
| `backend/app/services/triage_log.py` | `save_triage()`, `get_history()` |
| `backend/tests/api/test_triage_log_api.py` | 10 API tests |
| `docs/agent/T19_IMPLEMENTATION_REPORT.md` | This report |

### Modified Files

| File | Change |
|------|--------|
| `backend/app/models/__init__.py` | Register `TriageLog` |
| `backend/app/schemas/__init__.py` | Export `TriageLogOut`, `TriageLogHistoryResponse` |
| `backend/app/api/v1/routes/ai.py` | Persist triage for PATIENT callers; added `db` dep to `assess()` |
| `backend/app/api/v1/routes/patients.py` | Added `GET /{patient_id}/triage-history` endpoint |

---

## Design Decisions

### Feature Flag
The `POST /ai/triage` route does **not** check `AI_TRIAGE` feature flag (the triage rule engine is deterministic, not LLM-based). Inspection confirmed the existing route calls `triage.assess()` directly without any flag check. No flag bypass needed for persistence tests.

### `red_flags` Storage
Stored as `json.dumps(result.red_flags)` in DB (NULL when empty list). Deserialized to `list[str]` via `@field_validator` in `TriageLogOut` — same pattern as `top_risks` in `RiskScoreOut`.

### Persistence Logic Pattern
Follows T13 exactly: check `user.role == UserRole.PATIENT.value`, look up `PatientProfile` via `user_id`, skip silently if no profile (e.g. DOCTOR callers).

### RBAC on History Endpoint
Reuses `_check_read_access()` helper from patients.py — same rules as all other patient data endpoints. `AI_SERVICE` and `CLINIC_ADMIN` blocked (403), DOCTOR requires consent, PATIENT restricted to own data.

---

## Validation Results

```
alembic upgrade head  → OK (t18_add_ntrl -> t19_add_triage_log)
ruff check .          → All checks passed!
pytest tests/         → 401 passed, 1 skipped (baseline: 391 → +10)
```

### T19 Tests (10/10)
```
tests/api/test_triage_log_api.py::test_triage_saved_for_patient                  PASSED
tests/api/test_triage_log_api.py::test_triage_not_saved_for_non_patient          PASSED
tests/api/test_triage_log_api.py::test_patient_reads_triage_history              PASSED
tests/api/test_triage_log_api.py::test_patient_cannot_read_another_patients_history PASSED
tests/api/test_triage_log_api.py::test_doctor_reads_history_with_consent         PASSED
tests/api/test_triage_log_api.py::test_admin_reads_any_history                   PASSED
tests/api/test_triage_log_api.py::test_ai_service_cannot_read_history            PASSED
tests/api/test_triage_log_api.py::test_empty_triage_history                      PASSED
tests/api/test_triage_log_api.py::test_red_flags_serialized_correctly            PASSED
tests/api/test_triage_log_api.py::test_triage_history_ordered_newest_first       PASSED
```

---

## Acceptance Criteria Checklist

- [x] `TriageLog` model created with correct FK → `patient_profiles.id`
- [x] Migration runs cleanly (`t18_add_ntrl` → `t19_add_triage_log`)
- [x] `POST /ai/triage` persists for PATIENT callers
- [x] `GET /patients/{id}/triage-history` with RBAC + pagination
- [x] `red_flags` serialized as JSON in DB, deserialized to list in response
- [x] AI_SERVICE blocked on history endpoint (403)
- [x] 10 tests pass (10/10)
- [x] Zero regressions (391 baseline → 401 total)
- [x] Ruff clean

---

*Report generated: 2026-06-18 | Implementer: Antigravity*
