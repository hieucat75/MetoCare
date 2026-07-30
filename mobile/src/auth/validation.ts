import { vi } from '../i18n/vi'

/**
 * Client-side field validation for the email/password auth forms. Mirrors the
 * backend's relaxed build-phase policy: email required + shape check, password
 * min 6 chars, no complexity requirement.
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
export const MIN_PASSWORD_LENGTH = 6

export function validateEmail(email: string): string | null {
  const value = email.trim()
  if (!value) return vi.errors.emailRequired
  if (!EMAIL_RE.test(value)) return vi.errors.emailInvalid
  return null
}

export function validatePassword(password: string): string | null {
  if (!password) return vi.errors.passwordRequired
  if (password.length < MIN_PASSWORD_LENGTH) return vi.errors.passwordTooShort
  return null
}

export interface FieldErrors {
  email?: string
  password?: string
}

export function validateCredentials(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {}
  const e = validateEmail(email)
  const p = validatePassword(password)
  if (e) errors.email = e
  if (p) errors.password = p
  return errors
}

export function hasErrors(errors: FieldErrors): boolean {
  return Boolean(errors.email || errors.password)
}
