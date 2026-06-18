# T26 Task Card — Pilot Hardening + Final Smoke Test + Go/No-Go

**Branch:** `feature/t26-pilot-hardening`  
**Base:** `main` @ `29b5b5e`  
**Owner:** Claude Code  
**Sprint:** T26 (Final Sprint)  
**Date:** 2026-06-18  
**Status:** ✅ COMPLETE — Ready for Codex Review

---

## Objective

Final hardening sprint before pilot launch. Three fix items, two new operational documents,
and a formal Go/No-Go checklist.

---

## Scope

### 1. Rate Limit Smoke Test Investigation (P2 carry-over from T10)

**Finding:** The 1 skipped test is `test_postgres_hypertable_ingest_and_trend` in
`tests/test_migrations.py` (NOT in `test_ratelimit.py`). All 8 rate limit tests pass.

The skip is guarded by `@pytest.mark.skipif(not _PG_URL, ...)` — it requires a real
TimescaleDB PostgreSQL instance (`MCP_TEST_POSTGRES_URL` env var). This is an architectural
requirement that cannot be fixed without real infrastructure.

**Resolution:** Documented as P2-D3 in `docs/CODEX_REVIEW_T26.md`. No code change needed.

### 2. ImportError Guard in pdf_report.py (P2 from T24 Codex)

**File:** `backend/app/services/pdf_report.py`

Added a module-level `try/except ImportError` wrapper around a reportlab presence check.
On ImportError, raises `RuntimeError("reportlab is required for PDF export...")`.

The guard is at module import time, not inside the function, so it fails fast at startup
rather than at first PDF generation call.

### 3. AI_SERVICE Session Ownership Constraint (P2 from T18A Codex)

**File:** `backend/app/api/v1/routes/ai_sessions.py`

**Finding:** `AISession` model has no `service_account_id` field. Implementing the ownership
check requires a model change + migration — explicitly out of scope for T26.

**Resolution:** Documented as P2-D1 in `docs/CODEX_REVIEW_T26.md` with full remediation
plan and post-pilot action items.

### 4. Smoke Test Document

**File:** `docs/ops/T26_PILOT_SMOKE_TEST.md`  
All 26+ endpoint flows documented with role, expected status, and pass/fail status.

### 5. Go/No-Go Checklist

**File:** `docs/ops/T26_GO_NO_GO_CHECKLIST.md`  
Formal pilot readiness checklist covering Technical, Clinical Safety, and Operational items.

### 6. Final Sprint Report

**File:** `docs/agent/T26_FINAL_SPRINT_REPORT.md`  
Full project completion report covering T6–T26, all 515 tests, architecture summary, and
pilot readiness verdict.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/pdf_report.py` | Added ImportError guard |
| `docs/CODEX_REVIEW_T26.md` | P2 deferral documentation |
| `docs/agent/T26_TASK_CARD.md` | This file |
| `docs/ops/T26_PILOT_SMOKE_TEST.md` | NEW — full smoke test checklist |
| `docs/ops/T26_GO_NO_GO_CHECKLIST.md` | NEW — formal Go/No-Go |
| `docs/agent/T26_FINAL_SPRINT_REPORT.md` | NEW — project completion report |

## Files NOT Changed (per DO NOT TOUCH rules)

- `backend/app/api/v1/routes/ai_sessions.py` — no `service_account_id` field; P2-deferred
- `backend/tests/test_ratelimit.py` — all 8 ratelimit tests already pass; no change needed
- All model and migration files
- All auth/RBAC logic

---

## Test Results

```
Platform: Darwin arm64, Python 3.14.5
Tests: 515 passed, 1 skipped
Skipped: test_postgres_hypertable_ingest_and_trend (requires TimescaleDB)
Ruff: PASS (All checks passed)
```

---

## Acceptance Criteria

- [x] Rate limit skip investigated and documented
- [x] ImportError guard added to pdf_report.py
- [x] AI_SERVICE ownership constraint: P2-deferred with full documentation
- [x] Smoke test document created (26 flows)
- [x] Go/No-Go checklist created
- [x] Final sprint report created
- [x] 515 tests pass, 1 skipped (architectural)
- [x] Ruff clean

---

## Pilot Readiness

**VERDICT: GO** (with 4 deferred post-pilot items — see Go/No-Go checklist)
