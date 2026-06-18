# T18 Task Card — Nutrition Log Model + API

**TASK_ID:** T18  
**LABEL:** Nutrition Log — Model + Migration + CRUD API + Tests  
**Branch:** `feature/t18-nutrition-log-api`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

MVP P0 use case #5: "Ghi bữa ăn đơn giản + nhận coaching lối sống." No nutrition model exists. This sprint creates the model, migration, API, and tests.

---

## Scope

### ALLOWED_FILES

- `backend/app/models/nutrition.py` — NEW: `NutritionLog` model
- `backend/app/models/__init__.py` — register new model
- `backend/alembic/versions/t18_add_nutrition_log.py` — NEW migration
- `backend/app/schemas/nutrition.py` — NEW: `NutritionLogCreate`, `NutritionLogOut`
- `backend/app/schemas/__init__.py` — export new schemas
- `backend/app/services/nutrition_log.py` — NEW: service functions
- `backend/app/api/v1/routes/patients.py` — add 2 new endpoints
- `backend/tests/api/test_nutrition_log_api.py` — NEW: tests
- `docs/agent/T18_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- Other models
- Other routes
- Other migrations

---

## Model Design

`backend/app/models/nutrition.py`:

```python
class NutritionLog(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "nutrition_logs"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True, nullable=False)
    meal_type: Mapped[str | None] = mapped_column(String(32))  # "breakfast"|"lunch"|"dinner"|"snack"
    description: Mapped[str] = mapped_column(Text, nullable=False)  # free text description
    calories_kcal: Mapped[int | None] = mapped_column(Integer)  # optional estimate
    logged_at: Mapped[dt.datetime] = mapped_column(nullable=False)  # when the meal was eaten
```

---

## Migration

`backend/alembic/versions/t18_add_nutrition_log.py`:
- Revision: `t18_add_ntrl`
- Down revision: `t4_m9_add_sdel` (the latest existing migration)
- Create table `nutrition_logs` with columns above
- Downgrade: drop table

Run after creating: `alembic upgrade head`

---

## API Design

### `POST /patients/{patient_id}/nutrition`

- Request: `NutritionLogCreate` `{"description": "str", "meal_type": "breakfast|lunch|dinner|snack (optional)", "calories_kcal": int (optional), "logged_at": datetime (optional, default now)}`
- Response: `NutritionLogOut` 201
- RBAC: PATIENT (own), DOCTOR (consent-gated), INTERNAL_ADMIN, SUPER_ADMIN
- AI_SERVICE blocked (403)
- Audit: `action="log_nutrition"`

### `GET /patients/{patient_id}/nutrition`

- Query: `limit=20` (max 100), `offset=0`
- Response: `{"patient_id": str, "total": int, "items": [NutritionLogOut]}`
- Order: newest first (by `logged_at` desc)
- RBAC: same as POST

---

## Schemas

```python
class NutritionLogCreate(BaseModel):
    description: str
    meal_type: str | None = None
    calories_kcal: int | None = None
    logged_at: datetime | None = None  # default now

class NutritionLogOut(BaseModel):
    id: str
    patient_id: str
    description: str
    meal_type: str | None
    calories_kcal: int | None
    logged_at: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

---

## Service Layer

`backend/app/services/nutrition_log.py`:
- `create_log(db, *, patient_id, data: dict) -> NutritionLog`
- `list_logs(db, *, patient_id, limit, offset) -> tuple[int, list[NutritionLog]]`

---

## Test Requirements (minimum 10 tests)

1. `test_patient_logs_nutrition` → 201
2. `test_patient_cannot_log_for_another_patient` → 403
3. `test_doctor_logs_with_consent` → 201
4. `test_ai_service_cannot_log_nutrition` → 403
5. `test_patient_lists_nutrition_logs` → 200, items list
6. `test_nutrition_log_ordered_newest_first` → first item has latest logged_at
7. `test_unauthenticated_cannot_log_nutrition` → 401
8. `test_log_with_all_optional_fields` → 201, all fields present in response
9. `test_log_minimal_fields` → 201, optional fields null
10. `test_pagination_limit` → 200, respects limit param

---

## Acceptance Criteria

- [ ] `NutritionLog` model created
- [ ] Migration created and runs cleanly (`alembic upgrade head`)
- [ ] `POST /patients/{id}/nutrition` implemented with RBAC
- [ ] `GET /patients/{id}/nutrition` implemented with pagination, ordered newest first
- [ ] AI_SERVICE blocked (403)
- [ ] Audit on create
- [ ] 10 tests pass
- [ ] Zero regressions (380 baseline → 390+ total)
- [ ] Ruff clean

---

## Validation Commands

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
alembic upgrade head
ruff check .
python -m pytest tests/ --tb=short
```

---

## Required Final Status

```
READY FOR CODEX REVIEW
```

---

*Task Card issued: 2026-06-18 18:55 GMT+7 | Coordinator: OpenClaw*
