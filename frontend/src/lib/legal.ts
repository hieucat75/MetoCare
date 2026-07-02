import type { ConsentPayload } from '@/lib/api/auth'

/** Current legal document versions — keep in sync with backend app/core/legal.py. */
export const TERMS_VERSION = '1.0'
export const PRIVACY_VERSION = '1.0'
export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? '1.0.0'

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
export function buildConsentPayload(accepted: boolean): ConsentPayload {
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
  }
}
