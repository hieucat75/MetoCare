import { api } from './client'
import type { DoctorVerificationStatus } from './marketplace'

// ── DTOs ──────────────────────────────────────────────────────────────────────

/** The doctor's own profile including marketplace + verification fields. */
export interface DoctorProfileOut {
  id: string
  user_id?: string | null
  full_name: string
  specialty?: string | null
  license_no?: string | null
  bio?: string | null
  avatar_url?: string | null
  consultation_fee?: number | null
  is_verified: boolean
  is_active: boolean
  clinic_id?: string | null
  verification_status: DoctorVerificationStatus
  years_experience?: number | null
  languages?: string | null
  hospital_name?: string | null
  consultation_methods?: string | null
  rating_avg: number
  rating_count: number
}

/**
 * Editable marketplace fields. license_no / clinic_id are admin-only and
 * intentionally omitted. consultation_fee >= 0; years_experience 0..80;
 * languages / hospital_name / consultation_methods <= 255 chars.
 */
export interface DoctorMarketplaceUpdate {
  full_name?: string
  bio?: string
  avatar_url?: string
  consultation_fee?: number
  specialty?: string
  years_experience?: number
  languages?: string
  hospital_name?: string
  consultation_methods?: string
}

// ── Typed functions (DOCTOR, MFA) ─────────────────────────────────────────────

/** Fetch the caller's own doctor profile. */
export async function getMyDoctorProfile(): Promise<DoctorProfileOut> {
  return api.get<DoctorProfileOut>('/doctors/me')
}

/** Patch the caller's marketplace profile fields. */
export async function updateMarketplaceProfile(
  body: DoctorMarketplaceUpdate
): Promise<DoctorProfileOut> {
  return api.patch<DoctorProfileOut>('/doctors/me/marketplace', body)
}

/** Submit the profile for admin verification (PENDING_VERIFICATION). */
export async function submitForVerification(): Promise<DoctorProfileOut> {
  return api.post<DoctorProfileOut>('/doctors/me/submit-verification', {})
}
