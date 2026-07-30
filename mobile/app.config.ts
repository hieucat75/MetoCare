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

const API_URL_BY_ENV: Record<AppEnv, string> = {
  development: 'http://localhost:8000/api/v1',
  staging: 'https://metocare-staging.azurecontainerapps.io/api/v1',
}

// EXPO_PUBLIC_API_URL (if provided) always wins so CI/EAS can override.
const apiUrl = process.env.EXPO_PUBLIC_API_URL ?? API_URL_BY_ENV[APP_ENV]

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
