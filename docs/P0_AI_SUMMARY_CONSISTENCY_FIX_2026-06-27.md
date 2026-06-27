# P0 Fix — AI Summary Clinical Consistency

## STATUS: PASS ✅

**Date**: 2026-06-27  
**Severity**: P0 (wrong severity in AI Summary — contradicted batch row)  
**Commit**: `28a86ab`

---

## Root Cause

**Case C: AI Summary had its OWN classification path that didn't use normalized values.**

**File**: `backend/app/api/v1/routes/patient_insight.py` — lines 128–133 (pre-fix)

```python
# BEFORE (WRONG):
for r in verified:
    if r.canonical_name and r.value is not None:
        raw_inputs[r.canonical_name] = r.value     # ← raw mmol/L value!
        f = assess_biomarker(
            r.canonical_name,
            r.value,                               # ← 5.7 (mmol/L) fed as mg/dL!
            ...
        )
```

**Why this broke:**
- `r.value = 5.7` (raw OCR value in mmol/L as stored)
- `assess_biomarker("fasting_glucose", 5.7)` interprets this as **5.7 mg/dL**
- In `clinical_rules.py`: `if value >= 500 or value <= 54:` → 5.7 ≤ 54 → **CRITICAL**
- → AI Summary showed "Đường huyết ở mức rất nguy hiểm" for a borderline result

**The actual normalized value**: 5.7 mmol/L × 18.018 = **102.7 mg/dL** → borderline/prediabetes range (100–125 mg/dL)

---

## Fix

**File changed**: `backend/app/api/v1/routes/patient_insight.py`

```python
# AFTER (CORRECT):
for r in verified:
    if not r.canonical_name:
        continue

    # Resolve canonical (SI) value — prefer stored normalized_value_si;
    # fall back to on-the-fly normalization from r.value + r.unit.
    norm_si: float | None = r.normalized_value_si
    if norm_si is None and r.value is not None:
        clf = normalize_and_classify(r.canonical_name, r.value, r.unit or "")
        norm_si = clf.get("normalized_value_si") if clf else None

    if norm_si is None:
        continue

    raw_inputs[r.canonical_name] = norm_si  # ← canonical mg/dL
    f = assess_biomarker(r.canonical_name, norm_si, ...)  # ← 102.7 mg/dL
```

**Data flow after fix:**
```
LabResult.value=5.7, unit=mmol/L
  → normalized_value_si=102.7 mg/dL (pre-computed at upload)
  → assess_biomarker("fasting_glucose", 102.7)
  → status='borderline' / patient_explanation_vi="Đường huyết lúc đói đang ở vùng tiền tiểu đường."
  → AI Summary shows borderline, NOT dangerous ✅
```

Also fixed: `raw_inputs` dict now stores normalized values for `compute_all_derived()` (which also expects mg/dL).

---

## All Data Sources for Clinical Messaging (after fix)

| Surface | Source | Status |
|---------|--------|--------|
| Batch row status badge | `LabResult.status` (lab_interpreter.classify_value, ref_high=99 mg/dL) | ✅ canonical |
| Biomarker detail page | `LabResult.status` + clinical_message | ✅ canonical |
| Alert Banner | `LabResultOut.is_critical` + `clinical_message` | ✅ canonical |
| AI Summary severity | `normalized_value_si` → `assess_biomarker()` (post-fix) | ✅ canonical |
| Urgent alerts | Generated from `assess_biomarker()` findings with `normalized_value_si` | ✅ canonical |

**Note**: Two different classification systems exist (by design):
- `lab_interpreter.classify_value()`: batch row status (ref_high=99 mg/dL → 102.7 = "high"/"Cao")
- `clinical_rules.assess_biomarker()`: AI summary (100-125 = "borderline"/"tiền tiểu đường")

These produce slightly different labels ("Cao" vs "tiền tiểu đường") but **neither should say "rất nguy hiểm"** for 5.7 mmol/L.

---

## Stale Cache / Backfill

- No DB cache for patient_insights (the insight is generated on-the-fly via API, not cached)
- No backfill required — the fix is in the runtime generation logic
- Existing LabResult records with `normalized_value_si` populated will now be used correctly

---

## Regression Tests

**File**: `backend/tests/test_ai_summary_consistency.py`

| Test | Description | Result |
|------|-------------|--------|
| `test_glucose_57_mmol_normalizes_to_high_or_borderline` | 5.7 mmol/L → 102.7 mg/dL → high/borderline, NOT critical | ✅ PASS |
| `test_glucose_57_mmol_assess_biomarker_not_critical` | assess_biomarker(102.7) must not be critical | ✅ PASS |
| `test_glucose_57_raw_mmol_as_mgdl_wrongly_critical` | Documents the bug: raw 5.7 IS wrongly critical | ✅ PASS |
| `test_glucose_502_mgdl_is_critical` | 502 mg/dL still critical | ✅ PASS |
| `test_glucose_57_mmol_overall_status_not_urgent` | Pipeline overall_status != urgent | ✅ PASS |
| `test_glucose_57_mmol_no_urgent_alerts` | No urgent alerts for 5.7 mmol/L | ✅ PASS |
| `test_glucose_57_mmol_explanation_not_dangerous` | No "rất nguy hiểm" in explanation | ✅ PASS |
| `test_glucose_57_mmol_insight_severity_not_critical` | Card not critical-importance | ✅ PASS |
| `test_glucose_502_mgdl_is_urgent` | 502 mg/dL pipeline status = urgent | ✅ PASS |
| `test_glucose_502_mgdl_generates_urgent_alert` | 502 mg/dL generates urgent alert | ✅ PASS |
| `test_glucose_502_mgdl_explanation_contains_danger` | 502 mg/dL urgent alert mentions danger | ✅ PASS |
| `test_creatinine_822_umol_normalizes_to_normal` | 82.2 µmol/L = 0.93 mg/dL → normal | ✅ PASS |
| `test_creatinine_212_mgdl_is_elevated` | 2.12 mg/dL → lab_interpreter says high | ✅ PASS |
| `test_creatinine_822_umol_pipeline_not_dangerous` | 82.2 µmol/L pipeline not urgent | ✅ PASS |
| `test_glucose_57_all_surfaces_agree_not_critical` | All surfaces: LabResult, assess_biomarker, AI Summary agree non-critical | ✅ PASS |
| `test_glucose_502_all_surfaces_agree_critical` | All surfaces: 502 mg/dL agree critical | ✅ PASS |
| `test_resolve_norm_si_uses_stored_normalized_value` | Route uses stored normalized_value_si | ✅ PASS |
| `test_resolve_norm_si_fallback_normalizes` | Fallback normalization works | ✅ PASS |
| `test_raw_57_as_mgdl_would_be_critically_wrong` | Confirms bug existed before fix | ✅ PASS |

**Total: 19 / Passed: 19 / Failed: 0**

Full test suite: 1495 tests — **1492 passed, 3 failed** (the 3 failures in `test_rag.py` are pre-existing, unrelated to this fix).

---

## Screenshot Confirmation (Staging)

**Backend**: `https://ca-metocare-backend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io`  
**Frontend**: `https://ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io`

### AI Summary page for batch with glucose 5.73 mmol/L:
```
AI Summary page (Nhận định AI) — /labs/2cc5bec8-8ec2-4eb2-907d-e439c7b76a6c/insight

Đường huyết lúc đói đang ở vùng cần chú ý   [Vừa - medium priority]
"Đường huyết lúc đói đang ở vùng tiền tiểu đường."
Action: "Nên xét nghiệm lại theo lịch định kỳ."
```
→ **NOT "rất nguy hiểm"** ✅  
→ **NOT urgent** ✅

### Glucose 5.73 mmol/L AI Summary: NOT urgent/dangerous: ✅
### Glucose 5.73 mmol/L batch row: "Cao" (High by lab_interpreter ref_high=5.6 mmol/L): ✅
### Both surfaces consistent (neither says dangerous): ✅

---

## Files Changed

- `backend/app/api/v1/routes/patient_insight.py` — P0 fix: use normalized_value_si
- `backend/tests/test_ai_summary_consistency.py` — New: 19 regression tests

## Commits

- `28a86ab` — fix(P0): AI Summary must use canonical normalized_value_si — not raw mmol/L value

---

## Out-of-Scope Issues Noted

The following issues were discovered but are **out of scope for this P0**:
1. **Creatinine display**: Batch shows `87.66 mg/dL` when the actual test value was likely in µmol/L (87.66 µmol/L = 0.99 mg/dL). The `r.value` is 87.66 and `r.unit` is unclear. This is a separate data/display bug.
2. **LabResult.status "Chưa rõ"**: Some batch rows show "Chưa rõ" (Unknown) status because `normalized_value_si` was not populated. Backfill needed on staging — but this is pre-existing and not this P0's scope.
