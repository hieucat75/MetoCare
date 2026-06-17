# T8 Implementation Report — AI Routes Auth + RBAC + API Tests

**TASK_ID:** T8  
**Branch:** `feature/t8-ai-routes-rbac`  
**Implementer:** Antigravity  
**Date:** 2026-06-18 GMT+7  
**Status:** READY FOR CODEX REVIEW

---

## Summary

All 3 AI consumer routes (`/ai/chat`, `/ai/triage`, `/ai/metabolic-score`) now
require a valid JWT and enforce role-based access control.  Anonymous callers
receive 401; `AI_SERVICE` receives 403.

---

## Changes Made

### `backend/app/api/v1/routes/ai.py` (modified)

**Before:** Routes were unauthenticated. `_cost_subject()` did a best-effort
token decode to identify the caller for cost-guard purposes but did NOT enforce
authentication. Anonymous callers could access all AI endpoints.

**After:**
- Removed `_cost_subject()` helper entirely
- Removed `from app.core.security import decode_token` and `Request` imports
  (no longer needed)
- Added `from app.api.deps import CurrentUser, require_roles`
- Added `from app.models.user import UserRole`
- Defined `_AI_CONSUMER_ROLES` tuple:
  `(PATIENT, DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN)`
- Created `_require_ai_consumer = require_roles(*_AI_CONSUMER_ROLES)` shared
  dependency instance
- All 3 route handlers now accept `user: CurrentUser = Depends(_require_ai_consumer)`
- `user.id` is passed as `user_id` to `ai_assistant.respond()` (rate-limit subject)
- `LLMRateLimitError → 429` handling preserved unchanged

### `backend/tests/api/test_ai_routes_api.py` (new file)

12 API-level test cases:

| # | Test | Route | Expected |
|---|------|-------|----------|
| 1 | `test_patient_can_chat` | POST /ai/chat | 200, has `text` field |
| 2 | `test_doctor_can_chat` | POST /ai/chat | 200 |
| 3 | `test_ai_service_cannot_chat` | POST /ai/chat | 403 |
| 4 | `test_unauthenticated_cannot_chat` | POST /ai/chat | 401 |
| 5 | `test_chat_blocked_message_returns_blocked_true` | POST /ai/chat | 200, `blocked=True` |
| 6 | `test_patient_can_triage` | POST /ai/triage | 200, has `risk_level` |
| 7 | `test_doctor_can_triage` | POST /ai/triage | 200 |
| 8 | `test_ai_service_cannot_triage` | POST /ai/triage | 403 |
| 9 | `test_unauthenticated_cannot_triage` | POST /ai/triage | 401 |
| 10 | `test_patient_can_score` | POST /ai/metabolic-score | 200, has `score` + `band` |
| 11 | `test_ai_service_cannot_score` | POST /ai/metabolic-score | 403 |
| 12 | `test_unauthenticated_cannot_score` | POST /ai/metabolic-score | 401 |

**Test #5 implementation note:** The mock LLM provider returns safe canned
responses that never trigger the output guardrail directly. To test `blocked=True`,
test #5 injects an `_UnsafeMockProvider` (via `monkeypatch`) that returns a
prohibited diagnosis assertion string. The gateway's output guardrail fires on
this unsafe text and sets `blocked=True` in the ChatResponse. This matches the
same pattern used in `tests/test_llm_gateway.py::test_gateway_blocks_unsafe_output`.

**Fixtures:** `patient_setup`, `doctor_setup`, `ai_service_setup` — each creates
a DB user with the appropriate `UserRole` and mints a JWT via `create_access_token`.

### `backend/tests/test_api.py` (modified)

5 pre-existing AI route smoke tests were calling endpoints without auth.
Updated to pass `patient` fixture headers:
- `test_ai_chat_is_guardrailed_and_has_disclaimer`
- `test_ai_chat_red_flag_escalates`
- `test_ai_chat_medication_query_redirects`
- `test_triage_endpoint_red_flag`
- `test_metabolic_score_endpoint`

Also reformatted long lines to pass `ruff` E501 checks.

### `backend/tests/test_llm_gateway.py` (modified)

`test_gateway_cost_cap_maps_to_429` was calling `/ai/chat` without auth.
Updated to pass `patient` fixture headers. Reformatted long lines.

---

## RBAC Matrix

| Role | /ai/chat | /ai/triage | /ai/metabolic-score |
|------|----------|------------|---------------------|
| PATIENT | ✅ 200 | ✅ 200 | ✅ 200 |
| DOCTOR | ✅ 200 | ✅ 200 | ✅ 200 |
| CLINIC_ADMIN | ✅ 200 | ✅ 200 | ✅ 200 |
| INTERNAL_ADMIN | ✅ 200 | ✅ 200 | ✅ 200 |
| SUPER_ADMIN | ✅ 200 | ✅ 200 | ✅ 200 |
| AI_SERVICE | ❌ 403 | ❌ 403 | ❌ 403 |
| Anonymous | ❌ 401 | ❌ 401 | ❌ 401 |

---

## Test Results

```
248 passed, 1 skipped, 14 warnings in 5.13s
```

**Baseline:** 236 passed → **+12 new tests** = 248 total ✅

Ruff: `All checks passed!` ✅

---

## Domain Code: Untouched

As required by the task card, the following files were NOT modified:
- `backend/app/domain/triage.py`
- `backend/app/domain/metabolic_score.py`
- `backend/app/services/ai_assistant.py`
- `backend/app/domain/guardrails.py`
- All migration files
- All model files

---

## Safety Invariants

- AI guardrail in `ai_assistant.py` is NOT bypassed or weakened
- `blocked=True` responses pass through to client unchanged
- No new LLM calls added
- No consent bypass added for AI consumer routes
- Triage red-flag engine continues to fire correctly (test #6 verifies `risk_level`)

---

## Commit

```
feat(t8): AI routes auth + RBAC hardening + 12 API tests
Branch: feature/t8-ai-routes-rbac
Commit: 11059a6
```

---

*Report generated: 2026-06-18 GMT+7 | Implementer: Antigravity*
