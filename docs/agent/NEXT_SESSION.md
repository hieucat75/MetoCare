# MetoCare — Next Session Primer (2026-06-25)

## FIRST ACTIONS
```bash
git log --oneline -5           # confirm OCR hardening commit landed
git status                     # should be clean after session closure commit
cd backend && .venv/bin/pytest --tb=no -q | tail -3   # expect 836+ passed
cd frontend && npx tsc --noEmit | tail -5             # expect 0 errors
```

## CURRENT STATE

Branch: main
Last deploy: b512ee6 (PR #49, PX-02D + PA-11 insights)
DB migration head: hmbk_backfill (no new migrations needed)

### Key files modified this session
```
backend/app/domain/lab_interpreter.py     BiomarkerSpec: physiological bounds + expanded aliases
backend/app/services/lab_parser.py        hospital detection, plausibility check, confidence logging
backend/app/domain/hospital_profiles.py   NEW: 7 Vietnamese hospital profiles
backend/app/services/ocr_metrics.py       NEW: OcrMetrics singleton
backend/app/services/lab.py               wired OcrMetrics into interpret_document()
backend/tests/test_lab_ocr.py             16 Vinmec regression tests
backend/tests/test_lab_regression.py      NEW: golden master tests (371 lines)
backend/tests/data/lab_reports/           NEW: vinmec/medlatec/tam_anh/generic fixtures
frontend/src/app/(patient)/labs/upload/page.tsx  confidence badges (red/amber/blue)
```

## ARCHITECTURE: OCR PIPELINE

```
Patient uploads lab image
  -> Azure Document Intelligence (secretref:doc-intel-key, NEVER hardcoded)
  -> detect_hospital(text) -> HospitalProfile (vinmec/medlatec/tam_anh/hong_ngoc/108/bach_mai/fv)
  -> parse_lab_text(text, hospital_profile)
       - build _combined alias index (base + hospital extras + OCR corrections)
       - for each line: _match_biomarker -> extract value + unit
       - incompatible unit -> parse_conf = 0.0
       - SI convert (mmol/L -> mg/dL) -> parse_conf = 1.0
       - crude root fallback -> parse_conf = 0.6
       - outside physiological bounds -> parse_conf = 0.0
       - _logger.debug("ocr_confidence_breakdown", ...)
  -> interpret_panel -> InterpretedBiomarker list
  -> OcrMetrics.record_upload(...)
  -> LabResult rows (value in canonical units mg/dL / U/L / mIU/L)
  -> promote_lab_rows_to_metrics -> HealthMetric
  -> Dashboard / Metrics / PA-11 insight cards
```

## SI CONVERSION FACTORS
```
glucose / random_glucose       x18.018  (mmol/L -> mg/dL)
total_cholesterol / ldl / hdl  x38.67   (mmol/L -> mg/dL)
triglyceride                   x88.57   (mmol/L -> mg/dL)
tsh                            x1.0     (uIU/mL = mIU/L, rename only)
ft3 / ft4                      stored as-is in pmol/L
```

## PHYSIOLOGICAL BOUNDS (selected)
```
glucose        20 - 1500   mg/dL
cholesterol    50 - 1000   mg/dL
triglyceride   10 - 10000  mg/dL
hdl             5 - 200    mg/dL
alt / ast       0 - 15000  U/L
tsh             0 - 500    mIU/L
```

## PRIORITY QUEUE

### P1 — Do next
1. Deploy to staging: trigger "Azure Staging Deploy" workflow (no infra changes needed)
2. Smoke test: upload Vinmec lab image via UI, verify confidence badges, check LabResult values
3. Fix adherence unbounded query: adherence_summary() in backend/app/services/medication.py
   all_records fetch has no LIMIT — add limit=365 or equivalent
4. PR #47 Dashboard RCA: review screenshots, decide merge or close

### P2
- PA-11 PR-C: insight card in /metrics/[metricType] (branch feat/pa11-clinical-insight exists)

### P3 — Do NOT start
- Doctor phase (PAUSED — explicit hold)
- Native App (not started)
- Device Integrations (not started)
- AI coach confirm-action (missing backend fields: causes, outcome)

## SECURITY CONSTRAINTS (non-negotiable)
- Do NOT touch DigitalOcean VPS (LEGACY — deprecated 2026-06-28, server still running)
- Do NOT seed admin accounts
- Azure DI key = secretref:doc-intel-key only, never hardcoded
- No logging raw medical image content (bytes/base64)
- Doctor phase remains PAUSED

## TEST BASELINE
- Backend: 836 passed, 1 skipped
- Frontend: tsc 0 errors
- Regression fixtures: 4 hospitals (vinmec, medlatec, tam_anh, generic)
