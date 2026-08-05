# PR #47 Audit Report — Dashboard RCA vs Current Main

**Date:** 2026-07-07
**Branch:** feat/patient-dashboard-rca-redesign
**Base commit compared:** f2dc996b37a2946c87fbc10e50ef89a4843f712c (release(ocr): Azure Document Intelligence OCR fallback v1.4.0 — the point where PR #47 diverged from main)
**Main HEAD:** ec25db4b7e8835b6e0ef60a46eb5b753a9264813 (feat(doctor): add Meto clinical copilot)

---

## Summary

**VERDICT: CLOSE_AS_SUPERSEDED**

All useful work in PR #47 was merged into main via **PR #49** (commit `b512ee6`, 2026-06-22), which cherry-picked the RCA backend fix and the 6-section dashboard redesign as part of a broader Soft-UI + live-score increment. Main has since advanced significantly beyond PR #47 (medication adherence, health-summary API, Neu design system, AI copilot card, marketplace entry, clinical insights, lab unit integrity, and more).

The `git diff origin/main...origin/feat/patient-dashboard-rca-redesign` shows **1,276 insertions and 369 deletions**, but the direction is reversed — main is a **superset** of PR #47, not the other way around. PR #47 code that appears as "additions" in the diff are things main deleted when it evolved past them (old widget layout, `GlassCard`/`MintButton` components, etc.).

---

## Change Matrix

### ALREADY_IN_MAIN

| File | Change | Evidence |
|------|--------|----------|
| `backend/app/services/metabolic_live.py` | Entire new file — live metabolic score service (117 lines) | Identical content in main; introduced in commit `b512ee6` (PR #49). Only diff: main adds `HealthMetric.deleted_at.is_(None)` filter (line 65) — a correctness fix that PR #47 is missing. |
| `backend/app/schemas/risk_score.py` | `LiveScoreFactor` + `LiveScoreOut` schemas (29 lines added) | **Zero diff** between PR #47 and main (`diff` exits 0). Merged in PR #49, commit `b512ee6`. |
| `backend/app/api/v1/routes/patients.py` | `GET /{patient_id}/metabolic-score/live` endpoint | Present in main at lines 277-328. Core logic identical; main version differs only in import ordering and has additional endpoints (adherence, insight) PR #47 lacks. |
| `backend/tests/api/test_metabolic_score_live_api.py` | Full 194-line test suite for live score endpoint | **Zero diff** between PR #47 and main (`diff` exits 0). File lives at `backend/tests/api/` in both. |
| `docs/agent/DASHBOARD_RCA_REDESIGN.md` | 169-line RCA design document | **Zero diff** between PR #47 and main (`diff` exits 0). |
| `frontend/src/lib/dashboard/summary.ts` | `buildDashboardSummary`, `DashboardSummary`, `IndicatorConcern`, `TrendMover` interfaces | Core logic present in main (79 of 171 PR #47 lines exist in main). Main's version is more advanced: adds `original_value`/`original_unit`/`display` fields for clinical integrity, `computeAttentionReason()`, and `reason` field on concerns — all additions post-PR #49. |
| `frontend/src/lib/api/patient.ts` — `getLiveMetabolicScore` | New function + `LiveMetabolicScore` interface | Present in main at lines 327–348 (exact match). |
| `frontend/src/app/(patient)/dashboard/page.tsx` — RCA datasource switch | Switched from `getLatestMetabolicScore` (risk_scores table) to `getLiveMetabolicScore` (live compute) | Present in main. Data fetch pattern in main is identical in intent, more complete in execution (adds `getHealthSummary`, `getAdherenceSummary`, focus-refetch throttle). |

### STILL_MISSING

None. Every substantive fix from PR #47 is present in main, and main has extended all of them.

The only line PR #47 has that main's `metabolic_live.py` does **not** have is the absence of the `deleted_at.is_(None)` filter — but this is a case where **PR #47 is worse than main**, not better. Main added the soft-delete filter as a correctness improvement.

### OBSOLETE

| File | Change in PR #47 | Why Obsolete |
|------|-----------------|--------------|
| `frontend/src/app/(patient)/dashboard/page.tsx` — `GlassCard`, `MintButton`, `SectionHeader` components | PR #47 used an early glass-kit component set (`GlassCard`, `MintButton`, `SectionHeader`) | Main replaced these with the **Neu design system** (`NeuCard`, `NeuButton`, `NeuIconButton`, `NeuBadge`) via commits after PR #49. PR #47's component choices are no longer consistent with the live codebase. |
| `frontend/src/app/(patient)/dashboard/page.tsx` — 6-section layout (Sections 1–6 as flat `<section>` tags) | PR #47's layout: Hero → Tasks → Indicators → Trend → Labs → Meds | Main evolved to a different layout: AiCopilotCard (flagship first) → Marketplace → AdherenceReminderSection → HealthAlertsSection. The concept is preserved but the implementation and section order are different. Applying PR #47's layout now would **break** the current UX (removes Meto copilot card, marketplace entry, adherence module). |
| `frontend/src/lib/api/patient.ts` — trailing-comma reformatting | Prettier-style cleanup removing trailing commas from function signatures (~59 lines changed) | Main has since re-added types and functions with consistent style of its own. These cosmetic edits are already superseded by subsequent commits. |
| `frontend/src/lib/dashboard/summary.ts` — simplified `classifySeries` / `buildDashboardSummary` | PR #47 version lacks `reason`, `original_value`, `original_unit`, `display`, `computeAttentionReason()` | Main's version (added in clinical-integrity sprint, commits `aa7f306`, `47a6575`) is a strict superset. Reverting to PR #47's version would break the metrics page and health alerts. |

### CONFLICTING

| File | PR #47 Change | Conflicts With |
|------|--------------|----------------|
| `frontend/src/lib/api/patient.ts` — missing MetricType values | PR #47's `patient.ts` lacks `temperature`, `sleep_hours`, `steps`, `activity_minutes`, `bmi` in the `MetricType` union, and lacks corresponding `metricLabel`/`metricUnit`/`normalRange` entries | Main added these types in the P0 device-ecosystem sprint (`7df41a5`). Applying PR #47's `patient.ts` changes would remove metric types used by the metrics-log page and device ecosystem. |
| `frontend/src/lib/api/patient.ts` — missing `HealthMetric` fields | PR #47 lacks `original_value`, `original_unit`, `display`, `clinical_message`, `is_critical` on `HealthMetric` | Clinical-integrity P0 fix (`aa7f306`): these fields are now required for correct lab display. Removing them breaks the clinical display pipeline. |
| `frontend/src/lib/api/patient.ts` — missing `getHealthSummary`, `getAdherenceSummary`, `logAdherence` | PR #47 has no adherence or health-summary API functions | Main's dashboard depends on these (adherence section, AI copilot card). Replacing `patient.ts` with PR #47's version would break medication adherence tracking. |
| `backend/app/api/v1/routes/patients.py` — missing imports/routes | PR #47 lacks `FeatureFlag`, `is_enabled`, `clinical_insight` service, `AdherenceSummaryOut`, `MedicationAdherenceCreate/Out` imports and their corresponding routes | Main added adherence endpoints (`90a03c1`) and insight endpoints (`db9a721`). PR #47's `patients.py` is an older snapshot missing these. |

---

## Root Cause Fix Status

**Was the metabolic score dashboard bug fixed in main? YES**

**Evidence:**
- **Commit `b512ee6`** (PR #49, merged 2026-06-22, one day after PR #47 was created 2026-06-21): "feat(patient): PX-02D foundation — glass kit + RCA live metabolic-score backend. Fixes the P1 false-empty dashboard datasource (risk_scores -> live from health_metrics)."
- `backend/app/services/metabolic_live.py` — present in main at `HEAD` (ec25db4), confirmed by `git show origin/main:backend/app/services/metabolic_live.py`.
- `GET /patients/{id}/metabolic-score/live` endpoint — present in main at `patients.py` lines 277–328.
- Main's version is **more correct** than PR #47: it adds `HealthMetric.deleted_at.is_(None)` filter (line 65 of `metabolic_live.py`) so soft-deleted metrics are excluded from scoring. PR #47 is missing this filter.
- Frontend: `getLiveMetabolicScore()` and `LiveMetabolicScore` interface present in main's `patient.ts` (lines 327–348); dashboard `page.tsx` in main calls it correctly.

---

## 6-Section UI Redesign Status

PR #47 defines 6 sections:
1. **Health Summary Hero** — overall status + metabolic score
2. **Việc cần làm hôm nay** — actionable task list
3. **Top Indicators Requiring Attention** — max 3 abnormal metrics
4. **Health Trend** — improving/worsening metrics
5. **Latest Lab Results** — recent lab card
6. **Today's Medication** — active meds

**Status in main: 6/6 concepts present, 0/6 sections implemented in PR #47's exact form.**

| Section | Status in main |
|---------|---------------|
| 1. Health Summary Hero | ✅ Present — `HeroSummaryCard` / `AiCopilotCard` (more advanced: adds Meto AI summary + health-summary API integration) |
| 2. Today's Tasks | ✅ Present — `AdherenceReminderSection` covers medication tasks; profile-complete and pending-lab tasks handled elsewhere |
| 3. Top Abnormal Indicators | ✅ Present — `HealthAlertsSection` (more advanced: deep-links to Meto AI biomarker detail pages) |
| 4. Health Trend | ✅ Present — `groupMetricsByCategory` + MetricSeries trend data feeds both the health alerts and the copilot card |
| 5. Latest Lab Results | ✅ Present — labs fetched (`getLabs` limit 5) and displayed in the dashboard |
| 6. Today's Medication | ✅ Present — `AdherenceReminderSection` renders `today_medications` from the adherence API with tap-to-confirm UX |

**Verdict on redesign:** Main's dashboard implements all 6 conceptual sections but with a more evolved UX than PR #47 (Neu design system instead of GlassCard, adherence-aware medication section, Meto AI copilot as flagship first card, marketplace entry). PR #47's 6-section layout cannot be applied to main without removing significant functionality.

---

## Recommended Action

**Close PR #47 as superseded by PR #49 (commit b512ee6) and subsequent evolution.**

Steps:
1. Close PR #47 on GitHub with label "superseded" and reference PR #49 in the closing comment.
2. Delete the branch `feat/patient-dashboard-rca-redesign` (or archive it) — it has served its purpose.
3. No cherry-picks needed: every useful fix is already in main and main has extended them further.

**Note for PTH:** The one subtle difference worth noting is that PR #47's `metabolic_live.py` is missing the `deleted_at.is_(None)` soft-delete filter that main has. This means if PR #47 had been merged instead of PR #49, the live score would incorrectly include soft-deleted metrics. The current state in main is correct.

---

## Files to cherry-pick (if CREATE_FRESH_PR)

**N/A — verdict is CLOSE_AS_SUPERSEDED.**

No files need cherry-picking. All useful changes from PR #47 are already in main, in improved form.

---

## Appendix — Key Commits That Supersede PR #47

| Commit | Description | What it supersedes from PR #47 |
|--------|-------------|-------------------------------|
| `b512ee6` (PR #49, 2026-06-22) | PX-02D: Soft-UI foundation + live-score dashboard | All backend RCA files, `summary.ts`, `getLiveMetabolicScore`, initial dashboard redesign |
| `7df41a5` | feat(patient): P0 sprint — device ecosystem, medication adherence UI | Missing MetricTypes, missing adherence API |
| `90a03c1` | feat(adherence): complete medication adherence end-to-end | Today's medication section (Section 6) |
| `aa7f306`, `47a6575` | fix(clinical-integrity): lab unit display | `original_value`/`original_unit`/`display` fields, `computeAttentionReason` |
| `db9a721` + `c3473a8` | feat(patient-insight): Insight Layer + AI Health Intelligence | HealthSummary API, advanced copilot card |

---

## Closure Record

**Action taken:** CLOSE_AS_SUPERSEDED
**Closed:** 2026-07-07T15:24:53Z
**Closed by:** OpenClaw (coordinator)
**Branch deleted:** `feat/patient-dashboard-rca-redesign` — confirmed removed from remote
**Closing comment posted:** Root-cause fix merged via PR #49 / b512ee6; all 8 files superseded; merging would reintroduce obsolete code
**Cherry-picks:** NONE
**Audit report:** `docs/agent/PR47_AUDIT_REPORT.md`
