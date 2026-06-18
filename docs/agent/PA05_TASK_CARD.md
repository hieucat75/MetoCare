# PA-05 — AI Patient-Safe Explanation Endpoint

**Status:** READY FOR CODEX REVIEW  
**Branch:** `feature/pa05-ai-patient-explanation`  
**Created from:** `main` HEAD `a577bc2`  
**Owner:** Claude Code  
**Date:** 2026-06-18

---

## Objective

Implement a patient-safe AI explanation endpoint (`POST /api/v1/ai/explain`) that transforms structured health metrics into friendly, plain-language summaries. The endpoint is PATIENT-only and never exposes raw clinical scores or diagnostic conclusions.

---

## Scope

| Item | Detail |
|------|--------|
| New endpoint | `POST /api/v1/ai/explain` |
| RBAC | PATIENT only — DOCTOR, ADMIN, AI_SERVICE → 403 |
| Mock implementation | Deterministic mock summaries per `explanation_type` (pilot mode, no external LLM) |
| Patient ownership | Caller's `user_id` must resolve to a `PatientProfile` whose `id` matches `patient_id` |
| Disclaimer | Always present in every response |
| Schemas | `AiExplainRequest`, `AiExplainResponse`, `ExplanationType` enum, `SafetyLevel` enum |
| Tests | 11 tests (8 ACs + 4 parametrized disclaimer checks) |
| Migrations | None required |

---

## Files Changed

| File | Action |
|------|--------|
| `backend/app/api/v1/routes/ai.py` | MODIFIED — added `POST /ai/explain` endpoint |
| `backend/app/schemas/ai.py` | MODIFIED — added `AiExplainRequest`, `AiExplainResponse`, `ExplanationType`, `SafetyLevel`, `ExplainContext` |
| `backend/tests/api/test_ai_patient_explain.py` | NEW — 11 tests covering all 8 ACs |
| `docs/agent/PA05_TASK_CARD.md` | NEW (this file) |
| `docs/agent/PA05_IMPLEMENTATION_REPORT.md` | NEW — implementation report |

---

## Quality Gate

| Check | Result |
|-------|--------|
| `ruff check app/ tests/` | ✅ PASS (0 errors) |
| `pytest tests/api/test_ai_patient_explain.py -v` | ✅ 11/11 passed |
| `pytest tests/ -q --tb=short` | ✅ 535 passed, 1 skipped (≥531 ✓) |
