# Patient Dashboard — Root Cause Analysis + Redesign (P1)

**Status:** Phase 1 (RCA) complete · Phase 2 (redesign) in progress
**Branch:** `feat/patient-dashboard-rca-redesign`
**Author:** Claude (agent) · 2026-06-21
**Merge policy:** DO NOT MERGE / DO NOT DEPLOY — open PR for PTH review.

---

## STATUS

Observed bug: a patient with recorded health metrics (glucose, cholesterol, LDL,
HDL, …) opens `/dashboard` and the metabolic-score hero card shows
**"Chưa có điểm chuyển hóa"** ("No metabolic score yet"), while `/metrics`
correctly displays every value. Functional bug + UX failure.

---

## PHASE 1 — ROOT CAUSE ANALYSIS

### Data flow — Metrics page (WORKS)

```
/metrics page
  └─ getMetrics(patientId, {limit:300})            frontend/src/lib/api/patient.ts
       └─ GET /patients/{id}/metrics               backend/app/api/v1/routes/health.py
            └─ health_metrics.list_metrics()        reads HealthMetric table  ← REAL DATA
                 └─ SELECT * FROM health_metrics WHERE patient_id = ?
  └─ groupMetricsByCategory(metrics, catalog)       lib/metrics/kpi.ts → renders KPI cards
```

The metrics page reads the **`health_metrics`** table directly. Every manually
logged metric and every lab-promoted metric lives there, so it always shows data.

### Data flow — Dashboard hero (BROKEN)

```
/dashboard page  (metabolic-score hero)
  └─ getLatestMetabolicScore(patientId)             frontend/src/lib/api/patient.ts
       └─ GET /patients/{id}/metabolic-scores?limit=1   backend/app/api/v1/routes/patients.py
            └─ risk_score_svc.get_history()          reads RiskScore table  ← SEPARATE TABLE
                 └─ SELECT * FROM risk_scores WHERE patient_id = ?   ← EMPTY for normal patients
       └─ returns null  →  hero renders "Chưa có điểm chuyển hóa"
```

The dashboard hero reads a **different table — `risk_scores`** — which holds
*pre-computed* metabolic-score snapshots. It is NOT derived from `health_metrics`
at read time.

### Divergence point — who writes `risk_scores`?

`grep` for the only writer of `RiskScore`:

```
app/services/risk_score.py:24   def save_score(...)        ← the only persister
app/api/v1/routes/ai.py:149     risk_score_svc.save_score(...)   ← the only caller
```

`save_score()` is called from exactly one place: `POST /ai/metabolic-score`
(`ai.py:124`). That endpoint is:

1. **Behind the AI consumer gate** — `Depends(_require_ai_consumer)`
   (`ai.py:55,127`). The `ai_assistant` feature flag is **OFF** on staging
   (and the AI entry point on the dashboard is flag-gated off too).
2. **Never called by the normal patient flow.** Logging a metric goes
   `POST /patients/{id}/metrics → health_metrics.create_metric()`
   (`app/services/health_metrics.py:40`). That function persists the
   `HealthMetric` and **does nothing else** — no score recompute, no
   `save_score()`.

**Therefore `risk_scores` is permanently empty for every real patient**, and the
dashboard hero shows the false-empty state no matter how many metrics exist.

This maps to spec cause **C** (metabolic-score calculation service is never
triggered) compounded by **B** (dashboard uses a different datasource than the
metrics page).

### Secondary divergence — dashboard metrics grid

`dashboard/page.tsx:105` only requests **three hard-coded metric types**:

```ts
const metricTypes = ['fasting_glucose', 'weight', 'blood_pressure_systolic']
```

A patient whose data is cholesterol / LDL / HDL / triglyceride (e.g. promoted
from a lab report) sees **"Chưa có chỉ số nào"** in the dashboard grid too — even
though `/metrics` lists them all. This compounds the "empty dashboard despite
data" impression.

### Unit landmine (must handle in the fix)

The same `metric_type` can be stored in **different units**:

- Manual self-report uses the canonical map in `lib/api/patient.ts`
  (`fasting_glucose` → **mg/dL**, `triglyceride` → mg/dL, `hdl` → mg/dL).
- Lab-promoted rows (`lab.py:_promote_row`) store the lab's **native unit** —
  Vietnamese labs report glucose/lipids in **mmol/L** (the spec examples:
  "Đường huyết đói 5.73 mmol/L", "LDL-C 3.59 mmol/L").

The domain scorer `app/domain/metabolic_score.py` hard-codes **mg/dL** thresholds
(glucose ≥ 126, triglyceride ≥ 150 …). Feeding a raw mmol/L value (5.73) into it
would score 0 points → a wrong score. The fix must convert units (or rely on the
already-correct per-metric `status`).

### Root Cause (one sentence)

> The dashboard's metabolic-score hero reads the `risk_scores` table, whose only
> writer is the AI-gated `POST /ai/metabolic-score` endpoint that the patient app
> never calls — so the table is always empty and the hero renders a permanent
> false "no data" state, while `/metrics` reads `health_metrics` directly and
> shows the real data.

---

## FIX

Two independent defects → two fixes, both **read-only / no DB migration**:

### Fix 1 — live metabolic score (backend, root cause)

Add a read-only endpoint that computes the score **on demand from the latest
`health_metrics` + profile**, decoupled from the AI gate and unit-aware:

- `GET /patients/{id}/metabolic-score/live` → `{score, band, risk_level,
  factors[], inputs_used, computed_at}` or `null` only when there are genuinely
  no usable inputs.
- New service `app/services/metabolic_live.py`: pulls the latest reading per
  relevant metric type, converts mmol/L → mg/dL where needed, reads
  `waist_cm`/gender from the profile, calls the existing pure domain
  `metabolic_score.compute()`. **Does not persist** (idempotent, always current).
- PATIENT-own + admin RBAC, mirroring the metrics route.

### Fix 2 — dashboard never shows false-empty (frontend)

- Dashboard fetches the **full** metrics list (`getMetrics limit 300`) instead of
  three hard-coded types, and derives the summary from the existing, unit-safe
  per-metric `status` field (classified against correct reference ranges for both
  manual and lab rows) using the existing `lib/metrics/kpi.ts` + lab catalog.
- The hero shows a real status ("Ổn định" / "Cần chú ý" / "Nguy cơ chuyển hóa")
  whenever any metric exists. The empty state appears **only** when the patient
  truly has zero metrics.

---

## PHASE 2 — DASHBOARD UX REDESIGN

Replace the widget-collection dashboard with an action-oriented 6-section layout
(Claude Design: Mint Soft UI, Liquid Glass, mobile-first, large touch targets):

1. **Health Summary Hero** — overall status + abnormal-indicator count + last
   update. No empty decorative card.
2. **Việc cần làm hôm nay** — actionable tasks (complete profile, log overdue
   metric, pending lab review, today's meds).
3. **Top Indicators Requiring Attention** — max 3 abnormal metrics.
4. **Health Trend** — 7/30/90-day improving/worsening/stable per key metric.
5. **Latest Lab Results** — date + abnormal count → Labs module.
6. **Today's Medication** — today's meds only.

---

## VERIFICATION (to be attached to PR)

- Backend: pytest for `metabolic_live` (no-data / partial / full / mmol/L
  conversion / no-AI-gate).
- Frontend: Playwright iPhone screenshots for **no-data / partial-data /
  full-data** states (before/after).
- Acceptance: a patient with metrics never sees a false empty state; metrics-page
  values appear in the dashboard summary; the metabolic score reflects real data.
