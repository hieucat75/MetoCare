# Patient App — Liquid Glass + Stat Typography v1.0.4

> **Release:** v1.0.4 · **Target:** Azure Container Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #27 (`fix/patient-liquid-glass-deep-adoption`, merged squash `ddc6e21`).

## What changed

Deep visual rework of the patient app + stat readability. Patient-facing only; doctor/admin unchanged (scoped `.patient-app` + components used only by patient). **Frontend-only — no backend code or migration** (DB head stays `pauth_user_phone`).

### Liquid Glass / Soft UI
- Always-visible ambient mint radial gradient under `.patient-app` so translucent cards refract (no more flat white).
- Glass cards: `bg-white/85` + backdrop-blur + white border + mint ring + neutral lift shadow + inner highlight, `rounded-3xl` (PatientMetricCard included).
- Pillow buttons (mint gradient + pillow shadow + inner highlight + active-scale), frosted bottom nav + header, glass inputs, mint-glow empty-state icon discs (all `<EmptyState>` → `<PatientEmptyState>`).
- Tailwind shadows: glass / pillow-mint / frost-up / glow-mint / inset-mint.

### Larger stat typography (50+ readability)
- Metric values prominent: PatientMetricCard compact **36px** / full **42px**, MetricCard primitive **40px**, dashboard metabolic score **40px** bold; units 18–22px, labels 16–18px.
- App-wide bump: body 17px, meta 15px, card titles 18px, page/section/empty titles 24px, inputs **18px / 56px**, labels 17px, CTA buttons 17px, bottom-nav labels 13px.

## Quality gates (local)

- Frontend `tsc` / `lint` / `build` clean.
- Backend `pytest` **578 passed / 1 skipped** (unchanged).
- Playwright iPhone 14 Pro **15/15**: metric values 36–40px, input 18px/56px, no horizontal overflow, onboarding no-phone + name-prefill, register no-email; doctor/admin = blue/flat (unchanged).

## Deploy notes

- Deploy via the existing **"Azure Staging Deploy"** workflow (`workflow_dispatch`). No infra/workflow/config changes.
- DigitalOcean production is opt-in only (`[deploy-do]`) and is **not** touched.
- AI/OCR feature flags remain unset on staging (default OFF).

## Design debt — RESOLVED

The 5 Phase-2 UI debt items previously "tạm chấp nhận" (v1.0.2) are now addressed by this deep adoption: with-data components mint+glass (PatientMetricCard), filled metric states verified with seeded data, profile/empty-state altitude via glass + glow + bigger type, primitive adoption deepened. (Remaining: profile read-view DOB still ISO; settings optional email row — minor, non-blocking.)
