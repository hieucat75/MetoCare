# Patient App — Claude Design Liquid Glass foundation v1.3.0

> **Release:** v1.3.0 (minor bump — design-system foundation pass) · **Target:** Azure Container
> Apps staging (Singapore) · DigitalOcean production untouched.
> **Source PR:** #43 (`feat/patient-claude-design-handoff`, squash-merged into `main`).

## What ships

The patient app adopts the **Claude Design "MetoCare App" (Liquid Glass)** handoff as its design
foundation. This release is **tokens + fonts + ambient + navigation styling only** — no per-screen
rebuilds (those are deferred, see below).

- **Design tokens** (`tailwind.config.ts`): patient `mint` scale realigned to the handoff hues —
  primary `#0F9C6E`, glass gradient top `#1BB082` → bottom `#0B7F5B`. New **`ai` purple `#6D3FBE`**
  token added for future AI-generated-content provenance ("AI tạo · chờ bác sĩ duyệt").
- **Typography**: **Be Vietnam Pro** + **JetBrains Mono** added alongside Inter (handoff font stack).
- **Ambient** (`globals.css`): richer mint/blue/amber Liquid Glass background ("chiều sâu phân lớp");
  patient body text `#0E2A33`.
- **Bottom navigation** (`PatientBottomNav`): Liquid Glass **floating frosted pill bar + mint active
  accent**. **The original 5-tab IA is unchanged** (Tổng quan · Chỉ số · Xét nghiệm · Thuốc · Hồ sơ) —
  no center AI FAB, Labs/Medications retained. Glass *styling* from the handoff; *IA* per product decision.
- Mobile content padding `pb-24` to clear the floating bar.

## Scope boundary — patient-scoped, additive

- All changes are scoped to `mint` / `.patient-app`. **Doctor & admin portals (primary blue) are
  untouched.**
- The `ai` token ships unused (no AI-provenance UI yet); the AI-assistant route/tab stays out of MVP
  scope (AI feature flag OFF).

## Frontend-only — no backend / migration / workflow

- **No backend change**, **no DB migration** (DB head stays `hmbk_backfill`), **no workflow/config
  change**, no new runtime deps → fast frontend-only build.
- DigitalOcean production is `[deploy-do]`-opt-in and untouched.

## Deferred — per-screen rebuilds (next pass)

The pixel-level screen redesigns (dashboard hero mint-summary card, AI-assistant chat with purple
provenance pills + doctor-approved shield, care-plan progress ring/checklist) were built but are
**held back from this release** and preserved on branch `feat/patient-screens-liquid-glass-pass2`
for a separate follow-up pass.

## Quality gates (local)

- Frontend `tsc --noEmit` / `eslint` / `next build` clean (all routes compiled).
- Backend untouched — **pytest baseline green (exit 0)**.
- Live local Playwright iPhone 14 Pro: `/login` renders mint `#0F9C6E` primary + Be Vietnam Pro;
  patient routes show the floating glass 5-tab nav + mint ambient.

## Changed files

- `frontend/tailwind.config.ts` — mint hues + `ai` token + Be Vietnam Pro.
- `frontend/src/app/globals.css` — font import + patient text + Liquid Glass ambient.
- `frontend/src/components/nav/PatientBottomNav.tsx` — floating glass 5-tab bar.
- `frontend/src/app/(patient)/layout.tsx` — content padding for the floating bar.
- `frontend/src/app/(patient)/settings/page.tsx` — version string → v1.3.0.
