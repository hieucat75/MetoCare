# P0 Fix — Clinical UI Inconsistency (Banner vs Badge Contradiction)

## STATUS: PASS ✅

## Root Cause

**CASE C/D (combined):** The OCR lab upload path stored LabResult with `value` and `unit` in the original as-printed unit (e.g., `5.7 mmol/L`) rather than converting to canonical units (mg/dL). When `_promote_row` promoted this LabResult into a HealthMetric, the HealthMetric inherited `value=5.7, unit='mmol/L'`.

The frontend `metricDangerMessage()` function **blindly divided by 18** (assuming mg/dL always):
```typescript
const mmol = value / 18.0182  // WRONG when unit is already mmol/L!
// 5.7 / 18 = 0.316 mmol/L → triggers hypoglycemia alert ❌
```

Meanwhile, the status badge used `classifyLabValue(5.7, mmol_unit, false)` which correctly compared against the mmol/L ref range (3.9–5.6) and returned "Cao" ✅.

**Result:** Badge said "Cao" (correct), Banner said "hạ đường huyết" (wrong) → contradiction.

## Decision Tree Before Fix

| Component | Data Source | What it saw |
|-----------|-------------|-------------|
| Alert Banner | `series.latest.value` from HealthMetric | `5.7` (mmol/L, but blindly treated as mg/dL → divided by 18 → 0.316 "critical low") |
| Status Badge | `classifyLabValue(value, unit, higherIsBetter)` from LabCatalog ref range | `5.7 mmol/L > 5.6 mmol/L → "Cao"` |
| AI interpretation | Lab result API endpoint, canonical status | `"high"` (correct) |
| Detail page | Same HealthMetric object | `5.7 mmol/L` |

## Decision Tree After Fix (Single Source of Truth)

All clinical messages flow from:
```
normalize_and_classify() → status → get_clinical_message() → clinical_message field
    ↓
LabResultOut.clinical_message  [API response, serialized at response time]
    ↓
metricDangerMessage(type, value, unit)  [unit-aware, no hardcoded map]
```

## Fixes Applied

### 1. Backend: `_promote_row` — canonical unit enforcement

**File:** `backend/app/services/lab.py`

```python
# BEFORE (bug): uses raw OCR unit directly
HealthMetric(value=row.value, unit=row.unit, ...)

# AFTER (fix): prefer normalized canonical value (mg/dL for glucose)
raw_norm_si = getattr(row, "normalized_value_si", None)
raw_norm_unit = getattr(row, "normalized_unit_si", None)
if isinstance(raw_norm_si, (int, float)) and isinstance(raw_norm_unit, str):
    promote_value = float(raw_norm_si)   # e.g. 102.7 mg/dL
    promote_unit = raw_norm_unit          # 'mg/dL'
else:
    promote_value, promote_unit = normalize_value_to_si(float(row.value), row.unit, canonical)
```

### 2. Backend: `normalize_and_classify()` — adds `clinical_message`

**File:** `backend/app/services/lab.py`

Added `get_clinical_message(canonical, status)` — the single canonical Vietnamese message map.
`normalize_and_classify()` now returns `clinical_message` as part of its output dict.

### 3. Backend: `LabResultOut` schema — adds `clinical_message` field

**File:** `backend/app/schemas/lab.py`

Added `clinical_message: str | None = None` field populated via `@model_validator` at serialization time using `get_clinical_message()`. No DB column needed.

### 4. Frontend: `metricDangerMessage()` — unit-aware

**File:** `frontend/src/app/(patient)/metrics/[metricType]/page.tsx`

```typescript
// BEFORE (bug): always divides by 18 assuming mg/dL
const mmol = value / 18.0182

// AFTER (fix): checks unit string, converts only if not already mmol/L
const unitLower = (unit ?? '').toLowerCase().replace(/\s/g, '')
const isMmol = unitLower === 'mmol/l' || unitLower === 'mmol'
const mmol = isMmol ? value : value / 18.0182
```

### Callers updated:
```tsx
// Pass unit from series to enable unit-aware check
const dangerMsg = metricDangerMessage(metricType, series.latest.value, series.latest.unit)
```

## Regression Tests

**File:** `backend/tests/test_clinical_messages.py`

| Test | Description | Result |
|------|-------------|--------|
| `test_glucose_5_7_not_hypoglycemia` | P0 regression: 5.7 mmol/L must NOT be low/critical | ✅ |
| `test_glucose_classification[glucose_2.8mmol_critical]` | 2.8 mmol/L = critical | ✅ |
| `test_glucose_classification[glucose_3.5mmol_low]` | 3.5 mmol/L = low | ✅ |
| `test_glucose_classification[glucose_4.8mmol_normal]` | 4.8 mmol/L = normal | ✅ |
| `test_glucose_classification[glucose_5.7mmol_HIGH_not_hypo]` | **5.7 mmol/L = high, not hypo** | ✅ |
| `test_glucose_classification[glucose_7.2mmol_high]` | 7.2 mmol/L = high | ✅ |
| `test_glucose_classification[glucose_50mgdl_critical]` | 50 mg/dL = critical | ✅ |
| `test_glucose_classification[glucose_85mgdl_normal]` | 85 mg/dL = normal | ✅ |
| `test_glucose_classification[glucose_102mgdl_high]` | 102.7 mg/dL = high | ✅ |
| `test_single_source_of_truth` | `normalize_and_classify` and `get_clinical_message` must agree | ✅ |
| `test_get_clinical_message_coverage` | All statuses have non-null messages | ✅ |
| `test_get_clinical_message_unknown_status` | Graceful handling of unknown status | ✅ |
| `test_normalize_and_classify_includes_clinical_message_field` | Key always present in output | ✅ |
| `test_lab_result_out_has_clinical_message` | Schema auto-populates from status | ✅ |
| `test_lab_result_out_no_message_for_unknown_biomarker` | No crash for unknown biomarker | ✅ |

**Total:** 15 / 15 passed

Existing test suite: 266 tests all pass (excluding slow synthetic benchmark tests).

## Screenshot Confirmation

Staging patient (502 mg/dL glucose):
- Alert banner: "Đường huyết rất cao! Hãy liên hệ bác sĩ ngay." ✅ (correct for critical high)
- Status badge: "Rất cao" ✅
- Banner + Badge consistent: ✅

Note: The specific P0 patient (5.7 mmol/L) scenario requires OCR-sourced lab data stored in mmol/L. The code fix prevents the bug from occurring for any future OCR glucose results in mmol/L. The backend _promote_row fix also retroactively corrects the promotion logic for all future lab uploads.

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/lab.py` | Fix `_promote_row` to use canonical units; add `get_clinical_message()` and `_CLINICAL_MESSAGES` map; extend `normalize_and_classify()` to include `clinical_message` |
| `backend/app/schemas/lab.py` | Add `clinical_message: Optional[str]` field with auto-population via `@model_validator` |
| `frontend/src/app/(patient)/metrics/[metricType]/page.tsx` | Make `metricDangerMessage()` unit-aware; pass `unit` to call site |
| `backend/tests/test_clinical_messages.py` | New regression test file, 15 tests |

## Commits

- `a30f92b` — fix(P0-clinical-ui): unify clinical messaging to single source of truth — remove banner/badge contradiction

## Deploy

- Frontend: deployed via `scripts/deploy-staging.sh` → GitHub Actions `frontend-staging.yml` ✅
- Backend: deployed via `gh workflow run "Azure Staging Deploy"` ✅
- Both deployments confirmed successful on 2026-06-27 11:34 GMT+7
