# MetoCare — Android Internal-Pilot RC Package

**Date:** 2026-08-03 · **Branch:** `feat/patient-platform-journey2` · Engineering scope FROZEN (DIST-RC engineering complete).

This is the internal-pilot readiness package: artifact, accounts, data, runbook,
rollback, evidence, and the specific dependencies that gate the remaining pilot tasks.

---

## 1. Install artifact
- **Standalone APK** (JS bundled, no Metro needed): `mobile/android/app/build/outputs/apk/release/app-release.apk` — built via `cd mobile/android && ./gradlew :app:assembleRelease`.
- **Signing:** debug keystore fallback (`app/build.gradle` release→`signingConfigs.debug`). Fine for **internal pilot**; a real upload/Play key is a DIST dependency (Google signing deferred).
- **Package id:** `me.metocare.patient`. Install: `adb install -r app-release.apk`.
- ⚠️ **Build-time config:** the APK bakes in `API_BASE_URL` (mobile `src/config/env.ts`, default `http://localhost:8000/api/v1`). For a **remote** pilot, rebuild with `API_BASE_URL=<staging https URL>` so testers' devices reach the backend over the internet. The current artifact points at localhost (usable only with `adb reverse` on the dev host).

## 2. Staging URL
- Backend: Azure Container Apps staging (see `.github/workflows/azure-staging.yml`). Confirm the live FQDN from the latest staging deploy; set it as `API_BASE_URL` for the remote pilot build.
- Local QA backend (this session): `http://localhost:8000` (healthy), bridged to the emulator via `adb reverse tcp:8000 tcp:8000`.

## 3. Test accounts (VERIFIED)
- **Patient (email login — works with the app):** `pilot.patient@example.com` / `Pilot1234` — created + login-verified against the backend (register 201, login 200, role=patient, no MFA locally).
- ⚠️ **Pilot finding (fixed via account model):** the mobile app logs in with **email only** (`mobile/src/api/auth.ts`; phone/OTP deferred). The existing `backend/scripts/seed_demo_pilot.py` creates **phone-based** patients, which **cannot** log into the app. → Pilot demo accounts must be **email-based** (as above). This is a data/config change, not product scope.
- Password policy (§C) is active: pilot passwords need ≥8 chars incl. a letter + digit.

## 4. Demo data
- `backend/scripts/seed_demo_pilot.py` — 10 synthetic patients + metrics/labs/meds/adherence (idempotent, production-guarded, no PHI). **Caveat:** phone-based (see §3) and predates the J3 `MedicationSchedule`/`DoseOccurrence` model + the marketplace verified-doctor + Meto per-category-consent data, so it does not by itself satisfy all four journeys.
- **Journey prerequisites still needed for full demo:** (a) email demo patients; (b) J3 schedules with due doses (reminders journey); (c) a **verified doctor** in the marketplace (consultation journey) — note the project guardrail "do not seed admin accounts"; doctor provisioning is admin-gated; (d) Meto provider readiness + granted per-category consent (Meto journey).

## 5. Native-flow evidence (this session)
- `evidence/native-j2j5/` — app boots on-device to the login screen (`06-app-final.png`); the D-1 native-module crash (`expo-image-picker`) was found and fixed (rebuilt dev client); `FINDINGS.md` has details.
- **Four full-journey videos: NOT captured this session.** Reliable on-device capture is blocked by two specific dependencies (see §7).

## 6. Crash / log evidence
- D-1 (fixed): `Cannot find native module 'ExponentImagePicker'` → resolved by dev-client rebuild; post-fix `adb logcat` clean of native-module errors.
- No crashes on boot/login in the rebuilt build.

## 7. Blockers for the remaining pilot tasks (full 4-journey videos)
1. **UI-automation harness** — no Maestro/Appium present; raw `adb input text` mangles email/@ entry (evidence `07-login-filled.png` shows a corrupted email). Reliable multi-step journey capture needs Maestro (or manual QA on a real device). *Tooling dependency.*
2. **Emulator stability** — the Pixel_6_API_36 emulator ANRs under load (SwiftShader flakiness, documented) after long native builds, unreliable for long multi-journey runs. *Environment dependency.*
3. **Demo-data prerequisites** — verified-doctor seeding hits the "no admin seeding" guardrail; J3 due-dose + Meto-consent demo data need setup (§4). *Data/guardrail dependency.*

## 8. Credential gaps
See `CREDENTIAL-READINESS-MATRIX.md`. None blocks the Android *internal* pilot except: a reachable staging `API_BASE_URL` (§1) and, for wide distribution, a Play upload key.

## 9. Pilot runbook
1. Point the build at staging: set `API_BASE_URL` to the staging https URL; `cd mobile/android && ./gradlew :app:assembleRelease`.
2. Seed email demo patients on staging (email-based; §3) + their data.
3. Distribute `app-release.apk` to internal testers (`adb install -r`, or Play internal track once a key exists).
4. Testers log in with the email demo accounts.
5. Collect crash/logs via `adb logcat` / a crash reporter (none wired yet — see rollback).

## 10. Rollback
- **App:** `adb install -r <previous app-release.apk>`; or `adb uninstall me.metocare.patient` then install the prior build. No native DB migration risk (RN app is stateless beyond SecureStore tokens; clearing app data logs the user out safely).
- **Backend:** staging deploy rollback = redeploy the prior image via `azure-staging.yml` (or ACA revision rollback). Alembic is single-head and additive this program; `alembic downgrade -1` reverses the consent-versioning migration if needed.
- **Flags:** disable `AI_ASSISTANT` / `OCR` feature flags to dark-launch features without redeploy.
