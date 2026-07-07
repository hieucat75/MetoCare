/**
 * Safe display-name resolution for authenticated users.
 *
 * Guards against a backend row whose PHI decryption failed: a raw Fernet token
 * ("gAAAA…" base64) must never render in the UI (staging bug 2026-07-06 showed
 * one in the admin sidebar). Fallback chain:
 *   full_name → display_name → masked email → masked phone → role fallback.
 */

// Fernet ciphertext is URL-safe base64 starting with the version byte 0x80
// ("gAAAA"). Real names never match this shape.
const FERNET_TOKEN_RE = /^gAAAA[A-Za-z0-9_-]+={0,2}$/
const FERNET_MIN_LENGTH = 60

export interface DisplayNameSource {
  full_name?: string | null
  display_name?: string | null
  email?: string | null
  phone?: string | null
}

export function isCiphertextLike(value: string | null | undefined): boolean {
  return !!value && value.length >= FERNET_MIN_LENGTH && FERNET_TOKEN_RE.test(value)
}

/** "admin@metocare.vn" → "ad***@metocare.vn" (keeps enough to recognize). */
export function maskEmail(email: string): string {
  const [local, domain] = email.split('@')
  if (!domain) return email
  const visible = local.slice(0, 2)
  return `${visible}***@${domain}`
}

/** "+84912345678" → "+8491***678" */
export function maskPhone(phone: string): string {
  if (phone.length <= 7) return phone
  return `${phone.slice(0, 5)}***${phone.slice(-3)}`
}

function safeName(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  if (!trimmed || isCiphertextLike(trimmed)) return null
  return trimmed
}

export function getUserDisplayName(
  user: DisplayNameSource | null | undefined,
  fallback = 'Quản trị viên',
): string {
  if (!user) return fallback
  const name = safeName(user.full_name) ?? safeName(user.display_name)
  if (name) return name
  if (user.email) return maskEmail(user.email)
  if (user.phone) return maskPhone(user.phone)
  return fallback
}
