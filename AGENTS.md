<claude-mem-context>
# Memory Context

# [Metocare] recent context, 2026-06-19 6:39pm GMT+7

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 3 obs (606t read) | 8,565t work | 93% savings

### Jun 19, 2026
1026 1:11p 🔵 Code Review Initiated Against Main Branch
1027 1:47p 🔵 Code Review Against Main Branch Initiated
1028 2:35p 🔵 Code Review Initiated for Commit c22e7a7

Access 9k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>

---

# Patient Mobile App (PX-02 — Liquid Glass redesign)

The patient-facing experience is a **mobile-first app** (no admin sidebar at any
width), styled in the "Liquid Glass" mint design. Doctor/admin portals keep the
blue design system. Source of truth for the design: the claude.ai/design project
**"MetoCare App Interface Design"** → file `MetoCare App.dc.html`
(project id `832ed376-4d79-4fd7-8560-afd04569e284`), imported via the
`claude_design` MCP connector (`/design-login` grants `user:design:read/write`).

## Theme & primitives
- Mint theme is scoped under the `.patient-app` CSS class + glass utilities
  (`.mc-glass`, `.mc-hero`, `.mc-btn`, `.mc-btn-glass`, `.mc-input`) in
  `src/app/globals.css`. Touch targets ≥ 44px, body/input font ≥ 16px.
- Reusable glass primitives: `src/components/patient/glass.tsx` (MetoMark logo,
  Sparkline, Ring, GlassCard), `states.tsx` (empty/error/offline/AI-pending +
  provenance badges), `header.tsx` (sub-screen header).
- Floating glass bottom nav (5 tabs, center AI): `components/nav/PatientBottomNav.tsx`.

## Pilot V1 auth — PHONE + PASSWORD only
**No OTP, no email-first registration, no passwordless, no Zalo/biometric.**
The backend `/auth/register` and `/auth/login` still require an `email`
(EmailStr) field and were **not** changed. The frontend derives a deterministic
placeholder email from the normalized phone number:

```
0901234567  ->  0901234567@phone.metocare.vn
```

The domain MUST pass the backend's Pydantic `EmailStr` validation — reserved /
special-use TLDs (`.local`, `.localhost`, `.invalid`, `.test`) are rejected by
email-validator and would 422 every register/login, so we use a subdomain of the
org domain `metocare.vn` (deliverability is disabled in EmailStr, so no DNS
lookup occurs). Profile/Settings display the real phone via
`displayContact()` / `phoneFromPlaceholderEmail()` rather than the synthetic email.

Helpers live in `src/lib/api/auth.ts`: `normalizeVietnamPhone`,
`phoneToPlaceholderEmail`, `identifierToEmail` (email if it contains `@`, else
phone — so staff can still log in with their real email), `registerWithPhone`,
`loginWithIdentifier`. The real phone is also stored on the `PatientProfile`
during onboarding (and is reconstructed from the placeholder email if missing).

## Flow
`/welcome` (intro carousel) → `/register` or `/login` (phone) →
`/onboarding` (2-step profile wizard, gated before dashboard) → `/dashboard`
("Hôm nay cần làm gì?"). The `(patient)` layout redirects incomplete profiles to
`/onboarding` (completeness = gender + dob + height_cm + weight_kg, see
`src/lib/patient/onboarding.ts`).