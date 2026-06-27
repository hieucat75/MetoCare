# Data Integrity Cleanup + Guardrails

**Date:** 2026-06-27  
**Executed by:** OpenClaw subagent (automated)  
**Commit:** `dc13a7d`

---

## STATUS: PASS ✅

---

## Dry-Run Findings

| Pattern | Records Found | Action |
|---------|--------------|--------|
| creatinine_unit_mismatch | 0 | N/A — clean DB |
| health_metric_creatinine_high | 0 | N/A — clean DB |
| glucose_as_creatinine | 0 | N/A — clean DB |

Staging DB was clean — no pre-existing bad data found.

---

## Records Corrected

- **0** normalized_value_si re-computed (DB was clean)
- **0** data_quality_flag set to 'suspicious'
- **0** records deleted (NEVER DELETE — policy enforced)

---

## Write-time Guardrails Added

### New file: `backend/app/services/biomarker_specs.py`
- `BIOMARKER_PLAUSIBILITY` dict: 20 biomarkers with physiological min/max for both canonical and SI units
- `check_plausibility(biomarker_name, value, unit) -> dict`: returns `{plausible, suspicious, reason}`
- Covers: creatinine, fasting_glucose, lipids (TC/LDL/HDL/TG), liver enzymes (ALT/AST/GGT), HbA1c, CBC, electrolytes

### New function: `validate_before_save()` in `backend/app/services/lab.py`
- Called BEFORE `db.add()` in:
  1. `create_manual_entry()` ✅ (line 538)
  2. OCR path (interpret + persist) ✅ (line 389)
- Returns `{valid, suspicious, reason, action}` — always `valid=True` (never reject)
- Sets `row.data_quality_flag` and `row.data_quality_note` on suspicious records
- Logs `WARNING` for all flagged records

### Suspicious-record policy
- `action="save"` → normal write, no flag
- `action="flag"` → write + set `data_quality_flag='flag'` + `data_quality_note=<reason>`
- **NEVER** reject silently — data is always saved; humans review flagged records

---

## DB Changes

### Migration: `t7_m1_dquality_add_data_quality_fields`
- Added `data_quality_flag VARCHAR(20) NULLABLE` to `lab_results`
- Added `data_quality_note TEXT NULLABLE` to `lab_results`
- Applied: ✅ (`alembic upgrade head`)

### Model: `backend/app/models/clinical.py`
- `LabResult.data_quality_flag: Mapped[str | None]`
- `LabResult.data_quality_note: Mapped[str | None]`

---

## Cleanup Script

**Location:** `backend/scripts/data_integrity_cleanup.py`

**Usage:**
```bash
# Dry-run (default) — report only, no writes:
python backend/scripts/data_integrity_cleanup.py --dry-run

# Apply safe corrections:
python backend/scripts/data_integrity_cleanup.py --apply
```

**Patterns checked:**
1. `creatinine_unit_mismatch` — normalized creatinine > 28 mg/dL stored as mg/dL
2. `health_metric_creatinine_high` — HealthMetric creatinine value > 28 mg/dL  
3. `glucose_as_creatinine` — HealthMetric creatinine with value > 100 mg/dL (glucose range)

**Safety invariants enforced in script:**
- ❌ NEVER deletes records
- ❌ NEVER changes `original_value` or `original_unit`
- ❌ NEVER auto-corrects `metric_type` or `canonical_name`
- ✅ Only safe corrections: re-normalize `normalized_value_si`/`normalized_unit_si`
- ✅ Always marks suspicious with `data_quality_flag='flag'` and note

---

## Tests

**File:** `backend/tests/test_data_integrity.py`

| Test | Result |
|------|--------|
| creatinine 87.7 µmol/L → plausible | ✅ PASS |
| creatinine 0.99 mg/dL → plausible | ✅ PASS |
| creatinine 87.7 mg/dL → suspicious (unit mismatch) | ✅ PASS |
| creatinine 502 mg/dL → suspicious | ✅ PASS |
| glucose 502 mg/dL → plausible (critical but real) | ✅ PASS |
| glucose 5.5 mmol/L → plausible | ✅ PASS |
| ALT 5000 U/L → plausible | ✅ PASS |
| ALT 20000 U/L → implausible | ✅ PASS |
| unknown biomarker → allowed (pass-through) | ✅ PASS |
| cholesterol 800 mg/dL → plausible | ✅ PASS |
| HDL 300 mg/dL → implausible (>200 max) | ✅ PASS |
| creatinine at exact max boundary → plausible | ✅ PASS |
| creatinine 31 mg/dL → suspicious | ✅ PASS |
| validate_before_save: 87.7 µmol/L → no flag | ✅ PASS |
| validate_before_save: 87.7 mg/dL → flagged | ✅ PASS |
| validate_before_save: glucose 502 mg/dL → no flag | ✅ PASS |
| validate_before_save: unknown → always saves | ✅ PASS |
| validate_before_save: always valid (never reject) | ✅ PASS |
| validate_before_save: suspicious original → flagged | ✅ PASS |
| cleanup: 0 suspicous on clean DB | ✅ PASS |
| original_value never overwritten after cleanup | ✅ PASS |
| no silent deletion by cleanup | ✅ PASS |

**Total: 22 / Passed: 22 / Failed: 0**

---

## Staging Smoke

- Backend health `GET /api/v1/health`: **200 OK** ✅
- DB: **ok** ✅
- No new P0 contradictions: ✅
- Deploy workflow triggered: ✅ (frontend-staging)

---

## Remaining Risk

1. **No pre-existing bad data found** — guardrails are now active for new writes
2. **Import / bulk-upload path**: if a bulk-import endpoint exists beyond `create_manual_entry`, it should also call `validate_before_save`. Current coverage: create_manual_entry + OCR path. Search with `grep -n "def.*import\|def.*bulk" backend/app/services/lab.py` before adding new import paths.
3. **HealthMetric has no data_quality_flag column** — only `lab_results` was migrated. If direct HealthMetric writes exist outside lab promotion, consider adding the same columns there.
4. **Plausibility specs are intentionally loose** — they catch unit mismatches and gross impossibilities, not clinical borderline values. Clinical rules remain in `lab_normalization.py` / `lab_interpreter.py`.

---

## Commits

- `dc13a7d` — fix(data-integrity): add write-time plausibility guardrails + cleanup suspicious records
