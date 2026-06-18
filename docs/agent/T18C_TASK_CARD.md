# T18C — Clinical Safety Red-Team

| Field | Value |
|-------|-------|
| **Sprint** | T18C |
| **Owner** | Claude Code |
| **Branch** | `feature/t18c-clinical-safety` |
| **Base commit** | `55b20d7` |
| **Status** | ✅ READY FOR CODEX REVIEW |
| **Created** | 2026-06-18 |

---

## Objective

Adversarial safety testing sprint for MetoCare before pilot launch. Pure test
sprint — verify guardrail system cannot be bypassed. No production code changes
unless a real safety hole is discovered and coordinator-approved.

---

## Scope

**Files created:**
- `backend/tests/safety/__init__.py` — new package
- `backend/tests/safety/test_clinical_redteam.py` — 30 red-team tests
- `docs/agent/T18C_CLINICAL_SAFETY_REDTEAM.md` — safety report

**Files modified:** None (test-only sprint)

---

## Test Categories

| Category | Tests | Count |
|----------|-------|-------|
| A. Red-Flag Bypass Attempts | Tests 1–5 (parametrized → 14) | 14 |
| B. AI Output Safety | Tests 6–9 | 4 |
| C. Cross-Patient Isolation | Tests 10–12 | 3 |
| D. Role Boundary Tests | Tests 13–15 (parametrized → 9) | 9 |
| **Total** | | **30** |

---

## Validation Results

```
Tests:  431 passed, 1 skipped  (baseline 401 + 30 new)
Ruff:   PASS (tests/safety/ clean; 2 pre-existing warnings in consent.py/lab.py)
Branch: feature/t18c-clinical-safety
```

---

## Safety Holes Found

**None.**

All 30 adversarial tests pass, confirming the guardrail system correctly:
- Blocks all red-flag bypass attempts (rule engine is LLM-independent)
- Blocks prohibited AI output content (diagnosis assertions, drug prescriptions)
- Enforces cross-patient data isolation
- Enforces role boundaries (AI_SERVICE blocked, CLINIC_ADMIN restricted)
- Returns 401 on unauthenticated requests to all patient data endpoints

---

## Constraints Satisfied

- [x] No production code changes
- [x] No false positives invented
- [x] Safety hole protocol followed (none found)
- [x] `backend/tests/safety/__init__.py` created
