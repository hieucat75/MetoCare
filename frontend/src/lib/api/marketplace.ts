import { api } from './client'

// ── Enums (exact backend string values) ───────────────────────────────────────

export type ConsultationStatus =
  | 'REQUESTED'
  | 'CONFIRMED'
  | 'PAID'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'CANCELLED'

export type ConsultationType = 'CHAT' | 'VIDEO' | 'IN_PERSON'

export type PaymentStatus = 'UNPAID' | 'PAID' | 'REFUNDED' | 'FAILED'

export type DoctorVerificationStatus =
  | 'PENDING_VERIFICATION'
  | 'VERIFIED'
  | 'SUSPENDED'
  | 'REJECTED'

/** Rendered on booking + consultation + doctor detail screens (VN). */
export const MARKETPLACE_DISCLAIMER =
  'MetoCare không thay thế cấp cứu hoặc khám trực tiếp khi có dấu hiệu nguy hiểm.'

// ── Marketplace DTOs ──────────────────────────────────────────────────────────

export interface DoctorCardOut {
  id: string
  full_name: string
  specialty?: string | null
  avatar_url?: string | null
  consultation_fee?: number | null
  hospital_name?: string | null
  years_experience?: number | null
  languages?: string | null
  consultation_methods?: string | null
  rating_avg: number
  rating_count: number
}

export interface DoctorDetailOut extends DoctorCardOut {
  bio?: string | null
  next_available?: string | null
  disclaimer?: string | null
}

export interface BrowseDoctorsFilters {
  specialty?: string
  name?: string
  min_price?: number
  max_price?: number
  method?: string
}

// ── Typed functions ───────────────────────────────────────────────────────────

/** Browse VERIFIED doctors in the marketplace (PATIENT, no MFA). */
export async function browseDoctors(
  filters: BrowseDoctorsFilters = {},
): Promise<DoctorCardOut[]> {
  const qs = new URLSearchParams()
  if (filters.specialty) qs.set('specialty', filters.specialty)
  if (filters.name) qs.set('name', filters.name)
  if (filters.min_price != null) qs.set('min_price', String(filters.min_price))
  if (filters.max_price != null) qs.set('max_price', String(filters.max_price))
  if (filters.method) qs.set('method', filters.method)
  const query = qs.toString()
  return api.get<DoctorCardOut[]>(`/marketplace/doctors${query ? `?${query}` : ''}`)
}

/** Fetch a single verified doctor's public detail (404 if not found / not verified). */
export async function getDoctorDetail(id: string): Promise<DoctorDetailOut> {
  return api.get<DoctorDetailOut>(`/marketplace/doctors/${id}`)
}
