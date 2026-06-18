# PA-05 Implementation Report — AI Patient-Safe Explanation Endpoint

**Branch:** `feature/pa05-ai-patient-explanation`  
**Date:** 2026-06-18  
**Author:** Claude Code (subagent PA-05)

---

## Summary

Implemented the `POST /api/v1/ai/explain` endpoint as specified. The endpoint is PATIENT-only, returns deterministic mock plain-language summaries in pilot mode, enforces patient ownership, and always includes a medical disclaimer.

---

## Implementation Details

### 1. Schemas (`backend/app/schemas/ai.py`)

Added at the end of the existing schemas file:

- **`ExplanationType`** (`StrEnum`): `metabolic_score`, `health_metric`, `lab_result`, `general_summary`
- **`SafetyLevel`** (`StrEnum`): `informational` (only valid pilot value)
- **`ExplainContext`**: Optional context fields (`metric_type`, `value`, `unit`, `score`, `trend`)
- **`AiExplainRequest`**: Request model with `patient_id`, `explanation_type`, `context`
- **`AiExplainResponse`**: Response model with `explanation_type`, `plain_language_summary`, `safety_level`, `disclaimer`, `generated_at`
- **`_DISCLAIMER`**: Module-level constant for the medical disclaimer string

All fields use Pydantic v2 conventions consistent with the existing codebase.

### 2. Route (`backend/app/api/v1/routes/ai.py`)

Added to the existing AI router (no new router created):

```
POST /api/v1/ai/explain
```

Key design decisions:
- **`_require_patient_only`**: Uses `require_roles(UserRole.PATIENT)` — all other roles (DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN, AI_SERVICE) are rejected with 403.
- **Ownership check**: Resolves `PatientProfile` by `user_id == caller.id`, then compares `profile.id` to `payload.patient_id`. Mismatch → 403.
- **Mock summaries**: `_MOCK_SUMMARIES` dict maps each `ExplanationType` to a friendly, jargon-free summary. For `health_metric` and `metabolic_score`, context values are interpolated when provided.
- **Disclaimer**: Imported from `app.schemas.ai._DISCLAIMER`, always included in response — cannot be None or empty.
- **`generated_at`**: Uses `datetime.now(tz=UTC)` (UP017-compliant).

### 3. Tests (`backend/tests/api/test_ai_patient_explain.py`)

11 tests covering all 8 acceptance criteria:

| Test | AC | Result |
|------|----|--------|
| `test_explain_patient_metabolic_score` | AC-1 | ✅ |
| `test_explain_patient_health_metric` | AC-2 | ✅ |
| `test_explain_doctor_forbidden` | AC-3 | ✅ |
| `test_explain_admin_forbidden` | AC-4 | ✅ |
| `test_explain_unauthenticated` | AC-5 | ✅ |
| `test_explain_wrong_patient_id` | AC-6 | ✅ |
| `test_explain_invalid_type` | AC-7 | ✅ |
| `test_explain_disclaimer_always_present[metabolic_score]` | AC-8 | ✅ |
| `test_explain_disclaimer_always_present[health_metric]` | AC-8 | ✅ |
| `test_explain_disclaimer_always_present[lab_result]` | AC-8 | ✅ |
| `test_explain_disclaimer_always_present[general_summary]` | AC-8 | ✅ |

Fixtures follow the same pattern as `test_ai_routes_api.py`: per-test random emails, no shared state, `db` session from conftest.

---

## Patterns Followed

- **Import ordering**: Ruff I001 auto-fixed; `_DISCLAIMER` sorted before `AiExplainRequest` etc.
- **Ownership pattern**: Same `select(PatientProfile).where(...user_id == user.id)` pattern as `/ai/triage` and `/ai/metabolic-score`.
- **Mock-only (pilot mode)**: No feature flag needed — the endpoint is inherently mock-only, consistent with existing routes that skip external calls.
- **No migration**: No new DB tables or columns.

---

## Quality Gate Results

```
ruff check app/ tests/          → 0 errors ✅
pytest tests/api/test_ai_patient_explain.py -v  → 11 passed ✅
pytest tests/ -q --tb=short     → 535 passed, 1 skipped ✅  (baseline 523 + 11 new + 1 inherited)
```

---

## Notes for Codex Review

1. `_DISCLAIMER` is a module-level constant in `app.schemas.ai` and imported into the route — ensures the disclaimer string is defined exactly once and never drifts between schema and route.
2. The RBAC dependency `_require_patient_only` is intentionally separate from `_require_ai_consumer` to make the PATIENT-only restriction explicit and auditable.
3. Mock summaries are realistic and friendly — no clinical jargon, no diagnostic language.
4. The `ExplainContext` model uses all-optional fields with `None` defaults; this avoids 422 errors when callers omit context entirely.
