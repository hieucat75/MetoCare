# Patient App — Claude Design Compliance (mint/liquid-glass) v1.0.2

> **Release:** v1.0.2 · **Target:** Azure Container Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #23 (`fix/patient-ui-claude-design-compliance`, merged squash `12f9443`).

## What changed

UI/UX compliance pass on top of v1.0.1: the **patient-facing app** moved from the blue `primary` medical-SaaS theme to **mint / soft-green liquid-glass** (MetoCare Soft UI), mobile-first (iPhone 14 Pro). **Doctor/admin portals are unchanged (still blue — no regression).** Phone-based patient registration preserved.

- **Tailwind:** additive `mint` palette + `glass`/`focus-mint` shadows (`primary` untouched).
- **Shared components — additive variants/props only:** Button `mint`/`mint-soft` · Badge `mint` · Card `glass` · Alert `mint` · Switch `tone="mint"` · Tabs `tone="mint"`.
- **New patient primitives** (`src/components/patient/`): GlassCard, MintButton, PatientInput, MetricCard, SectionHeader, PatientEmptyState.
- **Shell + 9 routes + onboarding:** mint gradient shell, glass app bar, glass mint bottom nav; tokens → mint; cards → glass; info alerts → mint; empty CTAs → mint.

**No backend code or migration in this release** — frontend-only. DB migration head remains `pauth_user_phone`.

## Quality gates (local)

- Frontend `tsc` / `lint` / `build` clean.
- Backend `pytest` **578 passed / 1 skipped** (unchanged).
- Playwright iPhone 14 Pro: 13 screens captured + auth smoke (phone register 201 / login 200 / invalid 422).
- Regression: `test_admin_email_login_still_works` PASS; doctor/admin dashboards screenshotted = blue (unchanged).
- Visual review: avg 8.1/10 across 9 screens (PTH "tạm chấp nhận").

## Deploy notes

- Deploy via the existing **"Azure Staging Deploy"** workflow (`workflow_dispatch`). No infra/workflow/config changes.
- DigitalOcean production is opt-in only (`[deploy-do]`) and is **not** touched.
- AI/OCR feature flags remain unset on staging (default OFF) — unchanged.

## Accepted design debt (Phase 2 follow-up)

1. With-data healthcare components (PatientMetricCard / RiskLevelBadge / MedicationCard) not fully mint — blue focus-rings / some `primary` internals; only empty states verified.
2. Empty-state bias — package captured with no data; seed data + re-audit filled states (charts, tiles, med list, score).
3. Profile / Care-plan altitude — flat field lists + barren empty states; group into glass sections + warmer empty states.
4. Phone-first inconsistency — Settings still surfaces optional "Email — Chưa có" row.
5. Shallow primitive adoption — mint applied via token-swap + shared variants; new primitives under-used inside routes.
