# Codex Review — T8 AI Routes Auth + RBAC

**Branch:** `feature/t8-ai-routes-rbac`
**Reviewer:** Codex (read-only, subagent)
**Date:** 2026-06-18
**Commit:** `11059a6` (feat) + `3400f32` (docs)

---

## Result: ✅ APPROVE

**P1 Blockers:** None
**P2 Warnings:** 2 (minor — see below)
**Security:** PASS
**Test Results:** 248/248 PASS (12 new, 236 baseline)
**Acceptance Criteria:** 12/12 met

---

## Acceptance Criteria Verification

| # | Criterion | Status | Evidence |
|---|-----------|--------|---------|
| 1 | All 3 AI routes require JWT auth — unauthenticated → 401 | ✅ | `require_roles` chains through `current_user` which raises 401 on missing/invalid token; confirmed by `test_unauthenticated_cannot_*` (3 tests) |
| 2 | AI_SERVICE blocked from all 3 routes → 403 | ✅ | `_AI_CONSUMER_ROLES` explicitly excludes `UserRole.AI_SERVICE`; `require_roles` raises 403 for unlisted roles; confirmed by `test_ai_service_cannot_*` (3 tests) |
| 3 | `_cost_subject()` removed; `user.id` used as rate-limit subject | ✅ | `_cost_subject` and `decode_token` import gone; `ai_assistant.respond(..., user_id=user.id)` matches `respond(user_id: str = "anonymous")` signature |
| 4 | `LLMRateLimitError → 429` handling preserved | ✅ | `except LLMRateLimitError` block in `/chat` handler unchanged; `test_gateway_cost_cap_maps_to_429` passes |
| 5 | CLINIC_ADMIN allowed on all 3 routes | ✅ | `_AI_CONSUMER_ROLES` includes `UserRole.CLINIC_ADMIN`; RBAC matrix in report confirms 200 |
| 6 | Guardrail bypass not introduced — `ai_assistant.respond()` call unchanged | ✅ | `/chat` handler passes `payload.message`, `intent=payload.intent`, `user_id=user.id`; service layer untouched |
| 7 | `blocked=True` guardrail test asserts correctly | ✅ | `test_chat_blocked_message_returns_blocked_true` injects `_UnsafeMockProvider` via monkeypatch; pattern matches `DIAGNOSIS_ASSERTION_PATTERNS`; asserts `body["blocked"] is True` |
| 8 | Pre-existing tests updated correctly (not broken) | ✅ | 5 tests in `test_api.py` + 1 in `test_llm_gateway.py` pass patient fixture headers; no test logic changed |
| 9 | No regression from T7 baseline (236 → 248 passed) | ✅ | 248 passed, 1 skipped, 0 failures; net +12 new tests |
| 10 | Ruff clean | ✅ | "All checks passed!" |
| 11 | Medical safety: triage red-flag engine and AI guardrail not bypassed | ✅ | `triage.py`, `ai_assistant.py`, `guardrails.py` untouched; `test_triage_endpoint_red_flag` (emergency risk_level) and `test_ai_chat_red_flag_escalates` pass |
| 12 | No new LLM calls added | ✅ | Only `ai_assistant.respond()` call path; no direct LLM provider calls in route layer |

---

## Security Analysis

### Auth Enforcement: PASS

`require_roles(*_AI_CONSUMER_ROLES)` returns a FastAPI dependency that chains through `current_user`. The `current_user` dependency:

1. Rejects missing/null bearer → 401 `Missing bearer token.`
2. Rejects invalid/expired tokens (payload is None, type ≠ "access", no sub) → 401
3. Passes the decoded `role` to `_checker` in `require_roles`
4. `_checker` rejects any role not in `allowed` → 403

The flow is correct and has no bypasses. A valid token with `role="ai_service"` correctly hits the 403 branch because `"ai_service"` is not in `{r.value for r in _AI_CONSUMER_ROLES}`.

### RBAC Implementation: PASS

- `_AI_CONSUMER_ROLES` defined once as a module constant, reused via `_require_ai_consumer` across all 3 routes — no per-route drift risk.
- `require_roles` uses a deny-by-default model: only explicitly listed roles are allowed.
- The `allowed` set is constructed from `r.value` (string comparison), matching how `CurrentUser.role` is populated from the JWT `role` claim.

### Guardrail Integrity: PASS

- `ai_assistant.respond()` signature: `(user_text, *, intent, user_id)` — no security-relevant parameters added or removed.
- The guardrail chain (`check_input` → LLM → `check_output`) lives in the service layer, untouched by this PR.
- `blocked=True` responses propagate to the client correctly via `ChatResponse.blocked`.
- Test #5 (`test_chat_blocked_message_returns_blocked_true`) validates the end-to-end guardrail path at the API level.

### No Privilege Escalation: PASS

The previous `_cost_subject()` did a best-effort decode for cost tracking only — it was never an auth gate. Replacing it with the `require_roles` dependency is a strict upgrade: cost subject is now always a verified, authenticated `user.id`.

---

## P2 Warnings

### P2-1: `reset_gateway()` call in test #5 without cleanup

In `test_chat_blocked_message_returns_blocked_true`:

```python
monkeypatch.setattr("app.llm.gateway.get_provider", lambda: _UnsafeMockProvider())
from app.llm import reset_gateway
reset_gateway()
```

`reset_gateway()` reinitializes the module-level singleton. While `monkeypatch` restores `get_provider` after the test, the gateway singleton may remain in the reset state if other tests rely on it before the next lazy initialization. `test_llm_gateway.py` already does this same pattern and has a `teardown_module` to handle cleanup — but `test_ai_routes_api.py` has no equivalent teardown.

**Risk:** Low — test isolation via monkeypatch is generally sufficient in pytest-with-TestClient contexts, and the existing test suite passes at 248. No action required before merge; consider adding a fixture-scoped `reset_gateway()` in a follow-up.

### P2-2: Doctor RBAC test on `/ai/metabolic-score` not included

The test matrix covers:
- `/chat`: patient ✅, doctor ✅, AI_SERVICE ❌, unauth ❌
- `/triage`: patient ✅, doctor ✅, AI_SERVICE ❌, unauth ❌
- `/metabolic-score`: patient ✅, AI_SERVICE ❌, unauth ❌ — **doctor missing**

There is no `test_doctor_can_score` test. Given that DOCTOR is in `_AI_CONSUMER_ROLES` and the same `_require_ai_consumer` dependency is used for all 3 routes, the logic is correct. However, the test coverage matrix is asymmetric. Consider adding `test_doctor_can_score` in T9 or a test-coverage follow-up.

**Risk:** Cosmetic — no functional gap, just coverage asymmetry.

---

## Code Quality

- Module-level constant `_AI_CONSUMER_ROLES` and shared `_require_ai_consumer` dependency is idiomatic FastAPI. Single definition prevents inconsistency.
- Module docstring accurately describes the auth/RBAC contract for future readers.
- Fixtures in `test_ai_routes_api.py` use `os.urandom(4).hex()` for unique emails — correct for parallel test isolation.
- `_UnsafeMockProvider` in test file matches the guardrail pattern in `test_llm_gateway.py` — consistent approach.
- Import cleanup (removed `decode_token`, `Request`) is clean.

---

## Summary

T8 correctly hardens all 3 AI consumer routes with JWT authentication and role-based access control. The implementation is minimal, idiomatic, and does not touch any domain or guardrail logic. All 12 acceptance criteria are met, 248 tests pass, and no security regressions were found. Two minor P2 observations (gateway teardown in tests, missing doctor metabolic-score test) do not block merge.
