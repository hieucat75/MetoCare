/** Backend API contract types — mirrored from frontend/src/lib/api/auth.ts. */

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
  email: string | null
  phone: string | null
  role: UserRole
  full_name: string | null
  mfa_enabled: boolean
  notify_medication: boolean
  notify_lab_results: boolean
  notify_doctor_messages: boolean
  patient_profile_id?: string | null
  accepted_terms_version?: string | null
}

/** Consent payload accepted by /auth/register and /auth/accept-terms. */
export interface ConsentPayload {
  accepted: boolean
  terms_version: string
  privacy_version: string
  app_version?: string
  locale?: string
  timezone?: string
  device_platform?: string
  accepted_source?: string
  accepted_language?: string
}
