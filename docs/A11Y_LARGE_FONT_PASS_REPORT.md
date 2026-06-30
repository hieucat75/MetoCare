# A11Y Large Font Pass — Metocare Patient App

**Commit:** `845833c`  
**Branch:** `main`  
**Date:** 2026-06-30  
**CI Status:** ✅ All checks passed (ruff lint + backend tests + frontend typecheck)

---

## Objective

Comprehensive large-font accessibility pass across the Metocare patient frontend. No layouts, colors, branding, or component architecture changed. Only font sizes, line-heights, and minimal spacing for readability.

---

## Typography Rules Applied

| Element | Before | After |
|---|---|---|
| Body text (paragraphs) | 13–15px | 17–18px |
| Secondary/support text | 11–13px | 15–16px |
| Metric names | 13px | 16–20px |
| Metric values (KpiCard) | 26px | 40px |
| Metric values (hero NeuStat) | 30px | 40px |
| Metric values (dashboard tile) | 28px | 40px |
| Units | 12–13px | 18–20px |
| Badge text (neu-badge) | 12px (CSS) | 14px (CSS) |
| Badge text (inline overrides) | 10.5–11px | 13–14px |
| Card/section titles | 14–17px | 18–22px |
| Section headers (h2) | 14–20px | 24px |
| AI Copilot headings | 15–20px | 20–24px |
| AI Copilot paragraphs | 13–15px | 17–18px |
| AI Copilot bullet items | 14px | 17px |
| Navigation labels | 10px | 13px |
| Reference ranges | 11px | 15–16px |
| Chart legends/axis | 10.5–12px | 15px |
| Trend dates | 12px | 15–17px |
| neu-caption (mono) | 10.5px | 13px |

## Global CSS Changes

- `.patient-app` base font-size: 18px
- `.patient-app` line-height: 1.6
- `.neu-badge` font-size: 14px (was 12px)
- `.neu-caption` font-size: 13px (was 10.5px)
- `.patient-app h2` font-size: 1.5rem (24px), bold
- `.patient-app h3` font-size: 1.375rem (22px), semibold
- `.patient-app .bottomnav-btn span` font-size: 13px (was system 10px)

---

## Files Changed

### Global CSS
- `src/app/globals.css` — Added A11Y large font layer; bumped `.neu-badge` and `.neu-caption`

### Shared Components
- `src/components/nav/PatientBottomNav.tsx` — Nav labels 10px → 13px
- `src/components/patient/neu/NeuStat.tsx` — Metric value 30px → 40px; unit 13px → 20px
- `src/components/patient/neu/NeuBadge.tsx` — (inherits from `.neu-badge` CSS fix)
- `src/components/patient/metrics/MetricKpiCard.tsx` — Value 26px → 40px; unit 13px → 18px; label 13px → 16px; badge 11px → 13px
- `src/components/patient/metrics/MetricCategoryGroup.tsx` — Category heading 15px → 20px
- `src/components/patient/metrics/RefRangeBar.tsx` — Reference range labels 11px → 15px
- `src/components/patient/metrics/DangerAlertBanner.tsx` — Alert text 14px → 18px; link 12px → 16px
- `src/components/patient/LabResultRow.tsx` — Status badge 12px → 14px; reference range 13px → 16px
- `src/components/patient/LabInsightCards.tsx` — All insight card body text upgraded; section headers → 18–20px
- `src/components/labs/ExplanationSection.tsx` — Already at 18–24px (no changes needed; verified)
- `src/components/patient/NarrativeSection.tsx` — Section card titles 15px → 18px; body 14px → 17px; heading 20px → 24px; disclaimer 12px → 15px

### Page Files

#### AI Copilot (Priority 1)
- `src/app/(patient)/ai-copilot/page.tsx` — Redirect only; no changes needed
- `src/app/(patient)/ai-copilot/overview/page.tsx` — All body text 13–16px → 17–18px; section labels 12px → 15px; action heading 17px → 20px
- `src/app/(patient)/ai-copilot/biomarker/[key]/page.tsx` — Biomarker name 18px → 22px; status pill 14px → 16px; all tab body text 14px → 17px; chart labels 12px → 15px; values 24px → 32px; trend dates 12px → 15px
- `src/app/(patient)/ai-copilot/coach/page.tsx` — Greeting 20px → 22px; all body 12–14px → 16–18px; streak/goal labels upgraded
- `src/app/(patient)/ai-copilot/journey/page.tsx` — Heading 20px → 24px; weight/BP values 30px → 40px; event text 14px → 17px; AI annotations 14px → 17px

#### Dashboard (Priority 2)
- `src/app/(patient)/dashboard/page.tsx` — Metric tile values 28px → 40px; units 13px → 18px; labels 13px → 16px; alert labels 15px → 18px; AI focus line 15px → 18px; medication card text 15px → 18px; adherence stats 16px → 18px

#### Health Metrics (Priority 3)
- `src/app/(patient)/metrics/page.tsx` — Uses MetricKpiCard + MetricCategoryGroup (both upgraded)
- `src/app/(patient)/metrics/[metricType]/page.tsx` — Page title 20px → 24px; period tabs 13px → 15px; avg value 24px → 32px; chart legend 10.5px → 15px; history heading 14px → 18px; stat chips 10.5px/17px → 14px/20px; history rows 14px → 18px; timestamps 11.5px → 15px

#### Labs (Priority 4)
- `src/app/(patient)/labs/page.tsx` — Batch badge 12px → 14px; upload date 12px → 15px
- `src/app/(patient)/labs/[batchId]/results/[resultId]/page.tsx` — Uses ExplanationSection (already sized correctly)
- `src/app/(patient)/labs/upload/OcrReviewCard.tsx` — Not modified (verified sizes acceptable)

#### Secondary Pages (Priority 5)
- `src/app/(patient)/medications/page.tsx` — Med name 16px → 18px; meta 13.5px → 16px; note 13px → 15px
- `src/app/(patient)/nutrition/page.tsx` — Description 15px → 18px; calories 16px → 18px; time 12px → 14px; macros 13px → 15px; AI tip 13px → 16px
- `src/app/(patient)/care-plan/page.tsx` — Plan title 17px → 20px; content 15px → 18px; page title 20px → 24px
- `src/app/(patient)/profile/page.tsx` — Info rows 14px → 17px; link rows 14.5px → 17px
- `src/app/(patient)/settings/page.tsx` — Page title 20px → 24px; account info rows 14px → 17px; notification labels 14px → 17px; role badge 12px → 14px

---

## What Was NOT Changed

- Doctor / admin portal directories (untouched by design)
- Layout structure (flex, grid, direction)
- Colors, gradients, shadows
- Component logic, props, API calls
- Non-text elements (icons, borders, backgrounds)
- `ExplanationSection.tsx` — already had correct sizes (18–24px) from prior work

---

## Verification

- `npx tsc --noEmit --project tsconfig.build.json` → 0 errors
- `local-ci FAST TIER` → ruff lint ✅, backend tests ✅, frontend typecheck ✅
