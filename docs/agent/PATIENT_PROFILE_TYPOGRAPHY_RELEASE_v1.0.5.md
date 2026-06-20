# Patient App — Profile Read Typography + DOB Format v1.0.5

> **Release:** v1.0.5 · **Target:** Azure Container Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #29 (`fix/patient-profile-read-typography`, merged squash `65ab690`).

## What changed

Read-view typography bump for older patients + DOB format. Patient-facing only; doctor/admin unchanged. **Frontend-only — no backend code or migration** (DB head stays `pauth_user_phone`).

- **Profile read-view** (`ProfileField`): label 15→16px medium (mint-700), value 17→21px semibold, larger gap/padding, mint divider. Empty `—` → "Chưa cập nhật" (italic muted).
- **DOB**: ISO `1975-10-22` → `22/10/1975` (DD/MM/YYYY) via `formatDateVN` — resolves the Phase-2 debt logged at v1.0.3.
- **Settings** account fields (phone/email/role): label 16px medium mint, value 21px semibold; empty email → "Chưa cập nhật".
- **Medication detail** `InfoRow`: label 10→16px, value 17→20px.
- **Page titles** (PageHeader h1 + greetings) scoped `.patient-app` → 26px.

## Quality gates (local)

- Frontend `tsc` / `lint` / `build` clean.
- Backend `pytest` **578 passed / 1 skipped** (unchanged).
- Playwright iPhone 14 Pro **5/5** measured: label 16px, value 21px, DOB "22/10/1975", page title 26px, empty "Chưa cập nhật".

## Deploy notes

- Deploy via the existing **"Azure Staging Deploy"** workflow (`workflow_dispatch`). No infra/workflow/config changes.
- DigitalOcean production is opt-in only (`[deploy-do]`) and is **not** touched.
- AI/OCR feature flags remain unset on staging (default OFF).

## Design debt

Phase-2 item "profile read-view DOB ISO" is now **RESOLVED**. Remaining minor: settings still surfaces an optional email row (non-blocking).
