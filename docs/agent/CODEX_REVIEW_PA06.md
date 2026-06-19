# Codex Review — PA-06 Patient Dashboard + Health Metrics

**Date:** 2026-06-19  
**Branch:** `feature/pa06-patient-dashboard-metrics`  
**Base:** `main` (`25e70e3`)  
**Reviewer:** Codex (codex-cli v0.137.0 / gpt-5.5)  
**Session:** swift-bloom

---

## Verdict

**REQUEST_CHANGES** — 2 P1 findings, 0 P0

---

## P0 Findings (block merge)

- [none]

---

## P1 Findings (fix before merge)

### P1-1 — Missing `@/lib/api/patient` in tracked files

**Location:** `frontend/src/app/(patient)/dashboard/page.tsx:29`  
**Also affects:** `frontend/src/app/(patient)/metrics/page.tsx:22`

> In a clean checkout, `@/lib/api/patient` does not exist in the tracked patch,
> so the dashboard and metrics pages fail module resolution and the frontend
> cannot build. The local build only succeeds because an untracked
> `frontend/src/lib/api/patient.ts` is present; add that module to the patch
> or use the tracked API clients.

**Fix required:** Git-add `frontend/src/lib/api/patient.ts` to the branch commit so it is tracked.

---

### P1-2 — Parallel refresh race — token family revocation on concurrent 401s

**Location:** `frontend/src/lib/api/client.ts:74–75`

> When an access token expires while the dashboard issues its parallel requests,
> every 401 independently refreshes the same single-use refresh token.
> The first request rotates it, while subsequent requests trigger the backend's
> reuse-detection and revoke the entire token family, logging the user out.
> Share one in-flight refresh promise so all failed requests retry with the
> same newly issued token.

**Fix required:** Serialize token refresh — use a single shared `refreshing` promise
(a module-level variable that multiple concurrent 401 handlers await).

---

## P2 Observations (non-blocking)

- `metrics/page.tsx` (in diff at git) is the old 432-line fe-01 version importing `@/lib/api/patient`.
  The replacement 235-line version using `@/lib/api/metrics` is untracked (local file overwrites the git file).
  This is confusing but resolved by fixing P1-1 (adding patient.ts to git).
- `DESIGN_SYSTEM.md` has a trailing whitespace on line 107.
- Two design system components use `<img>` instead of `next/image` (`PatientSummaryHeader`, `Sidebar`).

---

## Contract Compliance

| Endpoint | Method | Contract Match |
|---|---|---|
| `POST /patients/{id}/metrics` | logMetric | ✅ |
| `GET /patients/{id}/metrics` | listMetrics | ✅ (returns array, contract says array) |
| `GET /patients/{id}/metrics/trend` | getMetricTrend | ✅ |
| Auth token refresh | client.ts | ⚠️ Race condition (P1-2) |

---

## Summary

Build passes locally but relies on an untracked file (`patient.ts`).
The core health metrics API client (`metrics.ts`) is correct and contract-compliant.
The token refresh race is a real bug that will log out users in production
when the dashboard's concurrent fetch hits an expired token.
Both P1s are straightforward to fix.

---

## Required Fixes Before Merge

1. `git add frontend/src/lib/api/patient.ts` — commit the file to the branch
2. `frontend/src/lib/api/client.ts` — add singleton refresh promise guard

## Next Action

- Fix P1-1 + P1-2
- Re-run build + backend tests
- Auto-merge if fixes pass (no PTH approval required per rules)
