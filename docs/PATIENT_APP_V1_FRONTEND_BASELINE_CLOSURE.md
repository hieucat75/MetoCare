# Patient App V1 — Frontend Baseline Closure

**Date:** 2026-06-24  
**Closed by:** Claude Code (claude-sonnet-4-6)  
**Status:** CLOSED — BASELINE LOCKED

---

## Audit Final Count

Independent re-audit completed 2026-06-24. Methodology: file-by-file inspection of every patient/auth/onboarding route. Classifications assigned from zero — no inheritance from prior sessions.

| Status | Count | Notes |
|--------|-------|-------|
| **IMPLEMENTED** | **45** | All routes exist, Soft-UI Neu skin, real API wired, proper state patterns |
| **DEFERRED** | **1** | B2-05 /forgot-password — Phase 2 SMS/OTP stub (see below) |
| **NATIVE_ONLY** | **1** | B1-01 /start — intentional plain HTML/Tailwind, no library |
| **BLOCKED** | **0** | — |
| **NOT_STARTED** | **0** | — |

**Total canonical screens audited:** 47 (57 inventory items; B5/B6 are the same 2 files; B3/B4 sub-blocks counted within their pages)

---

## Deferred Item

**B2-05 /forgot-password**  
File: `frontend/src/app/(auth)/forgot-password/page.tsx`

- Backend SMS/OTP password reset endpoint does not exist (Phase 2 work)
- Screen renders cleanly; user sees a green info banner on load: *"Tính năng đặt lại mật khẩu đang được phát triển (Phase 2). Vui lòng liên hệ hỗ trợ nếu cần."*
- On submit, user sees: *"Tính năng sắp ra mắt — Đặt lại mật khẩu qua SMS sẽ có trong phiên bản tiếp theo."*
- No broken UI, no error thrown, no fake success
- Reclassified from PARTIAL → DEFERRED (intentional documented stub, not a regression)
- Resolution: wire `handleSubmit` to backend OTP endpoint when Phase 2 ships

---

## Validation Results

| Check | Result | Detail |
|-------|--------|--------|
| `tsc --noEmit` | **PASS** | 0 errors |
| ESLint | **PASS** | 0 errors; warnings in legacy `@/design-system` files only (not patient routes) |
| `next build` | **PASS** | 42/42 pages compiled, 0 TypeScript errors |
| Route smoke (14 routes) | **PASS** | All return HTTP 200: `/` `/intro` `/login` `/start` `/dashboard` `/metrics` `/labs` `/profile` `/settings` `/notifications` `/medications` `/nutrition` `/report` `/onboarding` |
| Core patient journey | **PASS** | Auth guard confirmed (unauthenticated → login redirect); all patient routes serve 200 |

---

## Design System Status

All `@/design-system` imports removed from every patient/auth/onboarding screen.  
Remaining `@/design-system` usage is in: `(patient)/layout.tsx` (shell/nav — out of scope), `admin/` routes (out of scope), and the `design-system/` source itself.

**Soft-UI Neu component usage (patient routes):**
- `NeuCard`, `NeuButton`, `NeuBadge`, `NeuIconButton` from `@/components/patient/neu`
- `PatientSkeleton`, `PatientErrorState`, `PatientEmptyState`, `AiPendingBadge` from `@/components/patient/states`
- `GlassModal` from `@/components/patient/modal`
- Inline `role="alert"` divs for transient notifications (yellow/green/red/blue)

---

## P0 Post-Mortem — auth/register "Không thể kết nối máy chủ"

**Date:** 2026-06-24  
**Severity:** P0 — registration completely broken on staging  
**Status:** FIXED + guarded

### Root Cause

Manual Docker builds during this session passed `--build-arg NEXT_PUBLIC_API_URL=https://api.metocare.com`. That domain does not exist (DNS NXDOMAIN). `client.ts:1` uses `process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'` — since the env var was set (non-empty) but to a dead hostname, the fallback never triggered. Every fetch from the browser failed at the network layer before reaching the backend, producing the "Không thể kết nối máy chủ" error.

The backend was healthy throughout (`POST /api/v1/auth/register` → 201 when curled directly). No code, schema, or infrastructure change was needed.

### Fix

Rebuilt image with correct arg:
```
NEXT_PUBLIC_API_URL=https://ca-metocare-backend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io/api/v1
```
Deployed as revision `ca-metocare-frontend--fe-99bb2274-fix`.

**No source files were changed.** Fix was build-argument only.

### Verification

- JS chunk `7756-d054e54277674906.js` confirmed correct URL, 0 occurrences of `api.metocare.com`
- `POST /api/v1/auth/register` → **201**, valid JWT returned
- `GET /api/v1/auth/me` → **200**
- `GET /onboarding?_rsc` → **200** (new patient redirected correctly)
- Screenshots: `docs/agent/v1_closure_shots/p0_fix_register_success.png`, `p0_fix_onboarding_redirect.png`

### Prevention Guard

`.github/workflows/frontend-staging.yml` now contains two new steps between "Record current state" and "Build & push":

**Step: Validate API URL before build**
- Fails if `BACKEND_FQDN` is empty or resolves to `https:///api/v1`
- Fails if URL contains `api.metocare.com` (dead placeholder)
- Fails if URL contains `localhost`
- Fails if URL does not end with `/api/v1`
- Fails if `GET https://{BACKEND_FQDN}/health` does not return HTTP 200

**Step: Post-build bundle URL audit** (runs after image push, before ACA deploy)
- Pulls the built image, extracts `/app/.next/static/chunks/`
- Fails if `api.metocare.com` appears in any JS chunk
- Fails if `localhost:8000` appears in any JS chunk
- Fails if the correct ACA backend FQDN does NOT appear in any JS chunk

These guards would have caught the P0 before the image reached ACA. The workflow already derived `BACKEND_FQDN` from Azure at runtime (so the value is always live) — the validation makes that derivation auditable and non-bypassable.

---

## Staging Deployment

| Field | Value |
|-------|-------|
| **V1 Baseline revision** | `ca-metocare-frontend--fe-c18cf7e6` |
| **V1 Baseline SHA** | `c18cf7e62a8c6c68cbc23fb8720c350d6cf4a8ec` |
| **P0 fix revision** | `ca-metocare-frontend--fe-99bb2274-fix` |
| **P0 fix image** | `ghcr.io/hieucat75/metocare-frontend:99bb227451255174d163a19c77cf943ecdb9811e-fix` |
| **Container App** | `ca-metocare-frontend` |
| **Resource Group** | `rg-metocare-staging` |
| **Region** | Southeast Asia |
| **Traffic** | 100% |

**Rollback command:**
```bash
az containerapp update \
  --name ca-metocare-frontend \
  --resource-group rg-metocare-staging \
  --image ghcr.io/hieucat75/metocare-frontend:83ce7d346734ed4bd05f6ad51103d3b974cb8bfa \
  --revision-suffix fe-rollback
```
*(Previous stable revision: `fe-83ce7d34`, SHA `83ce7d346734ed4bd05f6ad51103d3b974cb8bfa`)*

---

## Screenshots

### New shots — this session (`docs/agent/v1_closure_shots/`)

| File | Route | Notes |
|------|-------|-------|
| `00_start.png` | /start | Landing splash |
| `01_intro.png` | /intro | Onboarding carousel step 1 |
| `02_login.png` | /login | Auth form with Soft-UI skin |
| `03_onboarding_auth_guard.png` | /onboarding | Auth guard redirect confirmed |
| `04_forgot_password_deferred.png` | /forgot-password | DEFERRED banner visible |

### Authenticated patient routes (`docs/agent/softui_shots/`)

| File | Screen |
|------|--------|
| `03-dashboard.png` | Dashboard — HealthScore + PriorityEngine + Metrics grid |
| `04-metrics-list.png` | Metrics — KPI category cards |
| `05-metric-detail.png` | Metrics — [metricType] detail + chart |
| `06-labs.png` | Labs — list |
| `07-lab-upload.png` | Labs — OCR upload |
| `08-medications.png` | Medications — list |
| `09-profile.png` | Profile — read view |
| `10-notifications.png` | Notifications |
| `11-settings.png` | Settings |
| `12-ai-assistant.png` | AI Assistant — feature-flagged state |

### Additional routes (`docs/agent/partial_fix_shots/`)

| File | Screen |
|------|--------|
| `07_metrics_log.png` | Metrics — /metrics/log form |
| `08_metrics_log_glucose.png` | Metrics — /metrics/log/[type] glucose |
| `09_onboarding.png` | Onboarding — step 1 personal info (authenticated) |
| `10_care_plan.png` | Care plan — list |

---

## Scope Boundary

**No further UI redesign is in scope before pilot.**

The following are explicitly out of scope until pilot is complete:

- Epic B (new screens beyond V1 inventory)
- Epic C, Epic D
- Native mobile app (`mobile/`)
- New design batches
- Backend Phase 2 (SMS/OTP, medication adherence API, AI coach endpoints)
- Any UI change not required to fix a P0 or P1 regression

The baseline is locked at SHA `c18cf7e62a8c6c68cbc23fb8720c350d6cf4a8ec`.

---

## Screens In Scope for Pilot (45 IMPLEMENTED)

B1: /start · /login · /register · /unauthorized  
B2: /intro · /onboarding (3 steps)  
B3: /dashboard (all 5 blocks)  
B4: /metrics · /metrics/[metricType] · /metrics/log · /metrics/log/[type]  
B5/B6: /care-plan · /care-plan/[id]  
B7: /profile (read + edit)  
B8: /labs · /labs/upload  
B9: /ai-assistant · /notifications · /report · /consents · /settings · /medications · /medications/[id] · /nutrition
