# PX-02B — Patient Visual Consistency Report

> **Goal:** Bring every remaining patient-facing screen onto the MetoCare Soft UI
> ("Liquid Glass" mint) design language, so the entire patient experience is
> visually consistent — no blue admin-style components anywhere in patient routes.
> **Status:** ✅ Complete · type-check / lint / build green · 20 screens captured at 390×844.
> **Date:** 2026-06-19
> **Source of truth:** claude.ai/design — *MetoCare App Interface Design* → `MetoCare App.dc.html`.

---

## 1. Scope delivered

The 8 screens named in the brief, **plus** every other reachable patient route
(to satisfy "no blue admin-style components remaining in patient routes"):

| # | Screen | Route | Status |
|---|--------|-------|--------|
| 1 | Labs | `/labs` | ✅ converted |
| 2 | Nutrition | `/nutrition` | ✅ converted |
| 3 | Medications | `/medications` | ✅ converted |
| 4 | Care Plan | `/care-plan` | ✅ converted |
| 5 | Metrics List | `/metrics` | ✅ converted |
| 6 | Notifications | `/notifications` | ✅ converted |
| 7 | Profile | `/profile` | ✅ converted |
| 8 | Settings | `/settings` | ✅ converted |
| + | Medication detail | `/medications/[id]` | ✅ converted |
| + | Care-plan detail | `/care-plan/[id]` | ✅ converted |
| + | Consents | `/consents` | ✅ converted |
| + | Patient error boundary | `(patient)/error.tsx` | ✅ converted |
| + | Forgot password | `/forgot-password` | ✅ converted (was orphaned + blue) |

**Verification — zero blue design-system imports remain in patient routes:**

```
$ grep -rln "@/design-system" frontend/src/app/(patient)
(no matches)
```

Doctor (`/doctor/*`) and admin (`/admin/*`) portals were **not touched** — they
keep the blue design system, as required.

---

## 2. Design language applied

All patient screens now share one token set (defined in `globals.css` under the
`.patient-app` scope) and a small set of reusable primitives.

| Token | Value | Usage |
|-------|-------|-------|
| Mint brand | `#0F9C6E` / gradient `#1BB082 → #0B7F5B` | primary CTAs, FABs, nav center, hero |
| Text | `#0E2A33` (heading) · `#244744` (body) · `#365651` (muted) · `#566E66` (subtle) | typography |
| Glass surface | `rgba(255,255,255,.66)` + `blur(22px) saturate(180%)` + inset highlight | every card |
| Semantic | success `#15915A` · warning `#C77A06` · danger `#D92D20` · info `#2563EB` · AI `#6D3FBE` | status, provenance |
| Radius | cards `14–20px` · pills `999px` | rounding |
| Touch target | ≥ **44px** | all buttons/inputs/nav |
| Font | ≥ **16px** on inputs (no iOS zoom), 13–16px body | typography |

**Reusable primitives** (`src/components/patient/`):
`glass.tsx` (MetoMark, Sparkline, Ring, GlassCard) · `states.tsx`
(empty/error/offline/skeleton + AI-pending vs doctor-approved provenance badges) ·
`header.tsx` (sub-screen header) · `modal.tsx` (Radix-based glass bottom-sheet) ·
`tabs.tsx` (segmented control) · `forms.tsx` (`Field`, `GlassField`, `InlineAlert`,
`MintFab`, `MINT_GRADIENT`).

Spacing, shadows, typography and CTA hierarchy are identical across screens because
they all flow through these primitives.

---

## 3. Per-screen result

Screenshots (390×844, 2×) in [`docs/px02b_screenshots/`](./px02b_screenshots/).

| Screen | Shot | Key Soft-UI elements |
|--------|------|----------------------|
| Dashboard | `01-dashboard.png` | mint hero, "Hôm nay cần làm gì?" actions, sparkline tiles, doctor note |
| Metrics (overview) | `02-metrics-overview.png` | segmented tabs, glass latest-value, row list |
| Metrics (detail) | `03-metrics-detail.png` | sparkline trend, status pills |
| Metrics (log) | `04-metrics-log.png` | glass form, mint CTA |
| AI Coach | `05-ai-coach.png` | mint user bubble, glass AI bubble w/ purple provenance border + "AI tạo · chờ bác sĩ duyệt" |
| Medications | `06-medications.png` | glass med cards, status pill, refill/detail CTAs |
| Medication detail | `07-medication-detail.png` | glass info rows |
| Care Plan | `08-care-plan.png` | status pill, approved indicator, AI-assist tag |
| Care Plan detail | `09-care-plan-detail.png` | pending-review banner, content card |
| Labs | `10-labs.png` | **AI explanation (purple) vs doctor-approved (mint)** provenance split |
| Nutrition | `11-nutrition.png` | mint calorie hero, grouped log, purple AI coaching tip |
| Notifications | `12-notifications.png` | segmented tabs, glass list, unread dots, mint type icons |
| Profile | `13-profile.png` | identity header, health card, account hub |
| Settings | `14-settings.png` | sectioned glass, mint toggles |
| Consents | `15-consents.png` | glass rows, revoke (glass modal confirm) |
| Onboarding | `16-onboarding.png` | progress, segmented gender, glass inputs |
| Welcome | `17-welcome.png` | full-mint intro carousel |
| Login | `18-login.png` | phone-first, "Quên mật khẩu?" restored |
| Register | `19-register.png` | phone-first glass |
| Forgot password | `20-forgot-password.png` | now glass (was orphaned + blue) |

Empty / error / offline states are rendered via the shared `states.tsx`
surfaces, so they are consistent on every screen.

---

## 4. Validation

| Check | Command | Result |
|-------|---------|--------|
| Type-check | `npm run type-check` | ✅ pass (0 errors) |
| Lint | `npm run lint` | ✅ no new warnings (only pre-existing design-system warnings) |
| Build | `npm run build` | ✅ compiled, 37/37 static pages |
| Browser (390×844) | Chrome headless via Playwright harness | ✅ 20/20 screens captured |

> The screenshot harness mocks the API at the network layer (real components,
> representative data) and drives the production build of the real app — it does
> not stub or fake any component.

---

## 5. Code review (high-recall, 8-angle) — findings & resolutions

| # | Finding | Severity | Resolution |
|---|---------|----------|-----------|
| 1 | "Quên mật khẩu?" link dropped from login → `/forgot-password` orphaned & still blue | regression | **Fixed** — link restored on login; forgot-password restyled to glass (phone-first) |
| 2 | Medications had no persistent nav entry (only via dashboard tile) | UX gap | **Fixed** — added "Thuốc & Điều trị" to the profile account hub |
| 3 | `GlassField` duplicated in login + register | dup | **Fixed** — extracted to `forms.tsx` |
| 4 | `Field` helper duplicated in 6 files | dup | **Fixed** — single shared `Field` |
| 5 | Inline error banners w/ inconsistent `role="alert"` | a11y | **Fixed** — shared `InlineAlert` (always `role="alert"`) |
| 6 | Mint-gradient FAB re-authored in 3 headers | dup | **Fixed** — shared `MintFab` + `MINT_GRADIENT` |
| 7 | Login/register `if(user)` redirect races onboarding-aware routing | minor | Accepted — the `(patient)` layout gate guarantees the correct final destination; only a redirect hop, no wrong end-state |
| 8 | Medications "completed" tab always empty / status not filtered | pre-existing | Unchanged — faithful port of prior behavior; backend has **no** medication status field (no backend changes in scope) |
| 9 | Metrics `limit:100` unfiltered fetch, client-side filter | pre-existing | Unchanged — identical to prior behavior; out of scope (no backend changes) |
| 10 | Dashboard pending-labs alert removed | intentional | By design — the approved design replaces it; lab updates still surface in Notifications |

All confirmed regressions (1–6) were fixed and re-verified by screenshot.

---

## 6. Constraints honored

- ✅ Same mint/liquid-glass visual system across all patient screens.
- ✅ Same spacing, shadows, typography, CTA hierarchy (via shared primitives).
- ✅ No blue admin-style components remaining in patient routes (grep-verified).
- ✅ Existing functionality preserved (forms, API calls, validation, modals, mark-read, revoke, search-param sync, history cap, logout).
- ✅ No backend changes.
- ✅ No doctor/admin UI changes.

---

## 7. External Codex review (review-only, no commit)

Ran `codex review --uncommitted` (codex-cli 0.137.0) — three passes.

| Pass | Result |
|------|--------|
| 1 | **P0** found: placeholder email domain `phone.metocare.local` is rejected by the backend's Pydantic `EmailStr` (`.local` is a reserved/special-use TLD) → every phone register/login would 422. Codex verified by running pydantic. |
| 2 (after fix) | **0 P0 / 0 P1.** P2: staff email keyboard, AI-retry preserves question, synthetic email shown in profile/settings. |
| 3 (after P2 fixes) | **0 P0 / 0 P1.** P2: `+84 (0)` normalization, onboarding re-check after profile edit, bottom-nav active state on non-tab routes. |

**Resolutions:**
- **P0 (domain)** → `PHONE_EMAIL_DOMAIN = 'phone.metocare.vn'` (subdomain of org domain; passes `EmailStr`, verified against the backend's email-validator). No backend change.
- Phone shown instead of synthetic email in Profile/Settings (`displayContact` / `phoneFromPlaceholderEmail`).
- AI assistant keeps the question through the request (loading bubble + retry); cleared only on success.
- Staff can enter an email identifier on the shared login (`type=text`).
- `normalizeVietnamPhone` handles `+84`, `+84 (0)`, and local `08x` numbers (unit-checked).
- Profile save re-enforces the onboarding invariant if a required field is cleared.
- Bottom nav highlights no tab on routes outside the 5 nav items.

**Gate: 0 P0 / 0 P1 across two consecutive runs.** Remaining items are P2/P3 (addressed
or accepted). Re-validated after every change: type-check / lint / build green.

> Codex ran in **review-only** mode (`codex review`) — it does not commit or modify files.

---

## 8. Merge recommendation

**Recommend: merge** `feature/px02-patient-liquid-glass` after the DEV smoke passes.

- Branch: `feature/px02-patient-liquid-glass` (committed locally; **PR intentionally
  not opened** per instruction).
- Risk: low-to-moderate — large but UI-only; **no backend changes**; doctor/admin
  untouched; gated behind a feature branch.
- Blocking pre-merge check: the real-DEV browser smoke (§9).

---

## 9. Pending steps (require your environment — not runnable from here)

- **Deploy to DEV** (`172.20.0.100:13000`) — the local Docker daemon is down and DEV
  is your infra. A full **local production build + server** was run (used to capture
  every screenshot above), which is the deploy-equivalent verification I can do here.
  Run `docker compose -f docker-compose.internal.yml up --build` (or your DEV CI) to
  publish.
- **External Codex review** — the in-repo 8-angle review above is complete; if you
  also run the external Codex pass per your `docs/CODEX_REVIEW_*` convention, attach
  it here.
- **PR** — intentionally **not opened** per instructions ("Do not open PR before the
  entire patient experience is visually consistent"). The branch is ready when you are.
