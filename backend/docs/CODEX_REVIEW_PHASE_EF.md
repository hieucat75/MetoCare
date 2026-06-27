# Codex Review — MetoCare Phase E + F (Patient Insight Layer)

**Commits:** `db9a721` (Phase E) · `4986458` (Phase F) · `25e2da9` (Phase F patch)
**Date:** 2026-06-27
**Reviewer:** Codex (read-only)

---

**Result:** APPROVE WITH CONDITIONS

**P1 Blockers:** 1
**P2 Warnings:** 3
**P3 Suggestions:** 2
**Security:** PASS
**AC Verification:** 13/14 met

---

## P1 Blocker — Must fix before production

### P1-1: Frontend `sex`/`age` → Backend `is_male`/`age_years` field name mismatch

Frontend (`labInsight.ts`) sends:
```json
{ "batch_id": "...", "sex": "female", "age": 55 }
```

Backend `PatientInsightRequest` declares:
```python
is_male: bool = True
age_years: int | None = None
```

Pydantic v2 silently ignores unknown fields. Result:
- `is_male` **always defaults to `True`** regardless of patient sex
- `age_years` **always stays `None`**

Impact: eGFR CKD-EPI formula uses wrong sex coefficient for female patients.
HDL/creatinine reference ranges may be wrong for age-adjusted thresholds.

**Fix required:** Either rename `is_male`→`sex` + `age_years`→`age` in `PatientInsightRequest`, or map them explicitly (`is_male = body.sex == "male"`, `age_years = body.age`). Frontend already sends the right data — the backend mapping is broken.

**Must fix before production. Staging deploy OK with awareness.**

---

## P2 Warnings

### P2-1: Dead code — inline `PatternDetection` import

In `patient_insight.py` route, line ~151:
```python
from app.domain.clinical_patterns import PatternDetection  # noqa: F401
```
`PatternDetection` is never used inside the function body — no type annotation, no isinstance, no usage. `detect_patterns` is already imported at module top-level. The `noqa: F401` hides this from automated checks. Technical debt, not a correctness issue.

**Fix:** Remove the dead inline import.

### P2-2: No row limit on no-filter path

When neither `batch_id` nor `lab_result_ids` is provided, the query fetches **all patient records** with no LIMIT clause. For a patient with years of history this could be a large payload. Current production risk is low (feature not yet exposed), but the path needs pagination or a row cap before general use.

**Fix:** Add `LIMIT 200` (or equivalent `.limit(200)`) to the no-filter query, or block it until the dashboard endpoint is formally implemented.

### P2-3: `TimelineRow` change_pct color is direction-agnostic

In `LabInsightCards.tsx`, positive `change_pct` is always green, negative always red:
```tsx
const changePctColor = item.change_pct != null
  ? (item.change_pct >= 0 ? '#17AE7B' : '#D92D20')
  : undefined
```
For LDL or Triglyceride, an increase (+10%) is clinically bad but displayed green. For HDL, a decrease (-5%) is bad but displayed red. Direction semantics depend on the biomarker.

**Fix (P2 not P1):** Accept a `higher_is_better: boolean | null` field from the backend (already in `lab_reference.json` schema) and invert color logic accordingly. For now, consider making `change_pct` color neutral (gray) until direction semantics are wired.

---

## P3 Suggestions

### P3-1: `raw_inputs` last-write-wins for duplicate canonicals in same batch

The route loop:
```python
for r in verified:
    if r.canonical_name and r.value is not None:
        raw_inputs[r.canonical_name] = r.value
```
If a batch has two `ldl` records (e.g. different units or a duplicate), the last one silently wins. Derived metrics (Friedewald LDL, non-HDL) then use whichever value was iterated last. No error, no log.

**Suggestion:** Pick the record with the latest `test_date` explicitly, or log a warning when a canonical appears more than once.

### P3-2: Duplicate `disclaimer_vi` in route vs domain module

The empty-report branch in the route hardcodes the disclaimer inline as a string literal, separate from `_DISCLAIMER` in `patient_insight.py`. If the disclaimer text ever changes, both locations must be updated in sync.

**Suggestion:** Import `_DISCLAIMER` from the domain module and use it in the route's empty-report branch.

---

## AC Verification (13/14)

| # | AC | Result |
|---|----|----|
| 1 | `batch_id` field + filters before `lab_result_ids` | ✅ PASS |
| 2 | No-filter path exists for future dashboard | ✅ PASS (P2-2 noted) |
| 3 | Empty verified list → valid report, not error | ✅ PASS |
| 4 | `overall_status` priority ladder correct | ✅ PASS |
| 5 | `urgent_alerts` only for `severity=="critical"` | ✅ PASS |
| 6 | `ai_draft_contract` always `None` | ✅ PASS |
| 7 | `disclaimer_vi` always non-empty | ✅ PASS |
| 8 | `insights` ≤5, `top_priorities` ≤3 | ✅ PASS |
| 9 | `ocr_confidence` never used clinically | ✅ PASS |
| 10 | Auth: PATIENT owns record, others via consent | ✅ PASS |
| 11 | Frontend `LabInsightSection` accepts + forwards `batchId` | ✅ PASS |
| 12 | Each `BatchCard` passes its own `b.id` (no shared state) | ✅ PASS |
| 13 | No diagnosis language in any Vietnamese text | ✅ PASS |
| 14 | Inline `PatternDetection` import assessment | ⚠️ Dead code (P2-1) |

---

## Risk Assessment

**Staging deploy risk: LOW-MEDIUM**

Strong safety properties: no LLM, fully deterministic, correct auth, proper empty-state, 40 tests / 0 failures. Clinical text appropriately hedged, no diagnostic overreach.

**P1-1 (sex/age mismatch) must be fixed before patient-facing production.** Staging deploy is acceptable with the understanding that clinical computations will use `is_male=True, age_years=None` for all patients.

---

## Recommended Next Actions (ordered)

1. **Fix P1-1** — Map `sex`/`age` from frontend to `is_male`/`age_years` in backend (or rename fields for consistency). Add test asserting female patients get female-specific eGFR coefficient.
2. **Fix P2-1** — Remove dead inline `PatternDetection` import from route.
3. **Fix P3-2** — Use `_DISCLAIMER` constant in empty-report branch (1-line fix).
4. **Fix P2-3** — Make `change_pct` display color neutral, or wire `higher_is_better` from catalog.
5. **Address P2-2** — Add row limit on no-filter path before dashboard use.
6. **Staging deploy** — After P1+P2-1+P3-2 fixed.
