import type { ConsentPayload } from '@/lib/api/auth'

/**
 * Current legal document versions.
 *
 * Canonical source: repo-root `legal-versions.json`. The frontend Docker build
 * context is `./frontend` only, so that file can't be imported here at build
 * time — these literals mirror it and `legalVersions.sync.test.ts` fails if they
 * ever diverge from the canonical JSON.
 */
export const TERMS_VERSION = '1.0'
export const PRIVACY_VERSION = '1.0'
export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? '1.0.0'

/** Where an acceptance came from (audit trail). */
export type ConsentSource = 'registration' | 'reconsent'

/**
 * True when the user must (re-)accept the Terms. Versions increase
 * monotonically, so a missing or non-current accepted version is outdated.
 */
export function isTermsOutdated(acceptedTermsVersion: string | null | undefined): boolean {
  if (!acceptedTermsVersion) return true
  return acceptedTermsVersion !== TERMS_VERSION
}

/** Summary bullets shown on the consent screen (not the full legal text). */
export const CONSENT_SUMMARY: readonly string[] = [
  'MetoCare sẽ lưu trữ hồ sơ sức khỏe của bạn.',
  'AI được phép phân tích dữ liệu sức khỏe nhằm hỗ trợ bạn theo dõi và quản lý sức khỏe.',
  'Khi bạn chủ động liên kết bác sĩ, bác sĩ sẽ được xem hồ sơ của bạn để phục vụ việc chăm sóc.',
  'Bạn có thể ngừng sử dụng hoặc chấm dứt liên kết với bác sĩ bất cứ lúc nào.',
  'AI chỉ hỗ trợ tham khảo và không thay thế chẩn đoán hoặc điều trị của bác sĩ.',
] as const

/**
 * Build the consent payload from the current versions + best-effort client
 * context (locale, timezone, platform). Safe to call on the client only.
 */
export function buildConsentPayload(
  accepted: boolean,
  source: ConsentSource = 'registration',
): ConsentPayload {
  let locale: string | undefined
  let timezone: string | undefined
  try {
    locale = typeof navigator !== 'undefined' ? navigator.language : undefined
    timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  } catch {
    // Intl / navigator unavailable — leave undefined.
  }
  return {
    accepted,
    terms_version: TERMS_VERSION,
    privacy_version: PRIVACY_VERSION,
    app_version: APP_VERSION,
    locale,
    timezone,
    device_platform: 'web',
    accepted_source: source,
    accepted_language: locale ?? 'vi',
  }
}
