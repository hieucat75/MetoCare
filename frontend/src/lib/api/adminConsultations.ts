import { api } from './client'
import type { ConsultationStatus } from './marketplace'

// ── Admin consultation monitoring DTOs ────────────────────────────────────────

/** One row in the admin consultation-monitoring list. */
export interface AdminConsultation {
  id: string
  patient_id: string
  patient_name: string | null
  doctor_id: string
  doctor_name: string
  status: ConsultationStatus
  consultation_type: string
  consultation_price: number
  payment_status: string | null
  created_at: string | null
}

/** Aggregate consultation KPIs for the admin overview. */
export interface AdminConsultationStats {
  by_status: Record<string, number>
  total: number
  paid_count: number
  mock_revenue: number
}

export interface AdminConsultationFilters {
  status?: ConsultationStatus | ''
  doctorId?: string
  patientId?: string
  dateFrom?: string
  dateTo?: string
  limit?: number
  offset?: number
}

// ── Typed functions (ADMIN, MFA) ──────────────────────────────────────────────

/** List consultations for admin monitoring (filtered, newest first). */
export async function listAdminConsultations(
  filters: AdminConsultationFilters = {}
): Promise<AdminConsultation[]> {
  const qs = new URLSearchParams()
  if (filters.status) qs.set('status', filters.status)
  if (filters.doctorId) qs.set('doctor_id', filters.doctorId)
  if (filters.patientId) qs.set('patient_id', filters.patientId)
  if (filters.dateFrom) qs.set('date_from', filters.dateFrom)
  if (filters.dateTo) qs.set('date_to', filters.dateTo)
  if (filters.limit != null) qs.set('limit', String(filters.limit))
  if (filters.offset != null) qs.set('offset', String(filters.offset))
  const query = qs.toString()
  return api.get<AdminConsultation[]>(`/admin/consultations${query ? `?${query}` : ''}`)
}

/** Fetch aggregate consultation KPIs (by-status counts, total, paid, mock revenue). */
export async function getAdminConsultationStats(): Promise<AdminConsultationStats> {
  return api.get<AdminConsultationStats>('/admin/consultations/stats')
}
