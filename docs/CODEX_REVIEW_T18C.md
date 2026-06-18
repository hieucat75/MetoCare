# Codex Review — T18C: Clinical Safety Red-Team

| Field | Value |
|-------|-------|
| **Reviewer** | Codex (read-only subagent) |
| **Date** | 2026-06-18 |
| **Branch** | `feature/t18c-clinical-safety` |
| **Base** | `main` |
| **Scope** | Test + docs files only |

---

## Result: ✅ APPROVE

**P1 Blockers:** None

**P2 Warnings:**
1. ⚠️ All four vital thresholds have `board_approved=False, proposed=True` in `clinical_thresholds.py` — medical board sign-off required before production launch (confirmed existing observation from T18C safety report §4.1, not a code defect in this PR)
2. ⚠️ `severe_hypoglycemia` keyword tuple uses combined phrase strings (`"vã mồ hôi lú lẫn"`, `"run tay"`) — a patient typing individual symptoms without the exact combined phrase will not trigger EMERGENCY via symptom path; glucose vital threshold provides backup. Flagged for medical board review per §4.3 of the safety report.

**Security:** PASS

**Test Results:** 30/30 PASS (431 total, 1 skipped, 0 failures — verified against reported counts)

**Acceptance Criteria:** 7/7 met

---

## Findings

### AC1 — Red-Flag Escalation ✅

All five emergency categories verified against production rule engine:

| Category | Test | Adversarial Angle | Engine Verdict |
|----------|------|-------------------|----------------|
| Chest pain + dyspnea | Test 1 (3 instances) | Minimizing language ("nhẹ", "không đáng lo") | EMERGENCY ✓ |
| Cannot breathe variants | Test 2 (4 instances) | Varied dyspnea phrasing | EMERGENCY ✓ |
| Stroke symptoms | Test 3 (4 instances) | Direct + indirect | EMERGENCY ✓ |
| Glucose = 40 vital | Test 4 | `VitalSign("fasting_glucose", 40.0)` | EMERGENCY ✓ |
| Suicidal ideation | Test 5 (4 instances) | Direct phrases | NOT LOW/MODERATE ✓ |

**AC1 Priority Focus — Glucose threshold analysis:**

`clinical_thresholds.py` sets `fasting_glucose.critical_low = 54.0 mg/dL` (ADA 2024).

`triage.py` condition: `v.value <= thresholds["critical_low"]`

→ `40.0 <= 54.0` is `True` → fires `vital_low:fasting_glucose` red flag → **EMERGENCY**

Test 4 asserts both `RiskLevel.EMERGENCY` and the `vital_low:fasting_glucose` flag in `red_flags`. This is correctly wired. A glucose value of `40` triggers EMERGENCY (not merely HIGH) because the rule engine's hard path is taken before the soft classifier runs.

The `test_severe_hypoglycemia_glucose_critical_low_emergency` test is correctly named and the metric_type string `"fasting_glucose"` precisely matches the threshold key in `_DEFAULT_VITAL_THRESHOLDS`. ✅

### AC2 — AI Output Safety ✅

- Test 6: `DISCLAIMER_VI` checked in live API response body — gate tested end-to-end
- Test 7: 4 medication dose patterns tested against `guardrails.check_output()` — all return `BLOCK` with `prescribe_medication` flag
- Test 8: 4 diagnosis assertion patterns tested — all return `BLOCK` with `definitive_diagnosis` flag
- Test 9: Triage response message passed back through output validator — no prohibited content; disclaimer required

### AC3 — Cross-Patient Isolation ✅

**AC3 Priority Focus — Fixture verification:**

Patient B is **not** a hardcoded UUID. The `patient_b` fixture:
1. Creates a `User` row in the test DB with `os.urandom(4).hex()` random email
2. Flushes to DB → auto-assigns `user.id` (real PK)
3. Creates a `PatientProfile` linked to that user → `profile.id` (real PK)
4. Returns `patient_b["patient_id"] = profile.id`

Tests 10, 11, 12 then use `patient_b["patient_id"]` from the live DB — real IDs, not guessed UUIDs. Test 11 additionally seeds an `AISession` row for patient_b and uses `session.id` from the commit. This confirms **real resource IDs are used** in all cross-isolation tests. ✅

| Test | Endpoint | Token Used | Expected | Verified |
|------|----------|------------|----------|---------|
| 10 | `GET /patients/{B_id}/triage-history` | Patient A JWT | 403 | ✓ |
| 11 | `GET /ai_sessions/{B_session_id}` | Patient A JWT | 403 | ✓ |
| 12 | `GET /patients/{B_id}/nutrition` | Patient A JWT | 403 | ✓ |

### AC4 — Role Boundaries ✅

| Test | Role | Endpoint | Expected | Verified |
|------|------|----------|----------|---------|
| 13 | AI_SERVICE | POST `/ai/triage` | 403 | ✓ |
| 14 | CLINIC_ADMIN | POST `/patients/{id}/metrics` | 403 | ✓ |
| 15 (5 instances) | Unauthenticated | All 5 patient endpoints | 401 | ✓ |

Note: Test 14 docstring title says "cannot read" but the implementation correctly tests `POST` (write) — the docstring has a minor inconsistency ("cannot read" vs "cannot write") but the tested behavior matches the intent and AC description ("CLINIC_ADMIN blocked from health metrics writes"). Not a blocker.

### AC5 — No Production Code Modified ✅

`git diff main..feature/t18c-clinical-safety --name-only` output:
```
backend/tests/safety/__init__.py
backend/tests/safety/test_clinical_redteam.py
docs/agent/T18C_CLINICAL_SAFETY_REDTEAM.md
docs/agent/T18C_TASK_CARD.md
```

`git diff main..feature/t18c-clinical-safety -- 'backend/app/**'` → empty (no output)

**Zero production code changes confirmed.** ✅

### AC6 — Adversarial Phrasing Coverage ✅

Test 1 explicitly uses minimizing language:
- `"Hôm nay tôi có cảm giác hơi đau ngực, không đáng lo ngại, chỉ khó thở nhẹ."` → EMERGENCY

This works because `triage.py` `_detect_symptom_red_flags()` uses `unicodedata.normalize("NFC", text).lower()` + `in` substring match — it does NOT perform sentiment analysis. The keywords `"đau ngực"` and `"khó thở"` are matched by substring regardless of surrounding minimizing adverbs. ✅

### AC7 — 30 Tests Pass, 0 Regressions ✅

Test count reconciliation:
| Tests | Count |
|-------|-------|
| test_1 (`@parametrize` × 3 adversarial_text) | 3 |
| test_2 (`@parametrize` × 4 phrases) | 4 |
| test_3 (`@parametrize` × 4 phrases) | 4 |
| test_4 (non-parametrized) | 1 |
| test_5 (`@parametrize` × 4 phrases) | 4 |
| tests 6–14 (9 non-parametrized) | 9 |
| test_15 (`@parametrize` × 5 endpoints) | 5 |
| **Total** | **30** |

Baseline 401 + 30 new = **431 passed, 1 skipped**. Matches reported results. ✅

---

## Minor Observations (Non-Blocking)

1. **Test 14 docstring inconsistency**: Says "cannot read patient health metrics" but tests `POST` (write). The behavior under test is correct; only the docstring title is misleading.

2. **`board_approved=False` on all thresholds**: This is an existing condition from prior sprints, not introduced by T18C. Flagged because it matters for production readiness.

3. **`severe_hypoglycemia` keyword gap** (§4.3 of implementer's report): `"run tay"` appears in the tuple but only as a standalone 2-word string. A patient input of just `"tôi run tay"` contains `"run tay"` as a substring → will actually match. However `"vã mồ hôi lú lẫn"` is a combined 4-word phrase that only matches the exact phrase. Low impact because vital threshold path covers glucose crises independently.

4. **No prompt-injection red-team coverage in this sprint**: The `is_injection()` function has existing coverage in `test_guardrails.py`. The implementer's decision not to duplicate it is defensible and noted.

---

## Summary

T18C adds 30 adversarial safety tests targeting the five highest-risk failure modes (emergency escalation bypass, AI output safety, cross-patient data leakage, role boundary violations, and unauthenticated access). All tests correctly probe the production guardrail code at both domain layer and API layer. The glucose threshold critical priority item is correctly handled: `glucose=40` triggers EMERGENCY via `40 <= 54.0` in the vital threshold comparator. Cross-patient isolation uses real DB-created IDs throughout. No production code was modified. The branch is safe to merge.
