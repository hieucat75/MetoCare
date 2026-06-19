import { api, setTokens, clearTokens } from './client'

export type UserRole =
  | 'patient'
  | 'doctor'
  | 'medical_reviewer'
  | 'internal_admin'
  | 'super_admin'
  | 'ai_service'
  | 'clinic_admin'

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  role: UserRole
  user_id: string
  mfa: boolean
}

export interface UserResponse {
  id: string
  email: string
  role: UserRole
  full_name: string | null
  mfa_enabled: boolean
  patient_profile_id?: string | null
}

export interface MfaEnrollResponse {
  secret: string
  provisioning_uri: string
  backup_codes: string[]
}

export async function login(
  email: string,
  password: string,
  totpCode?: string,
): Promise<TokenResponse> {
  const body: Record<string, string> = { email, password }
  if (totpCode) body.totp_code = totpCode
  const res = await api.post<TokenResponse>('/auth/login', body, { skipAuth: true })
  setTokens(res.access_token, res.refresh_token)
  return res
}

export async function register(
  email: string,
  password: string,
  fullName?: string,
): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>(
    '/auth/register',
    { email, password, full_name: fullName },
    { skipAuth: true },
  )
  setTokens(res.access_token, res.refresh_token)
  return res
}

// ── Phone-first auth (Pilot V1) ───────────────────────────────────────────────
//
// PX-02 override: patients authenticate with PHONE + PASSWORD only — no OTP, no
// email-first registration, no passwordless flow. The backend `/auth/register`
// and `/auth/login` still require an `email` (EmailStr) field, and we are not
// changing the backend. So we derive a DETERMINISTIC placeholder email from the
// normalized phone number: the same phone always maps to the same account.
//
//   0901234567  ->  0901234567@phone.metocare.vn
//
// IMPORTANT: the domain MUST pass Pydantic `EmailStr` validation. Reserved /
// special-use TLDs (`.local`, `.localhost`, `.invalid`, `.test`, `.example`) are
// REJECTED by email-validator and would 422 every register/login. We use a
// subdomain of the org domain `metocare.vn`, which validates (deliverability is
// disabled in Pydantic EmailStr, so no DNS lookup is performed).
//
// The real phone is also stored on the PatientProfile during onboarding so it
// can be displayed and edited. This scheme is documented in AGENTS.md.

export const PHONE_EMAIL_DOMAIN = 'phone.metocare.vn'

/**
 * Normalize a Vietnamese phone number to a canonical `0XXXXXXXXX` form so the
 * same subscriber always maps to the same placeholder email. Handles the
 * `+84`, `+84 (0)`, and bare local formats:
 *   84901234567  -> 0901234567
 *   840901234567 -> 0901234567   (trunk 0 after +84)
 *   0901234567   -> 0901234567
 */
export function normalizeVietnamPhone(raw: string): string {
  let d = raw.replace(/\D/g, '')
  // Only treat a leading 84 as the country code in international form (84 + a
  // 9–10 digit subscriber number). A local number like 0841234567 never reaches
  // this branch (it starts with 0), so it is preserved.
  if (d.startsWith('84') && d.length >= 11) d = d.slice(2)
  d = d.replace(/^0+/, '') // collapse leading zero(s) to a single canonical one
  if (d) d = '0' + d
  return d
}

/** Map a phone number to its deterministic placeholder email. */
export function phoneToPlaceholderEmail(phone: string): string {
  return `${normalizeVietnamPhone(phone)}@${PHONE_EMAIL_DOMAIN}`
}

/** A login identifier is treated as an email if it contains '@' (staff), else a phone. */
export function identifierToEmail(identifier: string): string {
  return identifier.includes('@') ? identifier.trim() : phoneToPlaceholderEmail(identifier)
}

/**
 * Recover the phone number from a patient placeholder email, or '' for a real
 * (staff) email. Used to display the phone instead of the synthetic address.
 */
export function phoneFromPlaceholderEmail(email: string | null | undefined): string {
  if (!email) return ''
  const [local, domain] = email.split('@')
  return domain === PHONE_EMAIL_DOMAIN ? local : ''
}

/** Human-facing contact: the patient's phone if known, else a recovered/real email. */
export function displayContact(
  email: string | null | undefined,
  phone?: string | null,
): string {
  return phone || phoneFromPlaceholderEmail(email) || email || ''
}

/** Register a patient with phone + password (placeholder email derived internally). */
export async function registerWithPhone(
  phone: string,
  password: string,
  fullName?: string,
): Promise<TokenResponse> {
  return register(phoneToPlaceholderEmail(phone), password, fullName)
}

/** Log in with a phone number (or, for staff, an email) + password. */
export async function loginWithIdentifier(
  identifier: string,
  password: string,
  totpCode?: string,
): Promise<TokenResponse> {
  return login(identifierToEmail(identifier), password, totpCode)
}

export async function logout(refreshToken: string): Promise<void> {
  try {
    await api.post('/auth/logout', { refresh_token: refreshToken })
  } finally {
    clearTokens()
  }
}

export async function me(): Promise<UserResponse> {
  return api.get<UserResponse>('/auth/me')
}

export async function mfaEnroll(): Promise<MfaEnrollResponse> {
  return api.post<MfaEnrollResponse>('/auth/mfa/enroll', {})
}

export async function mfaVerify(totpCode: string): Promise<{ message: string }> {
  return api.post<{ message: string }>('/auth/mfa/verify', { totp_code: totpCode })
}

export function getRoleHomePath(role: UserRole): string {
  switch (role) {
    case 'doctor':
    case 'medical_reviewer':
      return '/doctor/dashboard'
    case 'internal_admin':
    case 'super_admin':
    case 'clinic_admin':
      return '/admin/dashboard'
    case 'patient':
      return '/dashboard'
    case 'ai_service':
      // ai_service is non-interactive; should never authenticate via UI
      return '/login'
  }
}
