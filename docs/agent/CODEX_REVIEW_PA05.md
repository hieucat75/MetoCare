# CODEX REVIEW — PA-05 AI Patient-Safe Explanation
**Branch:** `feature/pa05-ai-patient-explanation`
**vs Base:** `main` (`a577bc2`)
**Date:** 2026-06-19
**Reviewer:** Codex (gpt-5.5, reasoning high)
**Test result:** 535 passed, 1 skipped

---

## VERDICT: REQUEST_CHANGES (P1 × 2)

---

## P0 Findings
**NONE**

---

## P1 Findings

### P1-1: Reversed metabolic-score guidance (medically inverted)
- **File:** `backend/app/api/v1/routes/ai.py:170-173`
- **Issue:** Default summary says "A higher score means your body is managing important factors… more efficiently."
- **Bug:** The domain model `metabolic_score.py` defines **higher = more concern** (0=good → 100=high risk). This is the exact opposite of what the summary tells patients.
- **Risk:** Patient with high metabolic risk told "higher is better" → dangerous misinterpretation.
- **Fix:** Reverse the guidance — higher score = more concern, lower = healthier.

### P1-2: Raw clinical score exposed in response
- **File:** `backend/app/api/v1/routes/ai.py:236-238`
- **Issue:** When `context.score` is provided, the route builds: `f"Your metabolic wellness score is {ctx.score}."` — exposes the raw numeric score.
- **Bug:** The endpoint's stated safety requirement says it "never exposes raw clinical scores or diagnostic conclusions." Returning `{ctx.score}` violates this explicitly.
- **Fix:** Remove raw score from summary. Use qualitative language only (e.g. "Your metabolic wellness is in a good range" based on the band, not the number).

---

## P2/P3 Findings

### P2-1: `import enum as _enum` placed mid-file (after class definitions)
- `schemas/ai.py` lines 73-74: imports placed after `DoctorReviewDecision` class
- Ruff does not fail due to `# noqa: E402` suppression but is non-idiomatic
- Minor code quality issue — low risk

### P3-1: `ExplainContext.trend` is free-form string
- No validation of trend values (could accept garbage: "very bad", "decreasing slightly")
- Consider `Literal["improving", "stable", "worsening"] | None` for stricter validation

---

## Positive Findings

- ✅ RBAC correctly enforced: `_require_patient_only` = `require_roles(UserRole.PATIENT)` only
- ✅ Ownership check: `PatientProfile.user_id == user.id` → profile.id vs payload.patient_id
- ✅ Medical disclaimer always present as constant (`_DISCLAIMER`), never None
- ✅ `_DISCLAIMER` defined once in schemas, imported into route — no drift risk
- ✅ Mock implementation — no external LLM call in pilot
- ✅ 11 tests covering all 8 ACs including parametrized disclaimer check
- ✅ `generated_at` uses `datetime.now(tz=UTC)` (timezone-aware)
- ✅ No new DB migrations required

---

## Required fixes before merge

1. Fix reversed metabolic-score default summary (P1-1)
2. Remove raw numeric score from contextualized summary (P1-2)
