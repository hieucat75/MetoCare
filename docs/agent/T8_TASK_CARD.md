# T8 Task Card — AI Routes Auth + RBAC + API Tests

**TASK_ID:** T8  
**LABEL:** AI Routes (/ai/chat, /ai/triage, /ai/metabolic-score) — Auth + RBAC Hardening + API Tests  
**Branch:** `feature/t8-ai-routes-rbac`  
**Base branch:** `main`  
**Repo:** `/Users/pth/Developer/Metocare`  
**Implementer:** Antigravity  
**Coordinator:** OpenClaw  
**Status:** IN PROGRESS  
**Issued:** 2026-06-18 GMT+7

---

## Objective

The 3 AI routes in `backend/app/api/v1/routes/ai.py` currently use no auth (`decode_token` manual fallback only, not enforced). This sprint:
1. Adds **required JWT authentication** to all 3 AI routes
2. Applies **role-based access control** per route
3. Adds **`tests/api/test_ai_routes_api.py`** with API-level tests

Domain code (`triage.py`, `metabolic_score.py`, `ai_assistant.py`) is STABLE — do NOT touch.

---

## Scope

### ALLOWED_FILES

- `backend/app/api/v1/routes/ai.py` — auth + RBAC
- `backend/tests/api/test_ai_routes_api.py` — NEW file, all API tests
- `docs/agent/T8_IMPLEMENTATION_REPORT.md` — NEW, final report

### DO NOT TOUCH

- `backend/app/domain/triage.py`
- `backend/app/domain/metabolic_score.py`
- `backend/app/services/ai_assistant.py`
- `backend/app/domain/guardrails.py`
- Any existing passing tests
- Any migration files
- `backend/app/models/`
- `backend/app/core/feature_flags.py`

---

## RBAC Requirements

### Current state (broken):
All 3 routes are unauthenticated — `_cost_subject()` does a best-effort token decode but does NOT enforce auth. Anonymous callers can access all AI endpoints.

### Required RBAC per endpoint:

| Endpoint | Allowed Roles | Notes |
|----------|---------------|-------|
| `POST /ai/chat` | PATIENT, DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN | Auth required. AI_SERVICE blocked. |
| `POST /ai/triage` | PATIENT, DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN | Auth required. AI_SERVICE blocked. |
| `POST /ai/metabolic-score` | PATIENT, DOCTOR, CLINIC_ADMIN, INTERNAL_ADMIN, SUPER_ADMIN | Auth required. AI_SERVICE blocked. |

**AI_SERVICE must NOT access any AI consumer routes** (it operates via AISession API, not direct AI routes).

### Implementation:
- Replace `_cost_subject()` manual decode with `CurrentUser = Depends(require_roles(...))` 
- Pass `user.id` as the cost/rate-limit subject instead of decoded sub
- Remove the `_cost_subject` helper entirely
- Keep the existing rate-limit/cost guard logic (just wire the user id from `user.id`)
- Preserve `LLMRateLimitError` → 429 handling

---

## Test Requirements

Create `backend/tests/api/test_ai_routes_api.py`:

### Fixtures (follow T7 pattern):
- `patient_setup` — PATIENT user + JWT
- `doctor_setup` — DOCTOR user + JWT  
- `ai_service_setup` — AI_SERVICE user + JWT

### Test cases (minimum 12):

**Chat (`POST /ai/chat`):**
1. `test_patient_can_chat` → 200, has `text` field
2. `test_doctor_can_chat` → 200
3. `test_ai_service_cannot_chat` → 403
4. `test_unauthenticated_cannot_chat` → 401
5. `test_chat_blocked_message_returns_blocked_true` → 200, `blocked=True` (use a flagged phrase)

**Triage (`POST /ai/triage`):**
6. `test_patient_can_triage` → 200, has `risk_level` field
7. `test_doctor_can_triage` → 200
8. `test_ai_service_cannot_triage` → 403
9. `test_unauthenticated_cannot_triage` → 401

**Metabolic Score (`POST /ai/metabolic-score`):**
10. `test_patient_can_score` → 200, has `score` field and `band`
11. `test_ai_service_cannot_score` → 403
12. `test_unauthenticated_cannot_score` → 401

### Payload helpers (use minimal valid payloads):
- Chat: `{"message": "Xin chào bác sĩ", "intent": null}`
- Triage: `{"symptom_text": "Đau đầu nhẹ", "vitals": [], "reported_severity": "mild"}`
- Metabolic score: `{"waist_cm": 85.0, "fasting_glucose": 5.5, "hba1c": null, "triglyceride": null, "hdl": null, "systolic_bp": null, "is_male": true}`

For `test_chat_blocked_message_returns_blocked_true`: use a phrase that triggers the safety guardrail. Check `app/domain/guardrails.py` for a known blocked phrase to use in the test.

---

## Acceptance Criteria

- [ ] All 3 AI routes require JWT auth (no anonymous access)
- [ ] AI_SERVICE blocked from all 3 routes (403)
- [ ] `_cost_subject()` helper removed; `user.id` used instead
- [ ] Rate limit / cost guard preserved with `user.id`
- [ ] LLMRateLimitError → 429 preserved
- [ ] All 12 test cases pass
- [ ] Zero existing tests broken (236 baseline → 248+ total)
- [ ] Ruff clean
- [ ] `docs/agent/T8_IMPLEMENTATION_REPORT.md` written

---

## Validation Commands

```bash
cd /Users/pth/Developer/Metocare/backend
source ../.venv/bin/activate
ruff check .
pytest tests/ --tb=short
```

Report: `N passed, N skipped, N warnings in Xs`

---

## Required Final Status

```
READY FOR CODEX REVIEW
```

Do NOT say: APPROVED / MERGE READY / SAFE TO MERGE

---

## Medical Safety Reminders

- AI guardrail in `ai_assistant.py` must NOT be bypassed or weakened
- Triage red-flag engine in `triage.py` must NOT be bypassed
- `blocked=True` responses from guardrail must pass through to client unchanged
- Do not add any new LLM calls
- Do not add consent bypass for AI consumer routes

---

*Task Card issued: 2026-06-18 05:12 GMT+7 | Coordinator: OpenClaw*
