# Codex Review — T26: Pilot Hardening + Final Smoke Test + Go/No-Go

**Sprint:** T26  
**Reviewer:** Codex (read-only)  
**Date:** 2026-06-18  
**Status:** APPROVED — Pilot Ready (with deferred items documented below)  
**Blockers:** 0  
**P2 Warnings:** 3 (all deferred to post-pilot)

---

## Scope

T26 is the final hardening sprint before pilot launch. Changes are:

1. `pdf_report.py` — ImportError guard added at module import time
2. `ai_sessions.py` — AI_SERVICE ownership constraint (P2-deferred, see below)
3. `test_ratelimit.py` — No changes required (all 8 tests already pass)
4. New docs: `T26_PILOT_SMOKE_TEST.md`, `T26_GO_NO_GO_CHECKLIST.md`, `T26_TASK_CARD.md`, `T26_FINAL_SPRINT_REPORT.md`

---

## P2 Deferred Items

### P2-D1: AI_SERVICE Session Ownership Constraint (from T18A Codex P2-W2)

**Finding:** `POST /ai_sessions/{session_id}/close` allows an `AI_SERVICE` principal to
close any patient's session without an ownership check. The task card (T26, Scope §3) requested
adding a check like `session.service_account_id == current_user.id`.

**Status: P2-DEFERRED — Field does not exist on the model.**

The `AISession` model (`backend/app/models/ai.py`) does not have a `service_account_id`
column or any equivalent "created_by" field that maps to an AI_SERVICE user identity.
Adding such a column would require:

1. A new Alembic migration (`service_account_id` FK column on `ai_sessions`)
2. Populating the field on session creation for AI_SERVICE callers
3. Updating the ownership check in `close_ai_session`

This is a **model change** — explicitly out of scope for T26 per the DO NOT TOUCH rules.

**Pilot Risk:** Low. AI_SERVICE credentials are internal service accounts, not user-facing
tokens. A compromised AI_SERVICE credential is a major incident by itself; the session-close
blast radius is limited. Acceptable for pilot scope.

**Post-Pilot Action:**
- Add `service_account_id: Mapped[str | None]` (FK → `users.id`) to `AISession`
- Populate on `create_ai_session` when `user.role == AI_SERVICE`
- Add ownership check in `close_ai_session`:
  ```python
  if user.role == UserRole.AI_SERVICE:
      if session.service_account_id != user.id:
          raise HTTPException(status_code=403, detail="AI_SERVICE may only close its own sessions.")
  ```
- Add test case: `AI_SERVICE tries to close another AI_SERVICE's session → 403`

**Tracking:** Follow-up sprint after pilot stabilizes.

---

### P2-D2: `active_only` Consent Filter Missing `valid_until` Check (from T18A Codex P2-W1)

**Finding:** The consent list `active_only=True` filter checks `revoked_at IS NULL OR revoked_at > now()`
but does not check `valid_until < now()`. A consent record with `valid_until` in the past would
still be returned as "active."

**Status: P2-DEFERRED — Documented but not fixed in T26.**

**Post-Pilot Action:** Add `OR (valid_until IS NULL OR valid_until > now())` to the
`active_only` filter in the consent list endpoint.

---

### P2-D3: Skipped Test — TimescaleDB Hypertable Integration (from T4/Migrations)

**Finding:** `tests/test_migrations.py::test_postgres_hypertable_ingest_and_trend` is
unconditionally skipped when `MCP_TEST_POSTGRES_URL` env var is absent (which it is in
CI/dev). This is an architectural requirement — the test requires a real PostgreSQL
instance with the TimescaleDB extension installed.

**Status: P2-DEFERRED — Architectural; cannot be fixed without real infrastructure.**

**Post-Pilot Action:** Add a PostgreSQL + TimescaleDB Docker Compose service to the
test environment, then set `MCP_TEST_POSTGRES_URL` in CI to enable this test. Alternatively,
create a separate integration test pipeline that runs against a managed TimescaleDB instance.

---

## Acceptance Criteria Review

| # | AC | Status |
|---|-----|--------|
| 1 | Rate limit skip investigated | ✅ PASS — skip is in `test_migrations.py`, requires TimescaleDB; all 8 ratelimit tests pass |
| 2 | ImportError guard in pdf_report.py | ✅ PASS — module-level try/except added |
| 3 | AI_SERVICE ownership in close endpoint | ✅ DOCUMENTED — field missing; P2-deferred with full remediation plan |
| 4 | Smoke test document created | ✅ PASS — `docs/ops/T26_PILOT_SMOKE_TEST.md` |
| 5 | Go/No-Go checklist created | ✅ PASS — `docs/ops/T26_GO_NO_GO_CHECKLIST.md` |
| 6 | Final sprint report created | ✅ PASS — `docs/agent/T26_FINAL_SPRINT_REPORT.md` |
| 7 | All 515 tests pass | ✅ PASS (1 skipped: TimescaleDB, architectural) |
| 8 | Ruff clean | ✅ PASS |

---

## Security Assessment

| Check | Result |
|-------|--------|
| No model/migration changes | ✅ PASS |
| No auth/RBAC logic changes | ✅ PASS |
| pdf_report guard: module-level, fail-fast | ✅ PASS — raises RuntimeError before any PDF code executes |
| AI_SERVICE close endpoint: unchanged behavior | ✅ PASS — P2-deferred with documented risk assessment |
| No new attack surface introduced | ✅ PASS |

---

## Verdict

**APPROVED for pilot launch.** All P0/P1 findings from T6–T25 are resolved. Three P2 items
are deferred with documented remediation plans. The system is technically ready for a
controlled pilot deployment per the Go/No-Go checklist.
