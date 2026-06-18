# T11 Task Card — Schema Consolidation: Remove Inline Schemas from Routes

**TASK_ID:** T11  
**LABEL:** Schema Consolidation — Move Inline Schemas out of Route Files  
**Branch:** `feature/t11-schema-consolidation`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

Route files should not define Pydantic schemas. Three inline schemas remain in route files after T10:

1. `ai_sessions.py` — `AISessionCreate`, `AISessionOut`, `AIClinicalRecommendationOut` (7-field thin version)
2. `admin.py` — `UnlockRequest` (minor, low priority)

This sprint moves them to the canonical `app/schemas/` layer and cleans up imports.

---

## Scope

### Items to Fix

**Item 1 — `ai_sessions.py` inline schemas (primary)**

`AISessionCreate` and `AISessionOut` are inline in the route. Move them to `backend/app/schemas/ai_session.py` (new file) or `backend/app/schemas/ai.py` if appropriate.

The 7-field `AIClinicalRecommendationOut` inline in `ai_sessions.py` must be **replaced** with the canonical 16-field version from `app.schemas.clinical`. Verify serialization with existing tests.

**Item 2 — `admin.py` inline `UnlockRequest`**

Move `UnlockRequest` to `backend/app/schemas/admin.py` (new file) or `backend/app/schemas/common.py`.

### ALLOWED_FILES

- `backend/app/api/v1/routes/ai_sessions.py` — remove inline classes, fix imports
- `backend/app/api/v1/routes/admin.py` — remove inline class, fix import
- `backend/app/schemas/ai_session.py` — NEW: `AISessionCreate`, `AISessionOut`
- `backend/app/schemas/admin.py` — NEW (or add to `common.py`): `UnlockRequest`
- `backend/app/schemas/__init__.py` — export new schemas
- `docs/agent/T11_IMPLEMENTATION_REPORT.md` — NEW

### DO NOT TOUCH

- Any test files (unless test imports break — fix only import paths)
- Domain files
- Model files
- Migration files
- `app/schemas/clinical.py` — do not modify, only import from it

---

## Acceptance Criteria

- [ ] No `class.*BaseModel` definitions remain in `app/api/v1/routes/ai_sessions.py`
- [ ] No `class.*BaseModel` definitions remain in `app/api/v1/routes/admin.py`
- [ ] `AISessionCreate`, `AISessionOut` defined in `app/schemas/ai_session.py` (or `ai.py`)
- [ ] `UnlockRequest` defined in `app/schemas/admin.py` (or `common.py`)
- [ ] `AIClinicalRecommendationOut` in `ai_sessions.py` uses canonical 16-field version from `schemas.clinical`
- [ ] All schemas exported from `app/schemas/__init__.py`
- [ ] Zero existing tests broken (277 baseline → 277 total, no regressions)
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

*Task Card issued: 2026-06-18 05:42 GMT+7 | Coordinator: OpenClaw*
