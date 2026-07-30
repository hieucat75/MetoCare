import type { ExpoConfig, ConfigContext } from 'expo/config'

/**
 * Dynamic Expo config with dev/staging environment profiles.
 *
 * The active profile is selected via `APP_ENV` (development | staging),
 * defaulting to `development`. Public runtime values are surfaced through
 * `expo-constants` (`Constants.expoConfig.extra`) AND mirrored to
 * `EXPO_PUBLIC_API_URL` so both `expo-constants` and `process.env` reads
 * resolve the same base URL. Never put secrets here — this file is bundled.
 */

type AppEnv = 'development' | 'staging'

const APP_ENV = (process.env.APP_ENV as AppEnv) ?? 'development'

// The real staging backend FQDN is an Azure/CI deploy value and is NOT committed
// to this repo (verified: no azurecontainerapps.io host exists in the tree).
// Staging builds MUST inject EXPO_PUBLIC_API_URL. This placeholder uses the
// reserved `.invalid` TLD so a mis-configured staging build fails loudly instead
// of silently pointing at a plausible-but-wrong host. (Review P1 fix.)
const STAGING_API_PLACEHOLDER = 'https://staging.metocare.invalid/api/v1'

const API_URL_BY_ENV: Record<AppEnv, string> = {
  development: 'http://localhost:8000/api/v1',
  staging: STAGING_API_PLACEHOLDER,
}

// EXPO_PUBLIC_API_URL (if provided) always wins so CI/EAS can override.
const apiUrl = process.env.EXPO_PUBLIC_API_URL ?? API_URL_BY_ENV[APP_ENV]

if (APP_ENV === 'staging' && !process.env.EXPO_PUBLIC_API_URL) {
  // eslint-disable-next-line no-console
  console.warn(
    '[config] APP_ENV=staging without EXPO_PUBLIC_API_URL — using a non-resolving ' +
      'placeholder host. Inject the real staging FQDN via EXPO_PUBLIC_API_URL.'
  )
}

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: APP_ENV === 'staging' ? 'MetoCare (Staging)' : 'MetoCare',
  slug: 'metocare-mobile',
  version: '1.0.0',
  orientation: 'portrait',
  scheme: 'metocare',
  userInterfaceStyle: 'automatic',
  ios: {
    supportsTablet: false,
    bundleIdentifier:
      APP_ENV === 'staging' ? 'me.metocare.patient.staging' : 'me.metocare.patient',
    // App uses only standard/exempt encryption (HTTPS) — declares export-compliance
    // so App Store Connect doesn't block test distribution.
    infoPlist: {
      ITSAppUsesNonExemptEncryption: false,
    },
  },
  android: {
    package:
      APP_ENV === 'staging' ? 'me.metocare.patient.staging' : 'me.metocare.patient',
  },
  plugins: [
    'expo-router',
    'expo-secure-store',
    [
      'expo-local-authentication',
      {
        faceIDPermission: 'Cho phép MetoCare dùng Face ID để mở khoá ứng dụng.',
      },
    ],
  ],
  extra: {
    appEnv: APP_ENV,
    apiUrl,
    eas: {
      // Linked EAS project (created via `eas init`). Not a secret. Overridable
      // per-environment via EAS_PROJECT_ID.
      projectId: process.env.EAS_PROJECT_ID ?? '7ba4d27e-9170-4b62-a3ae-a4f16575a889',
    },
  },
})
