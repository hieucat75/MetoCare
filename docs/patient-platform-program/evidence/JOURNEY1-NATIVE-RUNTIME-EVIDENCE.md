# Journey 1 (First-time Patient) — Native-Runtime Evidence Package

**Status:** ✅ **JOURNEY-1-DONE (native-runtime verified)** — Charter 7 DoD satisfied on a real Android runtime.
**Date:** 2026-07-31 · **Branch:** `feat/patient-platform-journey1` (off `main`, not merged) · **Repo:** `hieucat75/MetoCare`
**Supersedes:** `JOURNEY1-INTERIM-EVIDENCE.md` (headless-only; native-runtime was pending there).

---

## 1. What was proven (Charter 7 Definition-of-Done)

> DoD: *boot the artifact and complete `login → dashboard` on an Android/iOS runtime.*

All items below were executed on a booted **Android 16 (API 36) emulator (`Pixel_6_API_36`, arm64)** running a **standalone debug build** of the app (not Expo Go — see §5). Screenshots in `journey1-native/`.

| # | Evidence | Artifact |
|---|---|---|
| 1 | App boots on native runtime, no crash | `journey1-native/01-onboarding-1of3.png` |
| 2 | First-run onboarding 1→2→3 (Vietnamese, mint Liquid Glass) | `01/02/03-onboarding-*.png` |
| 3 | Onboarding complete → routes to Login | `04-login-empty.png` |
| 4 | Login form (email/password only, ADR-02; **no** biometric button offered — safe fallback, see §3) | `05-login-filled.png` |
| 5 | Real device→backend auth: `POST /auth/login → 200`, `GET /auth/me → 200` | backend access log (§4) |
| 6 | Dashboard with authenticated user's real name ("Xin chào, Journey One") + correct empty-state | `06-dashboard-after-login.png` |
| 7 | Cold-boot session restore: emulator **restart** + relaunch → straight to Dashboard, **no re-login** | `07-dashboard-coldboot-restore.png` |

## 2. Secure storage at-rest — **device-verified** (was mock-only)

Pulled from the running app's private data dir via `run-as me.metocare.patient`:

- `shared_prefs/SecureStore.xml` holds `meto_access`, `meto_refresh`, `meto_install_id` **only as AES ciphertext** — each entry is `{"ct":"…","iv":"…","tlen":128,"scheme":"aes","usesKeystoreSuffix":true,"keystoreAlias":"key_v1",…}` (Android Keystore-backed AES-GCM). Raw proof: `journey1-native/secure-store-ciphertext.xml`.
- **Zero plaintext token leak:** `grep -rl "eyJ" /data/data/me.metocare.patient` (the JWT header prefix) returns **nothing** — no JWT exists in plaintext anywhere in app storage.
- AsyncStorage-side prefs (`expo.modules.kotlin.PersistentDataManager.xml`) contain **no secrets** (`<map />`), consistent with the design: only the non-secret install marker + onboarding flag live outside SecureStore.

This retires interim pending item *"expo-secure-store Keychain/Keystore at-rest encryption (tested vs in-memory mock)."*

## 3. Biometric safe fallback — **device-verified**

- `src/auth/biometrics.ts` guarantees `fallback: true` on every failure branch (no hardware, not enrolled, user cancel, exception).
- `app/(auth)/login.tsx:31-33` gates the biometric button on `capability.available && hasStoredSession()`.
- On this emulator **no biometric is enrolled** → `getBiometricCapability().available === false` → the biometric unlock button is correctly **suppressed** and the user completes login via password (verified: no biometric button in `05-login-filled.png`; password login succeeded). This is exactly the required safe degradation.
- **Residual (honest):** the *positive* path — an actual Face ID/fingerprint prompt succeeding — was **not** exercised, because reaching the offer UI needs a stored-session-on-login-screen state the current routing does not naturally produce, and the emulator had no enrolled biometric. The safety-critical property (never block/crash when biometrics are absent) **is** verified. Real-hardware prompt success remains a device-farm/manual-QA item, not a code risk.

## 4. Backend auth log (real device requests, via `adb reverse tcp:8000`)

Local FastAPI (SQLite, `alembic upgrade head` → `k2_s0_round3_hardening`, 71 tables) served the app. Representative lines:

```
POST /api/v1/auth/login  200  (441 ms)   user_id "-"                      → tokens issued
GET  /api/v1/auth/me     200  (17 ms)    user_id 9794dc2d-…-c3033d2395d6  → profile (role=patient)
GET  /api/v1/auth/me     200  (6 ms)     user_id 9794dc2d-…-c3033d2395d6  → dashboard fetch
GET  /api/v1/auth/me     200            (again on cold-boot relaunch)     → session restore
```

Test patient registered via the same API: `journey1.patient@gmail.com` / role `patient` / `mfa_enabled=false` (MFA not enforced for patients per current build policy).

## 5. iOS artifact & why the runtime was Android

- The **EAS iOS-simulator build now succeeds** — build `f82e8165-155a-4471-95f4-1b87540ea0c5` · status **finished** · commit `297b8ae` (HEAD) · SDK 57 · archive `https://expo.dev/artifacts/eas/NllSELfdx2wtdYxMWW42sMraHQWEziJ_BXNv5bb3_8w.tar.gz`. (The two earlier iOS builds that errored are superseded.)
- **This build machine cannot boot an iOS `.app`:** only Command Line Tools are installed (no full Xcode, no iOS simulators). Installing Xcode is a multi-GB, GUI, operator-only action.
- Charter 7 accepts an **Android *or* iOS** runtime, so verification was performed on the available Android emulator. The iOS artifact exists and is downloadable for a future Xcode-equipped run.
- **Expo Go was rejected as the runtime:** Expo Go SDK 57 repeatedly **SIGSEGV**s in the React Native bridge JS thread on this Android-16 emulator (native crash, not app logic — the JS ran: `Running "main"`, correct `apiUrl`). A **local standalone dev build** (`expo run:android`, RN 0.86.2, `BUILD SUCCESSFUL in 19m30s`) is stable and was used for all evidence above.

## 6. Known limitations & deferrals (tracked, not hidden)

- **OTA / `expo-updates`:** the `ios-simulator`/staging EAS profile references channel `staging` without `expo-updates` installed → a **non-fatal** build warning. Per direction, OTA support is **deferred** (not in Journey 1 scope); the warning is recorded here and is unrelated to any runtime failure.
- **iOS real-device boot:** pending an Xcode-equipped machine (artifact already built).
- **Biometric positive prompt:** see §3 residual.
- **P2 — patient-role gate** (`src/api/auth.ts:isPatientRole` declared but not enforced post-login): still deferred to the next auth-touching slice (backend enforces data authz). Independent review of this branch was re-run (see §7).

## 7. Independent review + repairs

A fresh-context reviewer re-audited the Journey 1 source (auth, token rotation, secure storage, routing, error/offline states). **P0: none.** Findings and their dispositions:

| Sev | Finding | Disposition |
|---|---|---|
| P1 | Role gate written (`isPatientRole`) but **never enforced** → a doctor/admin could land in the patient app | **FIXED** — `AuthContext` now enforces `isPatientRole` after every `apiMe` (login/register/bootstrap/restoreSession); non-patient → session revoked (`apiLogout`) + `NotPatientError` surfaced as `vi.errors.patientsOnly`. Regression test `__tests__/roleGate.test.tsx` (reject non-patient + admit patient). |
| P1 | Transient transport error at boot bounced a valid session to login (all `apiMe` errors treated as auth failure) | **FIXED** — `bootstrap` now distinguishes `ApiError` (real 401 → unauthenticated) from transport errors (bounded retry ×3 w/ backoff; tokens preserved). |
| P1 | "Optional biometric unlock" gates nothing on the happy path and is unreachable in practice | **Design decision deferred (not silently half-shipped).** The safety property (never block/crash when biometrics absent) is verified (§3). Making biometrics a **mandatory app-open PHI lock** changes product behavior for every user and needs product/design sign-off — it is NOT unilaterally added here. The concrete sub-bug (silent no-op on biometric-then-failed-restore) **IS fixed** (now surfaces `vi.errors.sessionExpired`). |
| P2 | `doRefresh` didn't validate the refresh body → a malformed 200 could persist the literal `"undefined"` | **FIXED** — validates both tokens are non-empty strings, else `clear()` + `false`. Regression test in `__tests__/tokenRotation.test.ts`. |
| P2 | Biometric success + failed restore was silent | **FIXED** (see P1 biometric row). |
| P2 | Registration collects no consent (`accepted_terms_version` null) | **Flagged, deferred** — consent UI + legal text is a product/compliance decision, not in Journey 1 scope. Tracked for the next auth slice alongside the role-gate follow-ups. |

Reviewer-confirmed-correct (no change): single-flight refresh, forced-logout on refresh reuse, secrets-only-in-SecureStore, install-UUID reinstall-reset design, email/password-only (no phone/OTP), network-status default-online, login-401→invalid-credentials mapping.

**Post-repair verification:** `tsc --noEmit` clean · **jest 40/40 (8 suites)** incl. 2 new role-gate tests (exercise the real `AuthProvider` + `login()`/bootstrap via mocked backend) + 1 new refresh-guard test · `eslint` 0 errors. The patient happy-path (§1) was device-verified before the repairs; the additions are guarded and the patient-admit test confirms the gate does not regress it. (On-device re-run of the patched bundle was limited by software-GPU emulator instability; not faked.)

## 8. Reproduction

```
# backend
cd backend && source .venv/bin/activate && alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
# emulator + bridge
emulator @Pixel_6_API_36 -no-snapshot -gpu host    # (swiftshader_indirect also works, slower)
adb reverse tcp:8000 tcp:8000 && adb reverse tcp:8081 tcp:8081
# app (standalone dev build — NOT Expo Go)
cd mobile && APP_ENV=development npx expo run:android
```
