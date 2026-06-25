# MetoCare Session Closure — 2026-06-25

## Branch: main
## HEAD: e1aac34 (+ uncommitted workflow changes — see commit below)
## Azure Staging: southeastasia, rg-metocare-staging

---

## This Session — Completed

### Phase A: Medication Adherence (carried over, already deployed)
- `7d9aef3` fix(adherence): Codex HIGH fixes — mutual exclusivity + dead audit log
- Deployed at `bde71dd`; 836 tests passing at session end

### Phase B: OCR Accuracy Hardening — Vinmec Ground Truth
Commit `e1aac34` feat(lab-ocr): harden mapping layer with SI unit conversion + incompatible unit rejection:
- `BiomarkerSpec` extended: `si_unit`, `si_factor`, `incompatible_units`
- `parse_lab_text`: `_norm_unit`, `_is_incompatible`, `_try_si_convert`
- 16 new tests: `TestVinmecGroundTruth` (10) + `TestIncompatibleUnitRejection` (5)
- `triglycerid` alias added (Vietnamese OCR without trailing 'e')
- Test baseline after Phase B: 795 passed

### Phase C: Production OCR Hardening (workflow wf_08f5dd2f-366, 6 agents)

**Task 1 — Clinical Sanity Layer**
- `BiomarkerSpec` gained `physiological_min` / `physiological_max`
- All 22 biomarkers have plausibility bounds; values outside bounds → `parse_conf = 0.0`
- Modified: `backend/app/domain/lab_interpreter.py`

**Task 2 — Hospital Profile Library**
- `backend/app/domain/hospital_profiles.py` (NEW): `HospitalProfile` dataclass + `detect_hospital()`
- 7 Vietnamese hospital profiles: Vinmec, Medlatec, Tam Anh, Hong Ngoc, 108, Bach Mai, FV
- Detection via accent-stripped header patterns (first 30 OCR lines)

**Task 3 — OCR Alias Expansion**
- 11 biomarkers gained additional aliases
- Hospital-specific alias overlay wired into `parse_lab_text`
- Modified: `backend/app/domain/lab_interpreter.py`, `backend/app/services/lab_parser.py`

**Task 4 — Confidence Engine**
- Structured `_logger.debug("ocr_confidence_breakdown", ...)` in `parse_lab_text`
- Modified: `backend/app/services/lab_parser.py`

**Task 5 — Regression Dataset**
- `backend/tests/data/lab_reports/` (NEW): vinmec, medlatec, tam_anh, generic fixtures
- 4 x (report_01.txt + report_01.json)

**Task 6 — Golden Master Tests**
- `backend/tests/test_lab_regression.py` (NEW, 371 lines)
- TestVinmecGoldenMaster, TestMedlatecGoldenMaster, TestTamAnhGoldenMaster, TestGenericNoHospital
- TestPhysiologicalPlausibility

**Task 7 — Production Metrics**
- `backend/app/services/ocr_metrics.py` (NEW): `OcrMetrics` singleton
- Wired into `lab.py` `interpret_document()` call

**Task 8 — Review UX Improvements**
- Lab upload page: confidence badges (red/amber/blue per biomarker)
- Modified: `frontend/src/app/(patient)/labs/upload/page.tsx`
- Also updated: dashboard/page.tsx, medications/[id]/page.tsx, profile/page.tsx, lib/api/patient.ts

**Final test count: 836 passed, 1 skipped**

---

## Patient App Status
| Feature | State |
|---|---|
| MVP (10/10 screens) | COMPLETE, deployed |
| PA-11 Clinical Insight Engine PR-A + PR-B | COMPLETE, deployed (PRs #50/#51/#52) |
| PA-11 PR-C (metrics detail insight card) | DEFERRED |
| OCR Lab Upload (Azure DI) | COMPLETE, deployed |
| OCR Hardening v1 (SI + incompatible units) | COMPLETE, e1aac34 |
| OCR Hardening v2 (hospital profiles + bounds) | COMPLETE, uncommitted this session |
| Per-screen Liquid Glass rebuild | DEFERRED (feat/patient-screens-liquid-glass-pass2) |
| Device Setup Hub | COMPLETE, deployed |

## Backend Status
| Area | State |
|---|---|
| All patient endpoints | COMPLETE |
| Lab OCR pipeline | COMPLETE + hardened |
| Adherence (last-action-wins) | COMPLETE, deployed |
| Adherence unbounded query fix | PENDING (P1) |
| Dashboard RCA | PR #47 OPEN, not merged |

## Azure Staging
- Region: southeastasia (rg-metocare-staging)
- Last confirmed green deploy: b512ee6 (PR #49 PX-02D + PA-11)
- DB head: hmbk_backfill (no new migrations this session)
- OCR flags: MCP_FEATURE_OCR=true, cloud=false, ai_assistant=false

## Open PRs
| # | Title | Status |
|---|---|---|
| #47 | Dashboard RCA redesign | OPEN, not merged |
| #48 | Care Plan Liquid Glass | OPEN |
| #53 | V3 Decision-First UI | OPEN |

---

## Remaining Backlog

### P1
- Adherence unbounded query: adherence_summary() queries all_records with no LIMIT
- PR #47 Dashboard RCA: merge or close
- Deploy OCR hardening to staging + Vinmec upload smoke test

### P2
- PA-11 PR-C: insight card in /metrics/[metricType]

### P3 (DEFERRED — do not start)
- Doctor phase (PAUSED)
- Native App (not started)
- Device Integrations (not started)
- AI coach confirm-action (backend gaps: causes/outcome fields)

---

## Lessons Learned
1. En dash in Python code inside JS template literals in Workflow scripts causes a parse error; use hyphen directly
2. Fix-loop in Workflow: use string concatenation instead of escaped backticks
3. mIU/L != mIU/mL — both must appear in incompatible_units for mg/dL biomarkers
4. frozen=True + field(default_factory=dict) is incompatible; use non-frozen @dataclass for HospitalProfile
5. ECC Gateguard fires on first edit per file; must state importers + callers + schema before proceeding
6. Workflow scripts are JS not TypeScript — no type annotations, no Unicode escapes in embedded code
