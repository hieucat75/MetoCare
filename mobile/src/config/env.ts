import Constants from 'expo-constants'

/**
 * Resolves runtime configuration from expo-constants `extra` (populated by
 * app.config.ts per environment profile), falling back to EXPO_PUBLIC_* env
 * vars, then a localhost default. Single source of truth for the API base URL.
 */

type AppEnv = 'development' | 'staging'

interface Extra {
  appEnv?: AppEnv
  apiUrl?: string
}

const extra = (Constants.expoConfig?.extra ?? {}) as Extra

const DEFAULT_API_URL = 'http://localhost:8000/api/v1'

export const API_BASE_URL: string =
  extra.apiUrl ?? process.env.EXPO_PUBLIC_API_URL ?? DEFAULT_API_URL

export const APP_ENV: AppEnv = extra.appEnv ?? 'development'

export const IS_STAGING = APP_ENV === 'staging'

/**
 * True on non-production (development OR staging) builds. Gates dev/staging-only
 * affordances such as the QA fixture ingestion entry so they never render in a
 * production build.
 */
export const IS_NON_PRODUCTION: boolean = APP_ENV === 'development' || APP_ENV === 'staging'
