# Patient Typography (50+) + Onboarding Redundancy Fix — v1.0.3

> **Release:** v1.0.3 · **Target:** Azure Container Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #25 (`fix/patient-typography-onboarding-redundancy`, merged squash `81ac7d5`).

## What changed

UX fixes from live-staging feedback (iPhone, 50+ patients). Patient-facing only; doctor/admin unchanged (scoped via `.patient-app`). **Frontend-only — no backend code or migration** (DB head stays `pauth_user_phone`).

1. **Typography (50+ readability, mobile-first)** — scoped CSS under `.patient-app`: inputs/textarea/select min-height 52px + 17px value/placeholder; labels 16px; CTA buttons 16px (bottom-nav excluded). Token bump across patient/auth/onboarding: meta 14px, body 16px, page/section titles 20px. Bottom-nav labels 11px. Doctor/admin (no `.patient-app` wrapper) untouched.
2. **Onboarding redundancy** — removed the duplicate "Số điện thoại" field (phone captured at registration; PATCH no longer sends phone); full name pre-filled from profile → registered account name.
3. **DOB format** — native `type=date` (iOS long "ngày 22 thg 10, 1975") → masked `DD/MM/YYYY` text input + ISO conversion + validation + hint.

## Quality gates (local)

- Frontend `tsc` / `lint` / `build` clean.
- Backend `pytest` **578 passed / 1 skipped** (unchanged).
- Playwright iPhone 14 Pro **15/15**: onboarding 0 phone fields, name prefilled, register no email, phone register→onboarding, phone login→dashboard.

## Deploy notes

- Deploy via the existing **"Azure Staging Deploy"** workflow (`workflow_dispatch`). No infra/workflow/config changes.
- DigitalOcean production is opt-in only (`[deploy-do]`) and is **not** touched.
- AI/OCR feature flags remain unset on staging (default OFF).

## Carried design debt (Phase 2)

Unchanged from v1.0.2 (with-data healthcare components mint, empty-state seed-data audit, profile/care-plan altitude, settings email-row, deeper primitive adoption) + profile read-view DOB still ISO (onboarding date fixed; profile follow-up).
