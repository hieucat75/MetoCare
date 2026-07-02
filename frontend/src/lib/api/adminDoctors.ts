import { api } from './client'
import type { DoctorVerificationStatus } from './marketplace'

// ── Admin doctor-verification DTOs ────────────────────────────────────────────

/** Admin view of a doctor for the verification queue (base `/api/v1/admin/doctors`). */
export interface DoctorVerificationOut {
  id: string
  user_id?: string | null
  full_name: string
  specialty?: string | null
  license_no?: string | null
  hospital_name?: string | null
  years_experience?: number | null
  verification_status: DoctorVerificationStatus
  is_verified: boolean
  is_active: boolean
}

// ── Typed functions (ADMIN, MFA) ──────────────────────────────────────────────

/** List doctors for the verification queue, optionally filtered by status. */
export async function listDoctorsForVerification(
  status?: DoctorVerificationStatus,
): Promise<DoctorVerificationOut[]> {
  const qs = new URLSearchParams()
  if (status) qs.set('status', status)
  const query = qs.toString()
  return api.get<DoctorVerificationOut[]>(`/admin/doctors${query ? `?${query}` : ''}`)
}

/** Approve a doctor's verification (409 if not in a verifiable state). */
export async function verifyDoctor(id: string): Promise<DoctorVerificationOut> {
  return api.post<DoctorVerificationOut>(`/admin/doctors/${id}/verify`, {})
}

/** Reject a doctor's verification. */
export async function rejectDoctor(id: string): Promise<DoctorVerificationOut> {
  return api.post<DoctorVerificationOut>(`/admin/doctors/${id}/reject`, {})
}

/** Suspend a verified doctor (removes them from the patient marketplace). */
export async function suspendDoctor(id: string): Promise<DoctorVerificationOut> {
  return api.post<DoctorVerificationOut>(`/admin/doctors/${id}/suspend`, {})
}
