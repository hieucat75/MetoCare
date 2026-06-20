# Patient Auth — Phone Registration + Soft Mint UI (v1.0.1)

> **Release:** v1.0.1 · **Target:** Azure Container Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #21 (`fix/patient-auth-phone-design`, merged squash `5cafdf0`).

## What changed

P0 UI/Auth correction on top of the completed Patient App MVP (v1.0.0):

1. **Patient registration: email → VN phone number.** Full name + phone + password (no email). VN mobile validated + normalized to canonical `+84…` (E.164). Admin/doctor still authenticate by **email — no regression**.
2. **Patient auth screens → Claude Design** (mint / soft-green / liquid-glass), mobile-first: `/register`, `/login`, `/forgot-password` (Phase-2 stub).

## Backend contract

- `User`: `phone` (unique, nullable, `+84`) added; `email` relaxed to nullable (exactly one of email/phone per row).
- `register` accepts phone (422 invalid / 409 duplicate-after-normalize) or email (compat); `login` accepts `{phone}` or `{email}`. `UserOut` exposes `phone`; `email` nullable.
- Migration **`pauth_user_phone`** (head): `users.phone` unique index + `users.email` → nullable. Additive/safe on existing rows.

## Quality gates (local)

- Backend `pytest` **578 passed / 1 skipped** (+23 vs 555/1); `ruff` clean.
- Frontend `tsc` / `lint` / `build` clean.
- Playwright local **6/6**; live API: admin email login 200, phone login (normalized) 200, invalid phone 422.

## Deploy notes

- Deploy via the existing **"Azure Staging Deploy"** workflow (`workflow_dispatch`). No infra/workflow/config changes.
- DigitalOcean production is opt-in only (`[deploy-do]`) and is **not** touched.
- Keep AI/OCR feature flags unset on staging (default OFF) — unchanged by this release.
