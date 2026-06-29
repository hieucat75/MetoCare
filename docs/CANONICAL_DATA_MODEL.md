# Canonical Data Model — Lab Result Value Pipeline

> **Status:** Authoritative reference. Updated 2026-06-30.
> **Owner:** Backend / Clinical platform team.

---

## Overview

A lab result flows through four distinct stages in Metocare. Each stage has a single, canonical field that acts as the source of truth for that stage. Mixing fields across stages is a P0 bug class.

```
OCR → [original_value / original_unit]
     ↓  normalize_value_to_si()
     → [normalized_value_si / normalized_unit_si]  ← classification input
     ↓  _build_clinical_input()
     → [normalized_value (formatted str) / normalized_unit]  ← display + AI input
     ↓  generate_explanation()
     → patient sees: original value in their unit
       AI says: same original value in same unit
       status badge: based on SI classification (correct medical threshold)
```

---

## Stage 1 — OCR / Manual Entry

| Field | Column | Type | Description |
|-------|--------|------|-------------|
| `original_value` | `lab_results.original_value` | `Float` | As printed on the patient's lab report (e.g. `6.0`) |
| `original_unit` | `lab_results.original_unit` | `String(64)` | As printed on the lab report (e.g. `mmol/L`) |
| `original_reference_range` | `lab_results.original_reference_range` | `String(128)` | Reference range as printed (e.g. `"3.9–5.6 mmol/L"`) |
| `original_test_name` | `lab_results.original_test_name` | `String(128)` | Test name as printed |

**Rule:** Never modify these fields after OCR. They are an immutable record of what the patient received from their lab.

---

## Stage 2 — SI Normalization

| Field | Column | Type | Description |
|-------|--------|------|-------------|
| `normalized_value_si` | `lab_results.normalized_value_si` | `Float` | Value converted to canonical SI unit (e.g. `231.6333` mg/dL) |
| `normalized_unit_si` | `lab_results.normalized_unit_si` | `String(64)` | Canonical SI unit (e.g. `mg/dL`) |

**Purpose:** Enables threshold-based classification against a single unit regardless of what unit the lab used.

**Rule:** Only `normalize_value_to_si()` in the intelligence engine writes these fields. Do NOT change this function — it is the authoritative unit conversion source.

### Unit Conversion Examples

| Original | Normalized SI |
|----------|--------------|
| 6.0 mmol/L (glucose) | 108.1 mg/dL |
| 5.6 mmol/L (cholesterol) | 216.6 mg/dL |
| 1.5 µmol/L (creatinine) | ~0.17 mg/dL |

---

## Stage 3 — Status Classification

| Field | Column | Type | Description |
|-------|--------|------|-------------|
| `status` | `lab_results.status` | `String(16)` | Classification result: `normal` / `borderline` / `high` / `low` / `critical` |

**Input:** `normalized_value_si` compared against reference thresholds for the canonical biomarker.

**Rule:** Classification always uses SI-normalized values. Never re-classify using `original_value`.

### Status Vocabulary Mapping

The intelligence engine uses these stored status values:

| DB `status` | Canonical status (explanation layer) | Vietnamese label | Color |
|-------------|-------------------------------------|-----------------|-------|
| `normal` | `normal` | Bình thường | `#17AE7B` (green) |
| `borderline` | `borderline_high` | Hơi cao | `#F59E0B` (amber) |
| `high` | `high` | Cao | `#F59E0B` (amber) |
| `low` | `low` | Thấp | `#3B82F6` (blue) |
| `critical` | `critical` | Nguy hiểm | `#D92D20` (red) |

**Defensive values** (not stored by current engine, but handled by frontend):

| value | label | color |
|-------|-------|-------|
| `very_high` | Rất cao | `#DC6803` (orange) |
| `critical_high` | Nguy hiểm | `#D92D20` |
| `critical_low` | Nguy hiểm | `#D92D20` |

---

## Stage 4 — Display & AI Explanation

### `_build_clinical_input()` — The Canonical DTO

This function in `backend/app/api/v1/routes/lab.py` is the **single translation point** between DB fields and the explanation layer.

#### Fields returned

| Key | Source | Type | Purpose |
|-----|--------|------|---------|
| `normalized_value` | `original_value` → formatted string | `str` | **Display value** — what patient sees; what AI must say |
| `normalized_unit` | `original_unit` | `str` | **Display unit** — as printed on lab report |
| `canonical_value_si` | `normalized_value_si` (rounded 4dp) | `float \| None` | SI value for reference; NOT used in narrative |
| `canonical_unit_si` | `normalized_unit_si` | `str` | SI unit for reference |
| `reference_range` | `row.reference_range` → cleaned | `str` | Numeric range only, no unit suffix |
| `canonical_status` | mapped from `row.status` | `str` | Status for AI safety rules |
| `canonical_severity` | derived from status | `str` | `none` / `moderate` / `critical` |
| `canonical_priority` | derived from status | `str` | `routine` / `urgent` |
| `doctor_review_required` | derived from status | `bool` | True only for `critical` |

#### Fallback chain for display value

```python
display_value = original_value  if original_value is not None
             else normalized_value_si

display_unit  = original_unit   if original_unit is not None and non-empty
             else normalized_unit_si or unit or ""
```

If both `original_value` and `normalized_value_si` are `None`, `normalized_value` is set to `"—"`.

#### Float formatting rules

Applied via `format_lab_value(display_value, display_unit)` in `backend/app/utils/number_format.py`:

| Unit | Decimals | Example |
|------|----------|---------|
| mg/dL | 0 (integer) | `231.6333…` → `"232"` |
| mmol/L | 1 | `6.0` → `"6.0"` |
| g/dL | 2 | `14.5012` → `"14.50"` |
| % | 1 | `6.1` → `"6.1"` |
| µmol/L | 0 | `45.7` → `"46"` |

---

## Reference Range Handling

### The double-unit bug (Bug 3)

`reference_range` stored in the DB may contain a unit suffix from OCR:

```
"0.6–1.3 mg/dL"        ← includes unit
"2.76–8.07 mg/dL mg/dL" ← duplicate unit (OCR artifact)
```

If the frontend renders `{result.reference_range} {displayUnit}`, the result is:
`"0.6–1.3 mg/dL mg/dL"` — **wrong**.

### The fix

`_clean_reference_range(raw, display_unit)` strips trailing unit-like tokens using regex:

```python
re.sub(r'\s+[A-Za-zµμ%/·]+.*$', '', raw.strip())
```

Examples after cleaning:
- `"0.6–1.3 mg/dL"` → `"0.6–1.3"`
- `"2.76–8.07 mg/dL mg/dL"` → `"2.76–8.07"`
- `"< 200"` → `"< 200"` (unchanged — no unit suffix)
- `"70–99"` → `"70–99"` (unchanged)

The cleaned `reference_range` is stored in `clinical_input["reference_range"]` and sent to Claude. The frontend renders it directly without appending `displayUnit` again.

---

## AI Explanation Pipeline

### Invariant: What AI says = What patient sees

Claude receives `normalized_value` (the formatted display string) and `normalized_unit` (the original OCR unit). The narrative it generates must reference the same value the patient sees on screen.

**Before this fix:** Claude received `231.6333 mg/dL`, but the patient saw `6.0 mmol/L`.  
**After this fix:** Claude receives `"6.0" mmol/L`, matching exactly what the patient sees.

### Claude safety rules (enforced by `validate_explanation`)

- `canonical_status = "normal"` → no alarming language
- `canonical_status` not critical → no "nguy hiểm", "cần gặp bác sĩ ngay"
- `canonical_status = "high" / "borderline_high"` → no "bình thường"
- `canonical_status = "low"` → no "bình thường"
- `doctor_review_required = False` → no "cần gặp bác sĩ ngay"

If any rule fails → deterministic fallback (no LLM output shown).

---

## LabResultOut DTO (Frontend API Schema)

Fields used at each render point:

| Component | Field used | Why |
|-----------|-----------|-----|
| Value display | `original_value` / `original_unit` | As printed on lab report |
| Value display (fallback) | `value` / `unit` | If original absent |
| Status badge | `status` | Pre-computed classification |
| Reference range | `reference_range` (cleaned by backend) | No unit suffix |
| Gauge position | `value` (canonical mg/dL) | Numeric comparison against ref min/max |
| AI explanation | `normalized_value` / `normalized_unit` in `clinical_input` | Must match display value |

---

## What NOT to do

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| Show `normalized_value_si` with `original_unit` | Mismatched unit/value pair |
| Show `original_value` with `normalized_unit_si` | Mismatched unit/value pair |
| Append `displayUnit` to `reference_range` in frontend | DB string already has unit (or was cleaned by backend) |
| Pass raw `normalized_value_si` float to Claude | Creates "231.63330000000002" float artifact in narrative |
| Re-classify using `original_value` | SI thresholds assume SI units |

---

## Related Files

| File | Role |
|------|------|
| `backend/app/api/v1/routes/lab.py` | `_build_clinical_input()`, `_clean_reference_range()` |
| `backend/app/utils/number_format.py` | `format_lab_value()` — float → display string |
| `backend/app/services/clinical_explanation.py` | `build_prompt()`, `validate_explanation()`, `get_deterministic_fallback()` |
| `backend/app/models/clinical.py` | `LabResult` ORM model |
| `frontend/src/components/patient/LabResultRow.tsx` | `statusLabel()`, `statusColor()`, `resolveDisplayValueUnit()` |
| `frontend/src/app/(patient)/labs/[batchId]/results/[resultId]/page.tsx` | Detail page render |
| `frontend/src/lib/formatNumber.ts` | Frontend `formatLabValue()` — mirrors backend rules |
