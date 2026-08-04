# 11 — Mobile Distribution (WS11)

**Date:** 2026-08-04 · **Assessor:** independent Mobile-Distribution assessor (fresh context, direct source inspection)
**Branch:** `feat/patient-platform-journey2` · **HEAD at assessment:** `bfd6735` (brief said `6ab3b04`; `bfd6735` is a backend seed fix — no mobile code changed)
**Method:** every claim is traced to `file:line` or to a command whose output is reproduced. Prior evidence docs (`ANDROID-PILOT-RC.md`, `evidence/native-j2j5/`) were read, then **re-verified against the tree**; where they disagree with the tree, the tree wins and the divergence is called out.
**Gate:** this workstream gates **public beta** (`TRACKING.md` §A). The internal Android pilot is a separate, lower gate — see §4.

> **Headline.** Android internal distribution is real and reproducible today; everything beyond it is blocked on credentials **and** on four config/artifact gaps that no credential fixes. The most consequential new finding: **the release APK sitting on disk — the pilot artifact — was built before the WS11-F3 permission fix and still declares `RECORD_AUDIO` and `SYSTEM_ALERT_WINDOW`** (WS11-F4). The second: **there is no in-app account deletion**, so the GDPR work in `0da0f06` does **not** satisfy the Google Play / Apple store rule (WS11-F5). The third: **there is no OTA or hotfix path at all** (WS11-F7) — a bad pilot build can only be replaced by hand.

---

## 1. Verified artifact & config inventory

### 1.1 App identity and versioning

| Item | Value | Source |
|---|---|---|
| Expo SDK | `^57.0.9` | `mobile/package.json:20` |
| React Native | `0.86.2` (React `19.2.3`) | `mobile/package.json:31-33` |
| App name | `MetoCare` / `MetoCare (Staging)` | `mobile/app.config.ts:42` |
| Slug | `metocare-mobile` | `app.config.ts:43` |
| Version string | `1.0.0` | `app.config.ts:44` |
| Android package | `me.metocare.patient` (dev/prod) / `me.metocare.patient.staging` | `app.config.ts:58-60` |
| iOS bundle id | `me.metocare.patient` / `me.metocare.patient.staging` | `app.config.ts:50-51` |
| `android.versionCode` | **absent from `app.config.ts`**; hardcoded `1` in generated gradle | `android/app/build.gradle:95` |
| `ios.buildNumber` | **absent** | `app.config.ts` (no key) |
| EAS project id | `7ba4d27e-9170-4b62-a3ae-a4f16575a889` (override `EAS_PROJECT_ID`) | `app.config.ts:87` |
| App icon / splash / adaptive icon | **none declared**; `mobile/assets/` does not exist → Android ships Expo's default `@mipmap/ic_launcher` | `app.config.ts` (no keys); `android/app/src/main/AndroidManifest.xml:15` |
| minSdk / targetSdk | 24 / 36 | merged manifest `.../packaged_manifests/release/…/AndroidManifest.xml:7-9` |

`APP_ENV` has exactly two members — `'development' | 'staging'` (`app.config.ts:13`, `src/config/env.ts:9`). **There is no `production` app environment.**

### 1.2 Build profiles (`mobile/eas.json`, 37 lines)

| Profile | distribution | channel | env | Produces |
|---|---|---|---|---|
| `development` (`:7-14`) | `internal` | `development` | `APP_ENV=development` | dev client |
| `android-apk` (`:15-24`) | `internal` | `staging` | `APP_ENV=staging` | APK for sideloading |
| `ios-simulator` (`:25-34`) | `internal` | `staging` | `APP_ENV=staging` | **simulator-only** `.app` |

- `cli.appVersionSource: "remote"` (`:4`) — EAS is told to own version codes, but the checked-out gradle pins `versionCode 1` (`build.gradle:95`). Two conflicting sources of truth (WS11-F6).
- **`"submit": {}`** (`:36`) — no Play track, no App Store Connect app id, no Apple team id. `eas submit` cannot run.
- **No profile sets `distribution: "store"`**, and no `production` profile exists → a Play/TestFlight-grade build cannot be produced from this config as written.
- **No profile sets `EXPO_PUBLIC_API_URL`** → see §3.

### 1.3 Permissions

Declared in `app.config.ts` — an **allow-list is absent**; only a block-list exists (`:66-69`, added in `9692bb3`):

```diff
+    blockedPermissions: [
+      'android.permission.RECORD_AUDIO',
+      'android.permission.SYSTEM_ALERT_WINDOW',
+    ],
```

Current **generated** manifest (`android/app/src/main/AndroidManifest.xml`, mtime `2026-08-03 17:22`) — clean:
`INTERNET` (`:2`), `READ_EXTERNAL_STORAGE` maxSdk 32 (`:3`), `USE_BIOMETRIC` (`:4`), `USE_FINGERPRINT` (`:5`), `VIBRATE` (`:6`), `WRITE_EXTERNAL_STORAGE` maxSdk 32 (`:7`).

Current **merged/packaged** manifest that produced the APK on disk (`android/app/build/intermediates/packaged_manifests/release/processReleaseManifestForPackage/AndroidManifest.xml`, mtime `2026-08-03 15:48`) — **not** clean:
`INTERNET` (`:11`), `READ_EXTERNAL_STORAGE` (`:12-14`), **`RECORD_AUDIO` (`:15`)**, **`SYSTEM_ALERT_WINDOW` (`:16`)**, `USE_BIOMETRIC` (`:17`), `USE_FINGERPRINT` (`:18`), `VIBRATE` (`:19`), `WRITE_EXTERNAL_STORAGE` (`:20-22`), `ACCESS_NETWORK_STATE` (`:55`), `ACCESS_WIFI_STATE` (`:56`), `CAMERA` (`:57`), `me.metocare.patient.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` (`:63`).

Merger blame proves provenance:
```
$ grep -n "RECORD_AUDIO" -A2 mobile/android/app/build/outputs/logs/manifest-merger-release-report.txt
175:uses-permission#android.permission.RECORD_AUDIO
176-ADDED from …/mobile/android/app/src/main/AndroidManifest.xml:4:3-68
```
Root cause of the microphone request: `expo-image-picker`'s config plugin adds `RECORD_AUDIO` unless `microphonePermission: false` (`node_modules/expo-image-picker/plugin/build/withImagePicker.js:10-13`). `blockedPermissions` neutralises it — but only on a **rebuild**. → **WS11-F4**.

### 1.4 Signing

```groovy
// mobile/android/app/build.gradle:100-107
signingConfigs { debug { storeFile file('debug.keystore'); storePassword 'android'
                        keyAlias 'androiddebugkey'; keyPassword 'android' } }
// :112-115
release {
    // Caution! In production, you need to generate your own keystore file.
    signingConfig signingConfigs.debug
}
```
**The release APK is signed with the public Android debug keystore.** Correct for `adb install`; rejected by Play. R8/minify is off by default (`build.gradle:69,118`). Confirms WS11-F1.

### 1.5 The artifact on disk

```
mobile/android/app/build/outputs/apk/release/app-release.apk   97,920,924 B   2026-08-03 15:49
mobile/android/app/build/outputs/apk/debug/app-debug.apk      225,834,098 B   2026-08-01 03:07
```
`output-metadata.json`: `applicationId me.metocare.patient`, `variantName release`, `versionCode 1`, `versionName 1.0.0`, `minSdkVersionForDexing 24`.

> The release APK (15:49) is **older** than the cleaned manifest (17:22) and far older than commit `9692bb3` (2026-08-04 09:44). **The pilot artifact still contains the two unjustified permissions.**

### 1.6 Source-control posture

```
$ sed -n '11,13p' mobile/.gitignore
# Native
*.orig.*
/ios
/android
$ git ls-files mobile/android | wc -l
0
```
The entire native Android project is untracked. Nothing about the shipped APK — `versionCode`, signing config, manifest — is under version control. → **WS11-F6**.

---

## 2. Distribution matrix

Legend: ✅ READY · 🔑 BLOCKED-ON-CREDENTIAL · 🛠 BLOCKED-ON-WORK · ⛔ NOT-STARTED

| Platform | Channel | Status | Exact blocker → exact step |
|---|---|---|---|
| **Android** | **Internal APK (`adb install` / direct file share)** | ✅ **READY** (with §4 rebuild) | None credential-wise. Must rebuild to pick up `blockedPermissions` (WS11-F4) and to bake the correct staging URL (R-03 / WS11-F10). Runbook in §4. |
| **Android** | **Play Console — Internal testing track** | 🔑 + 🛠 | **Credential:** Google Play Developer account ($25 one-off) + an **upload key** (`keytool -genkey -v -keystore metocare-upload.jks -alias metocare -keyalg RSA -keysize 2048 -validity 10000`) or EAS-managed credentials (`eas credentials -p android`). **Work:** (a) add a `production`/`play` profile to `eas.json` with `distribution: "store"` and `android.buildType: "app-bundle"` (Play requires an **AAB**, not an APK, for new apps); (b) fill `eas.json` `submit.android` (`serviceAccountKeyPath`, `track: "internal"`); (c) fix `versionCode` monotonicity (WS11-F6); (d) supply an app icon (WS11-F8); (e) **in-app account deletion** — a hard Play policy gate (WS11-F5); (f) complete the Data safety form (§6). |
| **Android** | **Play — Closed/Open testing, Production** | 🔑 + 🛠 | Everything above, plus a published privacy policy URL, a Health-apps declaration form, and 12 testers × 14 days if the account is a personal (non-organisational) developer account. |
| **iOS** | **Simulator build (`ios-simulator` profile)** | ✅ READY | `eas build -p ios --profile ios-simulator`. No signing needed. Not installable on a device. |
| **iOS** | **TestFlight (internal + external)** | 🔑 + 🛠 | **Credential:** Apple Developer Program membership, an App Store Connect app record, distribution certificate + provisioning profile (`eas credentials -p ios`). **Work:** (a) no `mobile/ios/` project has ever been generated — `find . -maxdepth 3 -type d -name ios -not -path "*/node_modules/*"` returns nothing, and `/ios` is git-ignored (`mobile/.gitignore:12`); (b) **no `PrivacyInfo.xcprivacy` privacy manifest exists anywhere in the repo** — mandatory for App Store/TestFlight submission since 2024-05; (c) no `ios.buildNumber`; (d) no `production` eas profile; (e) `submit.ios` block empty. Only `ITSAppUsesNonExemptEncryption: false` is set (`app.config.ts:54-56`) — that part is correct. |
| **iOS** | **App Store** | 🔑 + 🛠 | All of TestFlight, plus §6's full review checklist including in-app account deletion (Apple Guideline 5.1.1(v)) and Health-data declarations. |
| **Web / PWA** | — | ⛔ NOT-STARTED | `react-native-web` is a dependency and `expo export --platform all` exists (`package.json:6-16`), but nothing targets web distribution. Out of scope for v1. |

Credential ownership and workarounds are already catalogued in `docs/patient-platform-program/CREDENTIAL-READINESS-MATRIX.md:12-13` (Apple signing = gap #1, Google Play signing = gap #2).

---

## 3. R-03 — the baked API base URL, resolved exactly

**The mechanism.** `mobile/src/config/env.ts:20-21`:

```ts
export const API_BASE_URL: string =
  extra.apiUrl ?? process.env.EXPO_PUBLIC_API_URL ?? DEFAULT_API_URL   // :18 'http://localhost:8000/api/v1'
```

`extra.apiUrl` is frozen into the bundle at build time by `app.config.ts:30,83`:

```ts
const apiUrl = process.env.EXPO_PUBLIC_API_URL ?? API_URL_BY_ENV[APP_ENV]
// API_URL_BY_ENV = { development: 'http://localhost:8000/api/v1',
//                    staging:     'https://staging.metocare.invalid/api/v1' }   // :22-27
```

So the precedence at **build** time is `EXPO_PUBLIC_API_URL` → per-`APP_ENV` default, and at **run** time `extra.apiUrl` always wins. There is no runtime override, no in-app server picker. **Changing the backend URL requires a rebuild + reinstall.**

**Three distinct hazards, all live:**

1. `APP_ENV` unset → `development` (`app.config.ts:15`) → `http://localhost:8000/api/v1`. A tester's phone has no server on `localhost:8000`; the app fails to log in with a network error. This is what `ANDROID-PILOT-RC.md:14` warns about.
2. `APP_ENV=staging` without `EXPO_PUBLIC_API_URL` → the deliberate `.invalid` placeholder (`app.config.ts:22`), which **fails loudly** — good design. Only a `console.warn` fires at config time (`:32-38`); the build still succeeds.
3. **`mobile/.env.staging:4` commits `EXPO_PUBLIC_API_URL=https://metocare-staging.azurecontainerapps.io/api/v1`** — which is *not* a valid Azure Container Apps FQDN shape (ACA mints `<app>.<random>.<region>.azurecontainerapps.io`), and directly contradicts the comment two files over (`app.config.ts:17-18`: *"no azurecontainerapps.io host exists in the tree"*). Anyone who does the obvious thing (`cp .env.staging .env` / `dotenv -e .env.staging`) gets a **silently wrong, plausible-looking host** — exactly the failure mode the `.invalid` placeholder was introduced to prevent. → **WS11-F10**.

**The exact fix for the pilot build.** Do not rely on `.env.staging`. Read the live FQDN and pass it explicitly:

```bash
# 1. Resolve the real staging FQDN (requires Azure login; do NOT edit any workflow/infra)
STAGING_FQDN=$(az containerapp show -g <RG> -n ca-metocare-backend \
                 --query properties.configuration.ingress.fqdn -o tsv)
export EXPO_PUBLIC_API_URL="https://${STAGING_FQDN}/api/v1"

# 2. Sanity-check it before baking it in
curl -fsS "https://${STAGING_FQDN}/info" | jq '{env, migration_version, ocr, ai_assistant, consent_gate}'

# 3. Build with both vars set (APP_ENV drives name/package, EXPO_PUBLIC_API_URL drives the URL)
export APP_ENV=staging
cd mobile && npx expo prebuild -p android --clean      # regenerates the manifest → applies blockedPermissions
cd android && ./gradlew :app:assembleRelease --rerun-tasks   # forces a fresh JS bundle

# 4. PROVE the URL is in the artifact before shipping it
unzip -p app/build/outputs/apk/release/app-release.apk assets/index.android.bundle \
  | strings | grep -o "https://[a-z0-9.-]*/api/v1" | sort -u
```

Step 4 is not optional — it is the only check that catches a stale bundle, and a stale bundle is precisely what §1.5 shows happened with the permissions.

**Permanent fix:** add `"env": { "APP_ENV": "staging", "EXPO_PUBLIC_API_URL": "<real staging URL>" }` to the `android-apk` profile in `eas.json:15-24` so the value lives in one reviewed place, and correct or delete `mobile/.env.staging:4`.

---

## 4. Internal Android pilot — build & install runbook

**Preconditions:** JDK 17, Android SDK, `adb`; Node ≥20; `az` CLI logged in (step 1 only). Do **not** touch Azure workflows or the Postgres firewall.

```bash
# ── 0. Clean state ────────────────────────────────────────────────────────────
cd /Users/pth/Developer/Metocare/mobile
npm ci
rm -rf android                        # WS11-F6: android/ is untracked build output, not source

# ── 1. Point at staging (see §3) ──────────────────────────────────────────────
export APP_ENV=staging
export EXPO_PUBLIC_API_URL="https://<verified-staging-fqdn>/api/v1"
curl -fsS "${EXPO_PUBLIC_API_URL%/api/v1}/info"        # must return env=staging + the expected migration head

# ── 2. Regenerate native project (applies blockedPermissions → WS11-F4) ───────
npx expo prebuild -p android --clean

# ── 3. Verify the manifest BEFORE building ───────────────────────────────────
grep -c "RECORD_AUDIO\|SYSTEM_ALERT_WINDOW" android/app/src/main/AndroidManifest.xml   # must print 0

# ── 4. Build the standalone release APK ──────────────────────────────────────
cd android && ./gradlew :app:assembleRelease --rerun-tasks && cd ..

# ── 5. Verify the ARTIFACT (not the source) ──────────────────────────────────
grep -c "RECORD_AUDIO\|SYSTEM_ALERT_WINDOW" \
  android/app/build/intermediates/packaged_manifests/release/*/AndroidManifest.xml     # must print 0
unzip -p android/app/build/outputs/apk/release/app-release.apk assets/index.android.bundle \
  | strings | grep -o "https://[a-z0-9.-]*/api/v1" | sort -u                            # must be the staging URL only
shasum -a 256 android/app/build/outputs/apk/release/app-release.apk | tee ../docs/launch-readiness/evidence/apk-$(date +%Y%m%d).sha256

# ── 6. Install ───────────────────────────────────────────────────────────────
adb install -r android/app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package me.metocare.patient | sed -n '/requested permissions/,/install permissions/p'   # third check

# ── 7. Smoke ─────────────────────────────────────────────────────────────────
adb logcat -c && adb logcat | tee pilot-$(date +%Y%m%d-%H%M).log &
# login with a synthetic email account → dashboard → each journey
```

**Distribution to testers.** The APK is ~98 MB. Ship it over a channel that preserves the checksum (private link + published SHA-256), require testers to enable "install unknown apps", and record `device model / Android version / APK SHA-256` per tester — there is no crash reporter to reconstruct this later (`mobile/src/lib/monitor.ts:51,61`: console adapter only; no Sentry dependency in `package.json:17-46`).

**Alternative (avoids the debug-keystore and the local toolchain):** `eas build -p android --profile android-apk` produces an internally-distributable APK signed with an EAS-managed keystore and a shareable install URL. It still needs `EXPO_PUBLIC_API_URL` added to the profile (§3) and an Expo account, but no Play credential.

---

## 5. Version & rollback

### 5.1 Version scheme (current, and what it must become)

| Field | Today | Problem | Required |
|---|---|---|---|
| `version` | `1.0.0` (`app.config.ts:44`) | fine | keep; bump per release |
| `android.versionCode` | `1`, hardcoded in **untracked** gradle (`build.gradle:95`) | Play rejects any upload whose `versionCode` is ≤ the previous one. With the file untracked and `--clean` prebuilds regenerating it, the value resets to 1 every time. | Either set `android.versionCode` explicitly in `app.config.ts` and bump it in the same commit as `version`, **or** rely on `eas.json:4` `appVersionSource: "remote"` and always build via EAS. Pick one — today both exist and disagree. |
| `ios.buildNumber` | absent | same class of problem for TestFlight | add, or use remote versioning |
| Channel binding | `eas.json` declares `channel: "staging"` (`:17,30`) but `app.config.ts` has **no `updates`/`runtimeVersion`** block and the native manifest sets `expo.modules.updates.ENABLED=false` (`AndroidManifest.xml:16`) | channels are inert | see §7 |

**Proposed convention:** `versionName = <semver>`, `versionCode = YYMMDDNN` (e.g. `26080401`) — monotonic, human-readable, collision-free across same-day rebuilds. Record `version / versionCode / commit SHA / APK SHA-256 / API_BASE_URL` for every artifact handed to a tester.

### 5.2 Rollback

| Layer | Procedure | Verified |
|---|---|---|
| **App (internal APK)** | `adb install -r <previous app-release.apk>`. If `versionCode` did not increase, Android refuses the downgrade → `adb uninstall me.metocare.patient` then install the older APK. Uninstall clears app data, which logs the user out safely (tokens live in SecureStore; `AndroidManifest.xml:15` sets `fullBackupContent=@xml/secure_store_backup_rules`). | matches `ANDROID-PILOT-RC.md:10` (Rollback); the downgrade caveat is **new** here and is a direct consequence of the pinned `versionCode 1` |
| **App (Play internal track)** | Halt the rollout, then promote the previous release. Play does not delete an installed build — a fix-forward with a higher `versionCode` is the only true rollback. | n/a — track not created |
| **App (TestFlight)** | Expire the build; testers keep the installed binary until they update. Fix-forward only. | n/a |
| **Backend** | Redeploy the prior image via `azure-staging.yml` (`workflow_dispatch`) or ACA revision rollback; `alembic downgrade -1` reverses the additive consent-versioning migration. | `TRACKING.md` §I |
| **Feature** | Flip `FEATURE_AI_ASSISTANT` / `MCP_FEATURE_OCR` on the Container App — no client rebuild, no reinstall. **This is the only same-day mitigation the mobile fleet has** (see §7). | `feature_flags.py:78-80` |

**Because there is no OTA, the app-layer rollback always costs a manual reinstall on every tester's device.** Keep every APK you distribute, with its SHA-256, for the duration of the pilot.

---

## 6. Store-review readiness checklist

| # | Requirement | Play | App Store | State | Action |
|---|---|---|---|---|---|
| 1 | **Signed with a non-debug key** | required | required | ⛔ debug keystore (`build.gradle:112-115`) | generate upload key or use `eas credentials` |
| 2 | **AAB (Play) / IPA (Apple)** | AAB required for new apps | IPA | ⛔ only APK profile (`eas.json:18-20`), no iOS device profile | add a store profile |
| 3 | **Every requested permission justified** | required | required | 🛠 source clean (`app.config.ts:66-69`); **artifact not** (WS11-F4). Remaining set is defensible: `INTERNET`, `CAMERA` + storage (document photo, `add-document.tsx:60-66`), `USE_BIOMETRIC`/`USE_FINGERPRINT` (`expo-local-authentication`, `app.config.ts:74-79`), `VIBRATE`, `ACCESS_NETWORK_STATE`/`ACCESS_WIFI_STATE` | rebuild + re-verify with `dumpsys package` |
| 4 | **iOS purpose strings, localised** | n/a | required | 🛠 `expo-image-picker` is **not** listed in `app.config.ts:71-80`, so its plugin defaults apply: `"Allow $(PRODUCT_NAME) to access your camera"` / `"…your photos"` (`node_modules/expo-image-picker/plugin/build/withImagePicker.js:7-9`) — **English strings in a Vietnamese-only app**. App Review rejects vague/mismatched purpose strings. | list the plugin explicitly: `['expo-image-picker', { microphonePermission: false, cameraPermission: 'MetoCare cần dùng camera để bạn chụp đơn thuốc / phiếu xét nghiệm.', photosPermission: 'MetoCare cần truy cập ảnh để bạn chọn tài liệu y tế đã chụp.' }]` — this also removes `RECORD_AUDIO` at source, making `blockedPermissions` redundant |
| 5 | **Privacy manifest `PrivacyInfo.xcprivacy`** | n/a | mandatory since 2024-05 | ⛔ absent repo-wide | author one declaring the required-reason APIs used by RN/Expo (`UserDefaults`, file timestamp, disk space, boot time) and the data types in row 6 |
| 6 | **Privacy nutrition labels / Data safety form** | required | required | ⛔ not drafted | Declare: *Health & fitness* (lab results, medications, metrics), *Personal info* (name, email, DOB), *Photos* (medical document images), *Identifiers*, *App activity*. Linked to identity: **yes**. Used for tracking: **no**. Encrypted in transit: **yes** (HTTPS). Deletion available: **yes** *(only once WS11-F5 ships)*. **Blocked on the OCR-F1 decision** — if medical images are sent to Azure Document Intelligence, the label must disclose a third-party processor. |
| 7 | **Health-data declaration** | Play Health-apps declaration form | App Review notes + (only if HealthKit is used) | ⛔ not drafted | Declare: not a medical device; no diagnosis; patient-confirmed records only. Cite the no-auto-canonical invariant and the AI output-safety guard as evidence. Do **not** claim HealthKit — the app does not use it. |
| 8 | **Account deletion initiated in-app** | **Play policy — required for any app with account creation**; a web deletion link alone is insufficient | **Guideline 5.1.1(v)** — required | ⛔ **NOT SATISFIED** | see below |
| 9 | **Published privacy policy URL** | required | required | UNVERIFIED — no URL in the mobile tree; `metocare.me` may host one. Run: check the marketing site and pin the URL into store metadata. | |
| 10 | **App icon + store assets** | required | required | ⛔ no icon/splash declared; `mobile/assets/` absent (WS11-F8) | add `icon`, `adaptiveIcon`, `splash` |
| 11 | **Age rating / content rating questionnaire** | required | required | ⛔ not started | medical-information category |
| 12 | **Crash reporting for review triage** | recommended | recommended | ⛔ console-only adapter (`mobile/src/lib/monitor.ts:51,61`) | WS5-F3 credential (Sentry DSN) |

### 6.1 Does `0da0f06` satisfy the store account-deletion rule? — **No.**

`0da0f06` added a complete, correct **backend** capability:
- `GET /patients/{patient_id}/export` (`backend/app/api/v1/routes/account.py:45`) — full data export, audited.
- `DELETE /patients/{patient_id}/account` (`account.py:79`) — soft-delete + anonymize (`services/account.py:137`), refresh-token revocation, and post-commit object-storage blob erasure (`account.py:105-111`).

But `git show --stat 0da0f06` touches **9 files, zero of them under `mobile/`**. And in the tree:

```
$ ls -R mobile/app          # 20 screens total
(app)/: _layout add-document consent consultations consultations/[id] dashboard
        marketplace marketplace/[doctorId] marketplace/[doctorId]/book
        medications medications/[id] meto reminders review/[documentId]
(auth)/: _layout login onboarding register
```

There is **no settings, profile, or account screen**; the dashboard's navigation targets are `/add-document`, `/meto`, `/medications`, `/reminders`, `/marketplace`, `/consultations`, `/consent` (`mobile/app/(app)/dashboard.tsx:77-123`). No file in `mobile/src/api/` calls `/account` or the export endpoint, and `mobile/src/i18n/vi.ts` has no delete-account copy.

⇒ **A patient cannot initiate deletion from inside the app.** Both Google Play's data-deletion policy and Apple Guideline 5.1.1(v) require in-app initiation for accounts created in-app. This is a **store-submission blocker**, not a GDPR blocker (GDPR is satisfied by the endpoint + a documented request channel). → **WS11-F5**. The remedy is small: one Settings screen with "Tải dữ liệu của tôi" → `GET …/export` and "Xoá tài khoản" → typed-confirmation → `DELETE …/account` → clear SecureStore → route to `/(auth)/login`.

---

## 7. Update / hotfix path during a pilot — there isn't one

| Mechanism | Present? | Evidence |
|---|---|---|
| `expo-updates` (OTA) | **No** — not a dependency | `mobile/package.json:17-36` |
| `updates` / `runtimeVersion` in config | **No** | `app.config.ts` — keys absent |
| Native OTA switch | **explicitly disabled** | `android/app/src/main/AndroidManifest.xml:16` `expo.modules.updates.ENABLED=false` |
| EAS channels | declared but inert | `eas.json:10,17,30` with no updates runtime to consume them |
| In-app "update available" prompt / forced-upgrade check | **No** — no version-check call in `mobile/src/api/` | — |
| Feature flags (server-side) | **Yes** | `backend/app/core/feature_flags.py:78-80`; flipping `MCP_FEATURE_OCR` / `FEATURE_AI_ASSISTANT` on the Container App changes behaviour with no client change |

**Consequences for pilot operations:**
- A JS-only bug requires a full rebuild, re-distribution, and a manual reinstall by every tester.
- There is no way to force testers off a broken build, and no way to know who is on which build — the app never reports its version to the backend.
- The **only** same-day mitigation available is a server-side feature-flag flip or a backend redeploy.

**Recommended before a wider pilot (in effort order):**
1. Add `expo-updates` + `runtimeVersion: { policy: "appVersion" }` and bind the `staging` channel already declared in `eas.json`. This converts JS-only hotfixes from "reinstall everyone" to `eas update --branch staging`. Native changes still need a rebuild.
2. Send `X-App-Version` / `X-Build` on every request from `mobile/src/api/client.ts` and log it server-side — a prerequisite for knowing what a tester is running.
3. Add a minimum-supported-version check (backend returns a floor; the app blocks with an upgrade prompt below it).
4. Wire a real crash reporter behind the existing `MonitorAdapter` seam (`mobile/src/lib/monitor.ts:61-64`) — a pilot with no OTA *and* no crash telemetry is flying blind twice.

---

## 8. Push notifications, and how a reminder actually reaches a patient (WS12-F1 re-verified)

**Nothing on the device can notify the patient.**

```
$ grep -rl "expo-notifications\|getExpoPushTokenAsync\|Notifications\.\|firebase\|google-services" \
    mobile/src mobile/app mobile/__tests__ mobile/android/app/src
(no output)
```
- `expo-notifications` is **not** a dependency (`mobile/package.json:17-36`); no `google-services.json`; no APNs key/entitlement; no `POST_NOTIFICATIONS` permission in any manifest; no local/scheduled notifications.
- Backend `app/services/notification_transport.py:36-82` fans out over exactly two real transports: a deterministic in-memory sink (`:58-60`) and an in-app `Notification` DB row (`:62-74`). Push is a **label append behind a setting that does not exist** — `_push_configured` reads `getattr(settings, "push_credentials_configured", False)` (`:28-29`), and `push_credentials_configured` is absent from `backend/app/core/config.py`, so it is permanently `False` (`:77-78`). There is no APNs/FCM client code anywhere.

**The real path today is pull-only, and shallower than it looks:**

1. Patient opens the app and navigates to Reminders (`mobile/app/(app)/reminders.tsx:19,32`).
2. `useReminders` fires **once on mount** — `getRemindersDue(...)` at `mobile/src/features/medication/useReminders.ts:54`, from a `useEffect` at `:63-66`. **No interval, no background fetch, no re-fetch on foreground.**
3. `GET /patients/{id}/reminders/due` (`mobile/src/api/medication.ts:104-106` → `backend/app/api/v1/routes/medication_schedule.py:243`) materializes due doses (`:253`) and calls `deliver_due_reminders` (`:260`).
4. That flips `pending → notified` and calls `notification_transport.deliver(...)` (`backend/app/services/medication_schedule.py:289`) — writing an in-app `Notification` row.
5. **The mobile app never reads those rows.** `grep -rn "notification" mobile/src mobile/app` → no matches, although the backend exposes notification routes (`backend/app/api/v1/router.py:46,81`).

⇒ A medication reminder reaches a patient **only if the patient independently remembers to open the app and tap Reminders** — at which point the reminder marks itself delivered. For a *medication adherence* product this is the single largest product gap in the mobile tier, and it is only partly a credential problem: even with APNs/FCM keys, there is no client wiring and no device-token registration endpoint.

**Ordered remediation:** (1) `expo-notifications` + local scheduled notifications from the dose schedule — works with **no** external credential and covers the common case; (2) device-token registration endpoint + real APNs/FCM in `notification_transport.deliver` (credential-gated); (3) render in-app `Notification` rows in the app so the "in-app" transport stops being write-only.

---

## 9. NEW findings (this assessment)

Existing WS11-F1 (debug-signed), WS11-F2 (iOS not submittable), WS12-F1 (no push) are **re-confirmed** above with fresh citations. New:

| ID | Sev | Finding | Evidence | Exact fix |
|---|---|---|---|---|
| **WS11-F4** | **P1** | **The pilot APK on disk still declares `RECORD_AUDIO` and `SYSTEM_ALERT_WINDOW`.** WS11-F3 was fixed in *source* (`app.config.ts:66-69`, commit `9692bb3`, 2026-08-04 09:44) but the distributable artifact is dated 2026-08-03 15:49 and was built from a manifest that contained both (`.../packaged_manifests/release/…/AndroidManifest.xml:15-16`; blame `.../logs/manifest-merger-release-report.txt:175-182`). Any tester who inspects the app, or any store reviewer, sees a microphone + draw-over-apps request from a health app. | as cited | `npx expo prebuild -p android --clean && ./gradlew :app:assembleRelease --rerun-tasks`, then **verify the artifact**, not the source: `grep -c "RECORD_AUDIO\|SYSTEM_ALERT_WINDOW" android/app/build/intermediates/packaged_manifests/release/*/AndroidManifest.xml` must be `0`, plus `adb shell dumpsys package me.metocare.patient`. Better: configure `expo-image-picker` with `microphonePermission: false` (§6 row 4) so the permission is never contributed. |
| **WS11-F5** | **P1** (P0 for any store submission) | **No in-app account deletion or data export.** The backend endpoints exist and are complete (`backend/app/api/v1/routes/account.py:45,79`) but no mobile screen or API client reaches them; `git show --stat 0da0f06` touched zero mobile files; `mobile/app` has no settings/profile/account screen and `dashboard.tsx:77-123` has no such destination. **`0da0f06` does NOT satisfy the Play data-deletion policy or Apple Guideline 5.1.1(v).** | as cited | Add `mobile/app/(app)/account.tsx`: "Tải dữ liệu của tôi" → `GET /patients/{id}/export` (share/save the JSON) and "Xoá tài khoản" → typed confirmation → `DELETE /patients/{id}/account` → clear SecureStore → `router.replace('/(auth)/login')`. Add `mobile/src/api/account.ts`, a dashboard entry point, VN copy in `src/i18n/vi.ts`, and a jest test. |
| **WS11-F6** | **P1** | **Builds are not reproducible and versions are not monotonic.** The whole `mobile/android` tree is untracked (`mobile/.gitignore:13`; `git ls-files mobile/android` → 0), so `versionCode 1` / `versionName 1.0.0` / the signing config (`build.gradle:95-96,112-115`) exist only as regenerable build output. `eas.json:4` sets `appVersionSource: "remote"` while the local gradle pins `1` — two conflicting sources. Play rejects any upload with a non-increasing `versionCode`, and `adb install -r` refuses a same-or-lower-code downgrade, which breaks §5.2's rollback. | as cited | Move `android.versionCode` (and `ios.buildNumber`) into `app.config.ts` and bump them in the same commit as `version`; **or** commit to EAS remote versioning and build only via EAS. Either way, record `version / versionCode / commit / APK SHA-256 / API_BASE_URL` per distributed artifact. |
| **WS11-F7** | **P1** | **No update or hotfix path exists.** `expo-updates` is not a dependency; `app.config.ts` has no `updates`/`runtimeVersion`; the native manifest sets `expo.modules.updates.ENABLED=false` (`AndroidManifest.xml:16`); the `channel` values in `eas.json:10,17,30` are inert; there is no version-check or forced-upgrade call. A JS-only defect during a pilot can only be fixed by rebuilding and having every tester manually reinstall, and the fleet's build composition is unknowable because the app never reports its version. | as cited | Add `expo-updates` + `runtimeVersion: { policy: "appVersion" }` bound to the `staging` channel → `eas update --branch staging` for JS hotfixes. Send `X-App-Version`/`X-Build` from `mobile/src/api/client.ts` and log it. Add a minimum-supported-version gate. |
| **WS11-F8** | **P2** | **No app icon, adaptive icon, or splash asset.** `app.config.ts` declares none and `mobile/assets/` does not exist, so the build falls back to Expo's default launcher icon (`android/app/src/main/AndroidManifest.xml:15` `@mipmap/ic_launcher`). Testers see a generic icon; both stores require a real one. | as cited | Add `mobile/assets/{icon.png,adaptive-icon.png,splash.png}` and the corresponding `icon`/`android.adaptiveIcon`/`splash` keys. |
| **WS11-F9** | **P2** | **The build-time QA-fixture gate is inert.** `ANDROID-PILOT-RC.md:68` states the QA document-fixture entry is gated on `IS_NON_PRODUCTION` (build-time) **and** backend `qa_fixture_enabled`. But `AppEnv` has no `'production'` member (`app.config.ts:13`, `src/config/env.ts:9`), so `IS_NON_PRODUCTION` (`env.ts:32`) is `true` in **every** producible build. The only real gate is the backend flag (which does fail loud in prod, `config.py:300`) — the claimed defence-in-depth is one layer, not two. | as cited | Add `'production'` to `AppEnv`, a `production` env profile, and a `production` EAS build profile; then `IS_NON_PRODUCTION` becomes meaningful. Until then, correct the RC doc's claim. |
| **WS11-F10** | **P1** | **`mobile/.env.staging:4` commits a wrong, plausible-looking backend URL** — `https://metocare-staging.azurecontainerapps.io/api/v1`, which is not a valid ACA FQDN shape and contradicts `app.config.ts:17-18` (*"no azurecontainerapps.io host exists in the tree"*). Because `EXPO_PUBLIC_API_URL` outranks the deliberate `.invalid` placeholder (`app.config.ts:22,30`), anyone who sources this file gets a build that fails at DNS with no loud config-time signal — defeating the exact safeguard the placeholder was added for (R-03). | as cited | Delete the line (or replace it with the verified FQDN), and move the real value into `eas.json`'s `android-apk` profile `env` block so it is reviewed with the build config. Add a CI/pre-build assertion that the baked URL resolves and `GET /info` returns `env=staging`. |
| **WS11-F11** | **P2** | **iOS purpose strings would ship in English.** `expo-image-picker` is a dependency used for camera + library capture (`mobile/app/(app)/add-document.tsx:5,60-66`) but is not listed in `app.config.ts:71-80`, so its plugin defaults apply — `"Allow $(PRODUCT_NAME) to access your camera"` / `"…your photos"` (`node_modules/expo-image-picker/plugin/build/withImagePicker.js:7-9`). MetoCare's UI is Vietnamese-only; App Review rejects purpose strings that don't explain the concrete use in the user's language. (The same plugin is what injects `RECORD_AUDIO` — `:10-13`.) | as cited | Add the explicit plugin entry from §6 row 4. Verify after `npx expo prebuild -p ios` by reading the generated `ios/*/Info.plist`. |

---

## 10. Verdict

| Gate | Verdict |
|---|---|
| **Android internal pilot** | ✅ **READY after one rebuild.** §4 is the runbook. The rebuild is mandatory, not cosmetic — it is what closes WS11-F4 and bakes the correct staging URL (R-03/WS11-F10). |
| **Play internal testing** | 🔑🛠 **BLOCKED** — upload key + a store build profile + AAB + monotonic `versionCode` (WS11-F6) + icon (WS11-F8) + **in-app account deletion** (WS11-F5) + Data safety form (§6 row 6, itself blocked on the OCR-F1 cloud-processing decision). |
| **iOS TestFlight** | 🔑🛠 **BLOCKED** — Apple membership + signing, no iOS project ever generated, **no privacy manifest**, no `buildNumber`, empty `submit` config, English purpose strings (WS11-F11). |
| **App Store / Play production** | ⛔ **NOT-STARTED** — all of the above plus §6 rows 7, 9, 11. |
| **Reminders reaching patients** | ⛔ **Pull-only, fetch-on-mount.** Not a distribution blocker, but it invalidates any pilot metric framed as "adherence to reminders" (§8). |

---

## 11. Tracking deltas requested

- `TRACKING.md` §A WS11 → **🟡 ASSESSED — Android internal ready after rebuild; store channels blocked (5 P1 open)**.
- `TRACKING.md` §C: **R-03 → still open**, and add WS11-F10 as its concrete cause; §4/§3 supply the exact command and config change.
- `TRACKING.md` §H (Known Limitations): add *"no OTA/hotfix path — every client fix requires a manual reinstall"* (WS11-F7) and *"reminders are pull-only; the app cannot notify"* (§8).
- `15-FINAL-LAUNCH-REVIEW.md` §3: WS11-F3 must move from ✅/PLANNED to **partially fixed — source only, artifact stale** (WS11-F4); add WS11-F5 as a store-submission P0.
- `ANDROID-PILOT-RC.md`: §11's `IS_NON_PRODUCTION` claim (`:68`) is inert (WS11-F9); §1's "current artifact points at localhost" (`:14`) is superseded by §11's staging-URL build — reconcile the two.
