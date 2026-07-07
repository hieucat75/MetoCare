import { api } from './client'

// ── Review Queue ──────────────────────────────────────────────────────────────

export type ReviewItemType = 'lab_result' | 'ai_session' | 'care_plan'
export type ReviewPriority = 'urgent' | 'high' | 'normal' | 'low'
export type ReviewStatus = 'pending_review' | 'in_review' | 'approved' | 'rejected' | 'request_info'

export interface QueueItem {
  id: string
  patient_id: string
  patient_name: string | null
  item_type: ReviewItemType
  priority: ReviewPriority
  status: ReviewStatus
  summary: string | null
  submitted_at: string
  assigned_doctor_id: string | null
}

export interface QueueResponse {
  total: number
  pending_count: number
  items: QueueItem[]
}

export async function getReviewQueue(params?: {
  status?: ReviewStatus
  priority?: ReviewPriority
  item_type?: ReviewItemType
  limit?: number
  offset?: number
}): Promise<QueueResponse> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.priority) qs.set('priority', params.priority)
  if (params?.item_type) qs.set('item_type', params.item_type)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<QueueResponse>(`/doctor/queue${query ? `?${query}` : ''}`)
}

export interface ReviewDecisionPayload {
  decision: 'approved' | 'rejected' | 'request_info'
  comment: string
  internal_note?: string
}

export async function submitReviewDecision(
  itemId: string,
  payload: ReviewDecisionPayload,
): Promise<QueueItem> {
  return api.patch<QueueItem>(`/doctor/queue/${itemId}/review`, payload)
}

// ── Patient List ──────────────────────────────────────────────────────────────

export interface DoctorPatient {
  id: string
  full_name: string | null
  email: string
  risk_segment: 'low' | 'medium' | 'high' | 'very_high' | null
  last_metric_at: string | null
  pending_labs: number
  active_care_plans: number
  consented: boolean
}

export interface DoctorPatientListResponse {
  total: number
  items: DoctorPatient[]
}

/**
 * Server-side risk filter. `high` includes `very_high` on the backend.
 */
export type DoctorPatientRiskFilter = 'low' | 'medium' | 'high'

/**
 * Server-side sort key. Default (when omitted) is `risk`.
 */
export type DoctorPatientSort = 'risk' | 'last_activity' | 'pending' | 'name'

export async function getDoctorPatients(params?: {
  limit?: number
  offset?: number
  search?: string
  risk?: DoctorPatientRiskFilter
  sort?: DoctorPatientSort
}): Promise<DoctorPatientListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  if (params?.search) qs.set('search', params.search)
  if (params?.risk) qs.set('risk', params.risk)
  if (params?.sort) qs.set('sort', params.sort)
  const query = qs.toString()
  return api.get<DoctorPatientListResponse>(`/doctor/patients${query ? `?${query}` : ''}`)
}

// ── Patient Timeline ──────────────────────────────────────────────────────────

export type TimelineEventType =
  | 'lab_uploaded'
  | 'lab_approved'
  | 'metric_logged'
  | 'care_plan_created'
  | 'care_plan_approved'
  | 'ai_session'
  | 'consent_granted'
  | 'consent_revoked'

export interface TimelineEvent {
  id: string
  event_type: TimelineEventType
  description: string
  occurred_at: string
  actor: string | null
  metadata: Record<string, unknown> | null
}

export async function getPatientTimeline(
  patientId: string,
  params?: { limit?: number },
): Promise<TimelineEvent[]> {
  const qs = params?.limit ? `?limit=${params.limit}` : ''
  return api.get<TimelineEvent[]>(`/doctor/patients/${patientId}/timeline${qs}`)
}

// ── Doctor Stats ──────────────────────────────────────────────────────────────

export interface DoctorStats {
  pending_reviews: number
  urgent_reviews: number
  total_patients: number
  reviews_today: number
  avg_review_time_min: number | null
}

export async function getDoctorStats(): Promise<DoctorStats> {
  return api.get<DoctorStats>('/doctor/stats')
}

// ── Appointments ──────────────────────────────────────────────────────────────

export type AppointmentStatus = 'pending' | 'confirmed' | 'cancelled' | 'completed'

export interface DoctorAppointment {
  id: string
  patient_id: string
  patient_name: string | null
  slot_start: string
  slot_end: string
  status: AppointmentStatus
  notes: string | null
  created_at: string
  updated_at: string
}

export interface DoctorAppointmentStats {
  today: number
  upcoming: number
  pending_confirmation: number
  completed: number
}

export interface DoctorAppointmentListResponse {
  total: number
  stats: DoctorAppointmentStats
  items: DoctorAppointment[]
}

export async function getDoctorAppointments(params?: {
  status?: AppointmentStatus[]
  search?: string
  dateFrom?: string
  dateTo?: string
  limit?: number
  offset?: number
}): Promise<DoctorAppointmentListResponse> {
  const qs = new URLSearchParams()
  params?.status?.forEach((s) => qs.append('status', s))
  if (params?.search) qs.set('search', params.search)
  if (params?.dateFrom) qs.set('date_from', params.dateFrom)
  if (params?.dateTo) qs.set('date_to', params.dateTo)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<DoctorAppointmentListResponse>(`/doctor/appointments${query ? `?${query}` : ''}`)
}

/**
 * Reuses the existing booking state-machine endpoint (PATCH /appointments/{id})
 * rather than duplicating confirm/cancel/complete transition logic.
 */
export async function updateAppointmentStatus(
  appointmentId: string,
  status: AppointmentStatus,
): Promise<{ id: string; status: AppointmentStatus }> {
  return api.patch<{ id: string; status: AppointmentStatus }>(`/appointments/${appointmentId}`, {
    status,
  })
}

// ── Clinical Notes (doctor-wide) ────────────────────────────────────────────

export type DoctorNoteStatus = 'draft' | 'finalized'

export interface DoctorNoteListItem {
  id: string
  consultation_id: string
  patient_id: string
  patient_name: string | null
  note_type: string
  status: DoctorNoteStatus
  content_preview: string
  created_at: string
  finalized_at: string | null
}

export interface DoctorNoteListResponse {
  total: number
  items: DoctorNoteListItem[]
}

export async function getDoctorNotes(params?: {
  consultationId?: string
  status?: DoctorNoteStatus
  limit?: number
  offset?: number
}): Promise<DoctorNoteListResponse> {
  const qs = new URLSearchParams()
  if (params?.consultationId) qs.set('consultation_id', params.consultationId)
  if (params?.status) qs.set('status', params.status)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<DoctorNoteListResponse>(`/doctor/notes${query ? `?${query}` : ''}`)
}
