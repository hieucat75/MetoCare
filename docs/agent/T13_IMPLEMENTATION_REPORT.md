# T13 Implementation Report — Metabolic Score History API

**TASK_ID:** T13  
**Status:** READY FOR CODEX REVIEW  
**Branch:** `feature/t13-metabolic-score-history`  
**Completed:** 2026-06-18 GMT+7  
**Implementer:** Antigravity (subagent)

---

## Summary

All acceptance criteria met. Metabolic scores are now persisted for PATIENT callers and exposed via a paginated history endpoint with trend analysis.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/risk_score.py` | NEW — `save_score()`, `get_history()`, `compute_trend()` |
| `backend/app/schemas/risk_score.py` | NEW — `RiskScoreOut`, `RiskScoreHistoryResponse` |
| `backend/app/api/v1/routes/ai.py` | MOD — persist score after compute for PATIENT callers |
| `backend/app/api/v1/routes/patients.py` | MOD — new `GET /patients/{id}/metabolic-scores` endpoint |
| `backend/app/schemas/__init__.py` | MOD — export `RiskScoreHistoryResponse`, `RiskScoreHistoryItemOut` |
| `backend/tests/api/test_metabolic_score_history_api.py` | NEW — 10 tests |

---

## Design Decisions

### Schema: separate `risk_score.py` from `clinical.py`
The existing `clinical.py` already exports a `RiskScoreOut` schema used by other consumers (with `top_risks: str | None`). The new T13 `RiskScoreOut` parses `top_risks` as a `list[Any]` for API consumers. A separate `schemas/risk_score.py` avoids a breaking change to the existing export.

The existing `clinical.RiskScoreOut` is kept as-is. The `__init__.py` exports the new one as `RiskScoreHistoryItemOut` to avoid name collision.

### Persistence: PATIENT role + PatientProfile check
`ai.py` now accepts a `db: Session` dependency. After computing the score, it looks up the caller's `PatientProfile` via `user_id`. If found, persists via `risk_score_svc.save_score()`. Doctors, admins, and others are silently skipped — no behavior change for existing callers.

### RBAC on history endpoint
Reuses `patient_profile.get_profile()` as the access gate. This avoids duplicating RBAC logic and ensures consistent consent enforcement (DOCTOR requires active consent with `scope='profile'`). The profile result is discarded — only the 403/404 side-effects matter.

### Trend determinism in tests
SQLite assigns identical `CURRENT_TIMESTAMP` to rows inserted in the same transaction. `_seed_scores()` explicitly sets `created_at` offsets (1 minute apart, starting 2026-01-01) to guarantee deterministic ordering without relying on `time.sleep()`.

---

## Validation

```
ruff check .        → All checks passed!
pytest tests/ --tb=short → 299 passed, 1 skipped (baseline 289 → +10)
```

---

## Acceptance Criteria

- [x] `POST /ai/metabolic-score` persists to `risk_scores` for PATIENT callers
- [x] `GET /patients/{id}/metabolic-scores` returns paginated history + trend
- [x] RBAC correct on history endpoint (PATIENT own, DOCTOR consent-gated, ADMIN any, AI_SERVICE 403)
- [x] Trend logic correct for all 4 states
- [x] `top_risks` serialized as JSON list in DB, deserialized as list in response
- [x] 10 new tests pass
- [x] Zero regressions (289 → 299)
- [x] Ruff clean

---

*Report generated: 2026-06-18 GMT+7*
