# Codex Review — T18: Nutrition Log Model + API

**Reviewer:** Codex (read-only)
**Branch:** `feature/t18-nutrition-log-api`
**Date:** 2026-06-18
**Repo:** `/Users/pth/Developer/Metocare`

---

## Result: ✅ APPROVE

**P1 Blockers:** None
**P2 Warnings:** 2 (non-blocking — see below)
**Security:** PASS
**Test Results:** 390/390 PASS (10 new, 0 regressions; 1 pre-existing skip)
**Acceptance Criteria:** 10/10 met

---

## Acceptance Criteria Verification

### AC1 ✅ — FK → `patient_profiles.id` (not `users.id`)

**File:** `backend/app/models/nutrition.py`

```python
patient_id: Mapped[str] = mapped_column(
    ForeignKey("patient_profiles.id"), index=True, nullable=False
)
```

FK target is `patient_profiles.id`. Confirmed correct. Migration also uses
`sa.ForeignKey("patient_profiles.id")` in the `upgrade()` DDL. ✅

---

### AC2 ✅ — Migration creates table cleanly; downgrade drops it

**File:** `backend/alembic/versions/t18_add_nutrition_log.py`

`upgrade()` creates `nutrition_logs` with all expected columns:
- `id` (PK, String 36)
- `patient_id` (FK → `patient_profiles.id`, NOT NULL)
- `meal_type` (String 32, nullable)
- `description` (Text, NOT NULL)
- `calories_kcal` (Integer, nullable)
- `logged_at` (DateTime(timezone=True), NOT NULL)
- `created_at` / `updated_at` (server_default CURRENT_TIMESTAMP)

Index `ix_nutrition_logs_patient_id` is created.

`downgrade()` drops the index first, then the table — correct order to avoid
FK/index constraint errors. ✅

---

### AC3 ✅ — POST /patients/{id}/nutrition → 201 with RBAC

**File:** `backend/app/api/v1/routes/patients.py` (T18 section)

- Route: `POST /{patient_id}/nutrition`, `status_code=201`
- RBAC enforced via `_check_write_access()` which blocks `AI_SERVICE` and
  `CLINIC_ADMIN`, enforces patient ownership, and gates doctors on consent.
- Audit record emitted with `action="log_nutrition"`, `resource_type="nutrition_log"`.
- Returns `NutritionLogOut` via `model_validate`. ✅

---

### AC4 ✅ — GET → paginated, ordered by `logged_at DESC`

**File:** `backend/app/services/nutrition_log.py`

```python
.order_by(NutritionLog.logged_at.desc())
```

Ordering is explicitly on `logged_at`, not `created_at`. Pagination via
`limit` + `offset` with total count returned as a separate scalar query. ✅

---

### AC5 ✅ — AI_SERVICE → 403 on both endpoints

`_check_write_access()` (used by POST) and `_check_read_access()` (used by GET)
both check `requester.role in _BLOCKED_WRITE_ROLES` which includes
`UserRole.AI_SERVICE`. Both endpoints call these guards before any data access.

Note: `_check_read_access` is a thin wrapper that delegates to `_check_write_access`
(the comment "also blocks AI_SERVICE for read" is technically redundant since
`AI_SERVICE` was already in `_BLOCKED_WRITE_ROLES`, but the behavior is correct). ✅

---

### AC6 ✅ — PATIENT cross-patient → 403

`_check_write_access()` for `UserRole.PATIENT`:
```python
profile = db.get(PatientProfile, patient_id)
if profile is None or profile.user_id != requester.id:
    raise HTTPException(status_code=403, ...)
```

Own-patient check enforced. Test 2 (`test_patient_cannot_log_for_another_patient`)
covers this. ✅

---

### AC7 ✅ — Audit record on create (`action="log_nutrition"`)

Route calls `audit.record(... action="log_nutrition", resource_type="nutrition_log", resource_id=record.id ...)`.
`audit.record()` does a `db.flush()` (not commit), then the route does `db.commit()`
to persist both the NutritionLog (already committed by service) and the AuditLog.
Pattern is consistent with T15 symptom/medication routes. ✅

---

### AC8 ✅ — `logged_at` defaults to `utcnow()` when not provided

**File:** `backend/app/services/nutrition_log.py`

```python
logged_at: dt.datetime = data.get("logged_at") or utcnow()
```

`utcnow()` from `app.core.clock` returns `dt.datetime.now(dt.UTC).replace(tzinfo=None)`
— a naive UTC datetime, consistent with the project-wide naive-UTC convention
documented in `clock.py`. The schema field is `logged_at: dt.datetime | None = None`,
so an absent field becomes `None` in `data`, triggering the `or utcnow()` fallback. ✅

---

### AC9 ✅ — Optional fields correctly nullable in DB + schema

**Model:** `meal_type: Mapped[str | None]`, `calories_kcal: Mapped[int | None]`

**Schema:** `meal_type: str | None = Field(None, ...)`, `calories_kcal: int | None = Field(None, ...)`

**Migration:** both columns defined `nullable=True`.

Test 9 (`test_log_minimal_fields`) verifies the response returns `null` for both. ✅

---

### AC10 ✅ — 10 tests pass, 0 regressions

Test file covers:
1. `test_patient_logs_nutrition` — 201, field verification
2. `test_patient_cannot_log_for_another_patient` — 403
3. `test_doctor_logs_with_consent` — 201 with consent fixture
4. `test_ai_service_cannot_log_nutrition` — 403 POST
5. `test_patient_lists_nutrition_logs` — 200, correct structure
6. `test_nutrition_log_ordered_newest_first` — ordering by `logged_at DESC`
7. `test_unauthenticated_cannot_log_nutrition` — 401
8. `test_log_with_all_optional_fields` — 201, all fields present
9. `test_log_minimal_fields` — 201, optional fields null
10. `test_pagination_limit` — respects `limit` param

Baseline: 380. New total: 390. Delta: +10. No regressions. ✅

---

## P2 Warnings (Non-Blocking)

### ⚠️ W1 — No test for AI_SERVICE on GET endpoint

**AC5** states "AI_SERVICE → 403 on **both** endpoints." Test 4 only exercises
`POST /nutrition`. There is no test verifying `GET /patients/{id}/nutrition` also
returns 403 for `ai_service`. The code is correct (both routes call `_check_read_access`
which delegates to `_check_write_access`), but test coverage is asymmetric.

**Recommendation:** Add `test_ai_service_cannot_list_nutrition` covering the GET path.

---

### ⚠️ W2 — Tz-aware `logged_at` not coerced to naive UTC before insert

`clock.py` documents that the project stores **naive UTC** datetimes for SQLite
portability. `utcnow()` correctly strips tzinfo. However, when a caller supplies
an explicit `logged_at` (e.g. `"2026-06-18T07:30:00+00:00"`), the service passes
it through **without** calling `as_naive_utc()`:

```python
logged_at: dt.datetime = data.get("logged_at") or utcnow()
```

If `data["logged_at"]` is a tz-aware datetime (from Pydantic parsing), SQLAlchemy
with SQLite may emit a warning or behave differently than the naive-UTC path.
Tests pass (likely SQLite tolerates it), but this is inconsistent with the project
convention and could surface as a type mismatch on PostgreSQL.

**Recommendation:** Apply `as_naive_utc()` to the caller-supplied `logged_at`:
```python
from app.core.clock import as_naive_utc, utcnow
logged_at = as_naive_utc(data.get("logged_at")) or utcnow()
```

---

## Files Reviewed

| File | Status |
|------|--------|
| `backend/app/models/nutrition.py` | ✅ Clean |
| `backend/app/services/nutrition_log.py` | ✅ Clean (W2 noted) |
| `backend/app/api/v1/routes/patients.py` (T18 section) | ✅ Clean |
| `backend/alembic/versions/t18_add_nutrition_log.py` | ✅ Clean |
| `backend/app/schemas/nutrition.py` | ✅ Clean |
| `backend/app/models/__init__.py` | ✅ NutritionLog registered |
| `backend/app/schemas/__init__.py` | ✅ Exports updated |
| `backend/tests/api/test_nutrition_log_api.py` | ✅ 10 tests (W1 noted) |

---

## Summary

T18 is well-implemented and production-ready. All 10 acceptance criteria are met:
FK is correctly targeting `patient_profiles.id`, ordering is `logged_at DESC`,
the `utcnow()` default is correct, RBAC blocks AI_SERVICE on both endpoints,
audit logging fires on create, and optional fields are nullable end-to-end.
Two non-blocking P2 warnings noted: missing GET-path test for AI_SERVICE (test
coverage gap), and tz-aware `logged_at` not coerced to naive UTC on user-supplied
values (consistency issue, passes tests but deviates from project convention).
Neither blocks merge.
