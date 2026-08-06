# 12 — Pilot Operations Runbook (WS13)

**Date:** 2026-08-03 · **Scope:** controlled pilot, **10–50 initial users** on staging backend + standalone Android APK. **Synthetic-or-consented data only.** No production deploy.

## Participant eligibility
- Internal team + explicitly invited external testers who accept the pilot consent + clinical disclaimer.
- Android device on API ≥ 31 (pilot verified on API 34, arm64-v8a). iOS deferred (no signing).
- Vietnamese-language medical documents (OCR is tuned for VN prescription/lab/general reports).

## Consent & data policy
- **Synthetic-data mode (default):** testers use seeded email demo patients; no real PHI. Recommended for the first cohort.
- **Real-data mode (opt-in, gated):** only after a tester signs the pilot consent; cloud OCR stays OFF (local/mock only — no PHI leaves region); Meto uses confirmed-data-only.
- Consent categories are per-category, fail-closed, revocable in-app (`714a819`); revocation excludes data from AI/doctor-sharing on the next request.
- Account export + deletion available in-app (`d229c04`) — testers can self-erase at pilot end.

## Onboarding guide (tester-facing, summarized)
1. Install `app-release.apk` (`adb install -r`, or Play internal track once a key exists).
2. Log in with the **email** demo account provided (phone/OTP is deferred; app is email-login).
3. Journeys to exercise: (A) upload/photograph a document → review → confirm; (B) medication schedule → mark taken → adherence; (C) Meto chat (consent-aware); (D) doctor marketplace → book → mock-pay → consult.
4. Report bugs via the pilot bug form (below).

## Real-data / demo prerequisites (from ANDROID-PILOT-RC §4)
- Email-based demo patients (phone-based seed accounts cannot log into the app).
- J3 schedules with due doses (reminders journey).
- A **verified doctor** in the marketplace (admin-gated; "no admin seeding" guardrail → provision via the admin console, not a seed script).
- Meto provider readiness + granted per-category consent.

## Support & escalation
- **Support contact:** single pilot support channel (email/Telegram) staffed during pilot hours. Owner to name the address before cohort start.
- **Escalation:** bug → triage (SEV per `13-INCIDENT-RESPONSE.md`) → fix-or-workaround → notify tester.
- **Clinical disclaimer (must be shown at onboarding):** "MetoCare is a health-information tool, not a medical device. It does not diagnose, prescribe, or replace professional medical advice. In an emergency call local emergency services."
- **Known-limitations notice:** debug-signed build; no remote push (in-app reminders only); local OCR only; mock payments; MFA relaxed on staging.

## Bug-reporting process
- Fields: journey (A/B/C/D), device+OS, app build (versionName/Code), steps, expected vs actual, screenshot, timestamp (for log correlation via request/correlation IDs — WS5).
- No PHI in bug reports when in synthetic mode; in real-data mode, redact document contents.

## Account cleanup
- Per-tester: in-app account deletion (self-service) OR ops-run deletion job.
- End-of-pilot: purge synthetic cohort via the seed script's idempotent teardown + verify blob cleanup (WS3/WS8 integrity queries).

## Pilot KPIs (measured via WS6 analytics)
| KPI | Target (pilot) |
|---|---|
| Activation (install → onboarding complete → first login) | ≥ 80% |
| Successful document import (upload → confirm) | ≥ 70% |
| OCR correction rate | tracked (baseline; no hard gate in pilot) |
| Reminder engagement (delivered → acted) | ≥ 50% |
| Meto usage (sessions/active user) | tracked |
| Doctor booking (detail → book) | tracked |
| Crash-free sessions | ≥ 99% |
| Support requests / active user | tracked |
| **Safety incidents (clinical/privacy)** | **0 unresolved P0/P1** |

## Pilot exit criteria (→ beta readiness input)
- No open SEV-0/SEV-1 incidents.
- Crash-free ≥ 99%, activation ≥ 80%.
- OCR + AI quality baselines captured (WS6/WS7) with no safety regression.
- Support load sustainable; known limitations accepted by owner.

## Operator dashboard
Until a SaaS dashboard is wired (WS5), the operator view is the structured-log/metrics queryable baseline (correlation-ID joined) + a daily pilot report generated from analytics events (WS6). Provider-abstraction plan in `04-OBSERVABILITY.md`.
