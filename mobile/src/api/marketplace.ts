import type { ApiClient } from './client'

/**
 * Doctor Marketplace (Journey 5) API — authenticated browse/detail of VERIFIED
 * doctors (backend requires a logged-in user; not a public/anonymous endpoint).
 * Mirrors the backend contract in backend/app/api/v1/routes/marketplace.py and
 * the response schemas in backend/app/schemas/marketplace.py.
 *
 * Read-only: patients browse doctors here, then book via the consultations API.
 */

export interface DoctorCardOut {
  id: string
  full_name: string
  specialty: string | null
  avatar_url: string | null
  consultation_fee: number | null
  hospital_name: string | null
  years_experience: number | null
  languages: string | null
  consultation_methods: string | null
  rating_avg: number
  rating_count: number
}

export interface DoctorDetailOut extends DoctorCardOut {
  bio: string | null
  next_available: string | null
  disclaimer: string | null
}

export interface DoctorListFilters {
  specialty?: string
  name?: string
  min_price?: number
  max_price?: number
  method?: string
}

/**
 * Build a `?a=b&c=d` query string from the (all-optional) filter set. Empty /
 * undefined values are omitted so the backend applies no filter for them.
 * Built manually (not URLSearchParams) for deterministic ordering in tests and
 * to avoid RN URL-polyfill quirks.
 */
export function buildDoctorQuery(filters: DoctorListFilters = {}): string {
  const parts: string[] = []
  const add = (key: string, value: string | number): void => {
    parts.push(`${key}=${encodeURIComponent(String(value))}`)
  }
  if (filters.specialty) add('specialty', filters.specialty)
  if (filters.name) add('name', filters.name)
  if (filters.min_price != null) add('min_price', filters.min_price)
  if (filters.max_price != null) add('max_price', filters.max_price)
  if (filters.method) add('method', filters.method)
  return parts.length ? `?${parts.join('&')}` : ''
}

export function listDoctors(
  client: ApiClient,
  filters: DoctorListFilters = {}
): Promise<DoctorCardOut[]> {
  return client.get<DoctorCardOut[]>(`/marketplace/doctors${buildDoctorQuery(filters)}`)
}

export function getDoctor(client: ApiClient, doctorId: string): Promise<DoctorDetailOut> {
  return client.get<DoctorDetailOut>(`/marketplace/doctors/${doctorId}`)
}
