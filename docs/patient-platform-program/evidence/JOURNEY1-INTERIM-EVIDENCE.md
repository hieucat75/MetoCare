# Journey 1 (First-time Patient) — Interim Evidence Package

> **SUPERSEDED 2026-07-31** by `JOURNEY1-NATIVE-RUNTIME-EVIDENCE.md` — native-runtime
> verification is now complete (login→dashboard booted on an Android runtime,
> secure-store at-rest encryption + biometric safe fallback device-verified).
> This doc is retained as the headless-phase record.

**Status:** IMPLEMENTED TO NATIVE-RUNTIME BOUNDARY · headless-verified · **NOT Journey-1-Done** (native-runtime evidence pending, per Charter 7).
**Date:** 2026-07-30 · **Branch:** `feat/patient-platform-journey1` (off `main`, not merged) · **Repo:** `hieucat75/MetoCare`

---

## 1. Source commits
| SHA | What |
|---|---|
| `a500453` | Batch-0 guardrail: Alembic single-head test (`test_single_alembic_head`) in existing CI pytest job |
| `bd96e02` | Journey 1 Expo foundation (38 files, `mobile/`) |
| `7d8728c` | Independent-review fixes (P1 staging host fail-loud; P2 rotation comment) |

## 2. Architecture note
Expo Router (strict TS) app in `mobile/`. Layers: screens (`app/`) → `AuthContext` → `api/client` (injectable `createApiClient`) → `storage/tokenStore` → `storage/secureStore` (expo-secure-store). All dependencies (fetch, token store, secure store, UUID generator) are injected so auth/rotation/identity logic is unit-testable without a device.
- **Auth (ADR-02):** email/password only; **no phone/OTP anywhere** (`phone` exists solely as a nullable mirror field on `UserResponse`). Register/login → rotated tokens in Keychain/Keystore → `/auth/me` → authenticated. Route groups: `(auth)` vs `(app)` guard redirects.
- **Token rotation:** mirrors the web contract (`frontend/src/lib/api/client.ts`) — single-flight refresh promise, one retry-after-refresh, then `clear()` + `onForcedLogout` on continued/failed 401 (forced logout on refresh-reuse).
- **Secure storage:** tokens (`meto_access`/`meto_refresh`) + install UUID live **only** in expo-secure-store; AsyncStorage holds only the non-secret install marker + onboarding flag.
- **Install UUID (ADR-03):** `expo-crypto` random UUID (never a hardware ID), gated by an AsyncStorage install marker so a reinstall (which wipes AsyncStorage but not the iOS Keychain) mints a **new** UUID; cleared on account unlink.
- **States:** loading/error/retry + offline (NetInfo → `OfflineBanner`) wired into login + dashboard (verified by review, not cosmetic). Vietnamese-first copy (`src/i18n/vi.ts`). Liquid Glass tokens (`#0F9C6E` mint / `#6D3FBE` AI).
- **Env:** dev=localhost, staging=inject `EXPO_PUBLIC_API_URL` (real FQDN not committed; see Known Limitations).

## 3. Tests & results (independently re-run by a fresh-context reviewer — not self-report)
| Check | Result |
|---|---|
| `npx tsc --noEmit` | **PASS** (exit 0, 0 errors) |
| `npx jest --ci` | **PASS** — 6 suites / **30 tests**, 0 failed (tokenRotation, installId, authContract, secureStore, dashboard, login) |
| `npx expo export` | **PASS** — bundles iOS (2.5 MB hbc) + Android (2.8 MB hbc) + web (1.2 MB) headlessly |
| `npx expo-doctor` | **20/20 PASS** |
| `npx eslint .` | PASS (0 errors; 10 warnings, all in test-mock hoisting) |
| Coverage | ~56% stmts / 49% branch (above configured thresholds) |
| Backend `test_single_alembic_head` + chain-order | **PASS** (2/2) |

## 4. EAS cloud-artifact attempts (real outcomes, no fabrication)
Expo account `hieucat75` is logged in. Project `@hieucat75/metocare-mobile` (projectId `7ba4d27e-9170-4b62-a3ae-a4f16575a889`).
| Build | Profile | ID | Status | Note |
|---|---|---|---|---|
| iOS #1 | ios-simulator | `1772e3ff-2fb1-4950-a447-db304987ad48` | **errored** (~90s) | ran against uncommitted tree |
| iOS #2 | ios-simulator | `b2b4a34f-1b8b-46a3-8d2c-6425c9b444a0` | **errored** (~1m42s, no artifact) | committed code — so uncommitted-tree was **not** the cause |
| Android | android-apk | — | **blocked** | Free-plan Android build quota exhausted; resets 2026-08-01 |

**No EAS artifact produced.** iOS build phase-level error cause is only in EAS's auth-gated web logs (https://expo.dev/accounts/hieucat75/projects/metocare-mobile/builds/b2b4a34f-1b8b-46a3-8d2c-6425c9b444a0) and could not be retrieved programmatically from this session. `expo export` is the standing headless proof the app bundles for all three platforms. Minor: `ios-simulator` profile references channel `staging` without `expo-updates` installed (non-fatal warning; unrelated to the error).

## 5. Independent review result
Fresh-context reviewer re-ran all three headless checks (green) and reviewed source: **P0 = none.** P1 = staging host placeholder (**fixed**, `7d8728c`). P2 = rotation comment (**fixed**) + patient-role gate (**deferred**, below). Verdict: **SHIP-READY (headless)**.

## 6. Known limitations & native-runtime evidence STILL PENDING
Logic-tested via mocks only — **explicitly not device-verified**:
- expo-secure-store Keychain/Keystore at-rest encryption (tested vs in-memory mock).
- expo-local-authentication biometric hardware (Face ID/Touch ID) — capability + fallback logic tested with a mock; real prompt untested.
- Install-UUID reinstall-reset — marker/Keychain-persistence logic unit-tested with fakes; true iOS reinstall behavior needs a device.
- **Booted `login → dashboard` on an Android/iOS runtime — NOT done.** No simulator/emulator/device in this session; both iOS EAS builds errored; Android quota-blocked.

**Deferred (tracked, not hidden):**
- **P2 — patient-role gate** (`src/api/auth.ts:isPatientRole` declared but not enforced post-login). Non-blocking (backend enforces data authz). To be implemented in the next auth-touching slice.

## 7. External dependencies recorded
- Real **staging backend FQDN** — an Azure/CI deploy value, **not committed** to the repo; staging builds must inject `EXPO_PUBLIC_API_URL`.
- **EAS iOS/Android build success** — needs the cloud iOS build error resolved (auth-gated logs) and/or Android quota reset (2026-08-01), or a local simulator/device to boot the artifact.

## 8. Definition-of-Done gate (Charter 7)
Journey 1 is **NOT Done**: it requires booting the artifact and completing `login → dashboard` on an Android/iOS runtime. That evidence does not yet exist and is **not claimed**.
