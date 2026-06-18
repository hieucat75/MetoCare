# T18 Implementation Report — Nutrition Log Model + API

**TASK_ID:** T18  
**Branch:** `feature/t18-nutrition-log-api`  
**Implementer:** Antigravity (subagent)  
**Completed:** 2026-06-18 GMT+7  
**Status:** ✅ READY FOR CODEX REVIEW

---

## Summary

Implemented MVP P0 use case #5: "Ghi bữa ăn đơn giản." Full nutrition logging API for Metocare, covering model, migration, schemas, service layer, API endpoints, and tests.

---

## Files Created / Modified

| File | Type | Description |
|------|------|-------------|
| `backend/app/models/nutrition.py` | NEW | `NutritionLog` ORM model |
| `backend/app/models/__init__.py` | MODIFIED | Registered `NutritionLog` |
| `backend/alembic/versions/t18_add_nutrition_log.py` | NEW | Migration (rev `t18_add_ntrl`, down_rev `t4_m9_add_sdel`) |
| `backend/app/schemas/nutrition.py` | NEW | `NutritionLogCreate`, `NutritionLogOut` |
| `backend/app/schemas/__init__.py` | MODIFIED | Exported new schemas |
| `backend/app/services/nutrition_log.py` | NEW | `create_log()`, `list_logs()` |
| `backend/app/api/v1/routes/patients.py` | MODIFIED | 2 new endpoints |
| `backend/tests/api/test_nutrition_log_api.py` | NEW | 10 tests |

---

## Design Decisions

### Model
- `NutritionLog` extends `UUIDPrimaryKey + TimestampMixin + Base` (consistent with `SymptomLog` pattern)
- No `SoftDeleteMixin` — meal logs don't need delete in MVP; consistent with `SymptomLog`
- `logged_at` uses `DateTime(timezone=True)` for explicit timezone handling

### Migration
- Revision `t18_add_ntrl`, down_revision `t4_m9_add_sdel`
- Index on `patient_id` created via `op.create_index` with `op.f()` for portable naming
- Separate index step (not inline `index=True` in Column) avoids SQLite "index already exists" issue

### Schemas
- `meal_type` validated via regex pattern: `^(breakfast|lunch|dinner|snack)$`
- `calories_kcal` bounded: `ge=0, le=99999`
- `description` bounded: `min_length=1, max_length=4096`
- `logged_at` optional — defaults to `utcnow()` in service layer

### RBAC
- Reuses existing `_check_write_access` / `_check_read_access` helpers from T15
- `AI_SERVICE` blocked via `_BLOCKED_WRITE_ROLES` frozenset
- `PATIENT` own-only enforced via `PatientProfile.user_id` comparison
- `DOCTOR` consent-gated via `require_access()`
- `INTERNAL_ADMIN` / `SUPER_ADMIN` unrestricted

### Audit
- `create_nutrition_log` emits `AuditLog` with `action="log_nutrition"`, `resource_type="nutrition_log"`
- Consistent with T15 symptom/medication audit pattern

---

## Validation Results

```
alembic upgrade head    → ✅ t18_add_ntrl applied cleanly
ruff check .            → ✅ All checks passed (1 I001 auto-fixed)
pytest tests/ --tb=short
  → 390 passed, 1 skipped (baseline: 380; +10 new tests)
```

---

## Test Coverage (10/10)

| # | Test | Result |
|---|------|--------|
| 1 | `test_patient_logs_nutrition` | ✅ 201 |
| 2 | `test_patient_cannot_log_for_another_patient` | ✅ 403 |
| 3 | `test_doctor_logs_with_consent` | ✅ 201 |
| 4 | `test_ai_service_cannot_log_nutrition` | ✅ 403 |
| 5 | `test_patient_lists_nutrition_logs` | ✅ 200 |
| 6 | `test_nutrition_log_ordered_newest_first` | ✅ newest first |
| 7 | `test_unauthenticated_cannot_log_nutrition` | ✅ 401 |
| 8 | `test_log_with_all_optional_fields` | ✅ 201, all fields |
| 9 | `test_log_minimal_fields` | ✅ 201, nulls |
| 10 | `test_pagination_limit` | ✅ respects limit |

---

## Acceptance Criteria Checklist

- [x] `NutritionLog` model created
- [x] Migration created and runs cleanly (`alembic upgrade head`)
- [x] `POST /patients/{id}/nutrition` implemented with RBAC
- [x] `GET /patients/{id}/nutrition` implemented with pagination, ordered newest first
- [x] AI_SERVICE blocked (403)
- [x] Audit on create (`action="log_nutrition"`)
- [x] 10 tests pass
- [x] Zero regressions (380 baseline → 390 total)
- [x] Ruff clean

---

*Report generated: 2026-06-18 GMT+7 | Implementer: Antigravity*
