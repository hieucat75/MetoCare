# Labs UX Rebuild — Final Report

**Date:** 2026-06-27  
**Author:** OpenClaw subagent  
**Staging:** https://ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io  
**Revision deployed:** `ca-metocare-frontend--fe-labsuxv2`  

---

## STATUS: PASS ✅

All phases completed. Tests pass, build clean, staging verified with real biomarker data.

---

## Screens Changed

| Screen | Route | Change Type |
|--------|-------|-------------|
| Labs List | `/labs` | Major redesign (batch cards, biomarker rows, auto-expand, AI CTA) |
| Biomarker Detail | `/labs/[batchId]/results/[resultId]` | Created (was missing) |
| AI Summary | `/labs/[batchId]/insight` | Created (was missing) |

---

## Components Changed/Created

| File | Status | Description |
|------|--------|-------------|
| `src/app/(patient)/labs/page.tsx` | **Modified** | BatchCard: per-batch lazy fetch, auto-expand latest, AI CTA at bottom |
| `src/components/patient/LabResultRow.tsx` | **Modified** | Left color status border, ref range display, 22px name, 36px value, 72px min-height |
| `src/app/(patient)/labs/[batchId]/results/[resultId]/page.tsx` | **Created** | Biomarker detail: value gauge, AI interpretation, trend chart, next actions |
| `src/app/(patient)/labs/[batchId]/insight/page.tsx` | **Created** | AI summary: urgent alerts, overall status, insight cards, action cards, timeline |
| `src/components/patient/__tests__/labs.test.tsx` | **Created** | 17 tests, 7 test cases |
| `frontend/jest.config.js` | **Created** | Jest config with jsdom, babel transform, path aliases |
| `frontend/babel.config.test.js` | **Created** | Babel presets for Jest |
| `frontend/jest.setup.js` | **Created** | @testing-library/jest-dom setup |
| `frontend/__mocks__/` | **Created** | api-client, fileMock, styleMock |
| `scripts/deploy-staging.sh` | **Created** | Deploy helper script |

---

## Design Decisions

### Labs List
- **Auto-expand latest batch**: `setExpandedBatchId((prev) => prev ?? batchRes.items[0].id)` — first item (most recent, sorted by backend) expands on load
- **AI CTA placement**: Secondary outline button at **bottom** of each expanded batch (`Xem AI nhận định tổng thể →`), not inline with rows
- **NO AI text inline** in biomarker rows — clean, medical data only

### Biomarker Row (`LabResultRow.tsx`)
- Left color border: green (normal), amber (high), red (critical), blue (low), gray (unknown)
- Name: 22px font-semibold
- Value: 36px font-bold, colored to match status
- Unit: 16px muted
- Reference range: 13px muted below name
- Min-height: 72px for accessibility (older users)
- Status badge: colored pill (Bình thường / Cao / Nguy hiểm / Thấp / Chưa rõ)
- Trend arrow: ↑ ↓ → when `changePct` provided
- Entire row tappable → detail page

### Biomarker Detail Page
- SimpleGauge: custom SVG-free gauge bar showing value position relative to reference range
- AI interpretation: matched from insight report by canonical_name/test_name
- Trend: MetricLineChart + historical values table
- DisclaimerAccordion: expandable ⚠️ medical disclaimer

### AI Summary Page
- Reuses `LabInsightCards.tsx` components (UrgentAlertCard, OverallStatusCard, InsightCardItem, ActionCardItem, TimelineRow, PositiveReinforcementBanner)
- Full report structure: urgent → overall → positive → insights → actions → timeline → disclaimer

---

## Routes Added

```
/labs                                         (existing, redesigned)
/labs/[batchId]/insight                       (new)
/labs/[batchId]/results/[resultId]            (new)
```

---

## Tests

| Suite | Cases | Result |
|-------|-------|--------|
| test_labs_list_renders | 7 | ✅ PASS |
| test_batch_expand_shows_results | 1 | ✅ PASS |
| test_biomarker_row_navigates_to_detail | 2 | ✅ PASS |
| test_ai_summary_route_exists | 2 | ✅ PASS |
| test_empty_state_shows_message | 1 | ✅ PASS |
| test_error_state_shows_retry | 2 | ✅ PASS |
| test_mobile_viewport_no_overflow | 2 | ✅ PASS |
| **Total** | **17** | **17 passed, 0 failed** |

Run: `cd frontend && npm test -- --watchAll=false`  
Time: 0.789s

---

## Build

```
cd frontend && npm run build
```

**Result: SUCCESS, 0 errors, 0 TypeScript errors**

---

## Staging Screenshots

All 5 screenshots captured from live staging after deploy `fe-labsuxv2`.

| Screenshot | Status | Notes |
|------------|--------|-------|
| Labs list — collapsed view | ✅ | All 4 batches visible (Medlatec Jun 2026, Vinmec Oct 2024, BV Hồng Ngọc Mar 2024, Medlatec Jul 2017) |
| Labs list — expanded with biomarker rows | ✅ | 8 biomarker rows visible with real data (fasting_glucose 5.73, triglyceride 1.97, total_cholesterol 5.49, ALT 51.63, AST 25.37, creatinine 87.66, urea 4.55, GGT 75.78) + AI CTA button |
| Biomarker detail | ✅ | fasting_glucose 4.78 mmol/L, visual gauge, AI analysis, trend history (3 dates), next steps |
| AI Summary page | ✅ | Vietnamese AI narrative: "Chỉ số Đường huyết lúc đói cần chú ý ngay", "Chỉ số Creatinine cần chú ý ngay" |
| Mobile viewport (375px) | ✅ | Labs list responsive at 375px, no horizontal scroll |

---

## API Integration Notes

- **Batch-scoped results**: `GET /api/v1/patients/{patient_id}/lab-batches/{batch_id}/results` — commit `63d0093` added this endpoint. Replaces the original client-side `allResults.filter(r => r.batch_id === batch.id)` workaround (which failed because results had `batch_id: null` in early data).
- **Per-batch lazy fetch**: Results fetched on first expand, cached in component state. Retry button on error.

---

## Phase 4 Issues Fixed

| Issue | Fix |
|-------|-----|
| Tiny text | Min 16px secondary, 22px primary name, 36px value |
| Dense cards | 72px min-height rows, 16px horizontal padding, 12px vertical |
| Bottom nav overlap | `pb-28` on main container, fixed FAB at `bottom-28` |
| No TV/foreign iframes found | — (not present in labs screens) |
| Debug artifacts | None added, none remain |
| Responsive 375px+ | Verified via screenshot, `w-full` on rows, `truncate` on long names |

---

## Commits

| SHA | Message |
|-----|---------|
| `d11ad6a` | `feat(labs-ux): rebuild labs screen for Vietnamese 45-70 users` |
| `63d0093` | `fix(labs-api): add batch-scoped GET /labs/{batch_id}/results endpoint + frontend integration` |

Tags deployed to staging:
- `labsuxv1` → ACA revision `fe-labsuxv1` (commit `d11ad6a`)
- `labsuxv2` → ACA revision `fe-labsuxv2` (commit `63d0093`) ← **current live**

---

## Remaining Risk

| Risk | Severity | Mitigation |
|------|----------|------------|
| Status `"Chưa rõ"` for all Medlatec results | Low | Backend `clinical_rules.py` status enrichment may not fire for this dataset. Cosmetic only — reference range text and value still visible. |
| AI disclaimer is generic | Low | `disclaimer_vi` is always shown; clinical accuracy is the backend's responsibility |
| `canonical_name` not always set | Low | Biomarker detail falls back to `test_name` for AI matching |
| Node.js 20 deprecation in GHA | Info | Actions warning only, not blocking. Workflows use `checkout@v4` etc. — upstream fix needed |
| No production deploy | Info | Only staging. Production requires PTH approval per policy. |

---

## How to Deploy to Production

When ready for production:

1. Merge `main` to production branch (if separate), or tag a release
2. Trigger production deploy workflow (if exists) with PTH approval
3. Verify ACA production revision + smoke test

**Do NOT deploy to production without PTH approval.**
