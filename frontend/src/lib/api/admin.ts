import { api } from './client'

// ── Platform Stats ─────────────────────────────────────────────────────────────

export interface AdminStats {
  total_users: number
  active_patients: number
  active_doctors: number
  total_clinics: number
  ai_sessions_today: number
  pending_reviews: number
  flagged_ai_sessions: number
  audit_events_today: number
}

export async function getAdminStats(): Promise<AdminStats> {
  return api.get<AdminStats>('/admin/stats')
}

// ── Users ─────────────────────────────────────────────────────────────────────

export type AdminUserRole = 'patient' | 'doctor' | 'medical_reviewer' | 'internal_admin' | 'super_admin' | 'clinic_admin' | 'ai_service'

export interface AdminUser {
  id: string
  // Patients register by phone, so email can be null (one of email/phone set).
  email: string | null
  phone?: string | null
  full_name: string | null
  role: AdminUserRole
  is_active: boolean
  mfa_enabled: boolean
  created_at: string
}

export interface AdminUserListResponse {
  total: number
  items: AdminUser[]
}

/**
 * Backend GET /admin/users returns a plain array and supports skip/limit/role
 * only — `search` is filtered client-side over the fetched page.
 */
export async function getUsers(params?: {
  role?: AdminUserRole
  search?: string
  limit?: number
  offset?: number
}): Promise<AdminUserListResponse> {
  const qs = new URLSearchParams()
  if (params?.role) qs.set('role', params.role)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('skip', String(params.offset))
  const query = qs.toString()
  const users = await api.get<AdminUser[]>(`/admin/users${query ? `?${query}` : ''}`)
  const q = params?.search?.trim().toLowerCase()
  const items = q
    ? users.filter(
        (u) =>
          (u.email ?? '').toLowerCase().includes(q) ||
          (u.phone ?? '').toLowerCase().includes(q) ||
          (u.full_name ?? '').toLowerCase().includes(q),
      )
    : users
  return { total: items.length, items }
}

export async function toggleUserActive(userId: string, isActive: boolean): Promise<AdminUser> {
  return api.patch<AdminUser>(`/admin/users/${userId}`, { is_active: isActive })
}

// ── Patients ──────────────────────────────────────────────────────────────────

export interface AdminPatientListItem {
  id: string
  user_id: string
  full_name: string | null
  phone: string | null
  gender: string | null
  birth_year: number | null
  age: number | null
  is_active: boolean
  lab_result_count: number
  medication_count: number
  has_data_quality_flag: boolean
  consent_status: 'valid' | 'revoked' | 'none'
  created_at: string | null
  last_activity_at: string | null
}

export interface AdminPatientListResponse {
  total: number
  items: AdminPatientListItem[]
}

export interface AdminPatientConsultation {
  id: string
  doctor_id: string
  doctor_name: string | null
  clinic_name: string | null
  status: string
  created_at: string | null
}

export interface AdminPatientConsent {
  terms_version: string
  privacy_version: string
  accepted_at: string
  revoked_at: string | null
}

export interface AdminPatientAuditEntry {
  id: string
  action: string
  resource_type: string
  outcome: string
  timestamp: string
}

export interface AdminPatientDetail {
  id: string
  user_id: string
  email: string | null
  full_name: string | null
  phone: string | null
  dob: string | null
  age: number | null
  gender: string | null
  address: string | null
  height_cm: number | null
  weight_kg: number | null
  waist_cm: number | null
  risk_segment: string | null
  known_conditions: string | null
  allergies: string | null
  family_history: string | null
  lifestyle_profile: string | null
  is_active: boolean
  created_at: string | null
  last_activity_at: string | null
  consent_status: 'valid' | 'revoked' | 'none'
  consent: AdminPatientConsent | null
  consultations: AdminPatientConsultation[]
  audit_log: AdminPatientAuditEntry[]
  summary: Record<string, unknown>
}

export interface AdminPatientListParams {
  search?: string
  status?: 'active' | 'inactive'
  gender?: string
  hasLabs?: boolean
  hasMeds?: boolean
  hasConsent?: boolean
  createdFrom?: string
  createdTo?: string
  ageGroup?: string
  sort?: string
  limit?: number
  offset?: number
}

/**
 * Backend GET /admin/patients performs real server-side search/filter and
 * pagination over the full dataset (unlike getUsers above, which is limited
 * to client-side filtering of one fetched page).
 */
export async function getPatients(
  params?: AdminPatientListParams,
): Promise<AdminPatientListResponse> {
  const qs = new URLSearchParams()
  if (params?.search) qs.set('search', params.search)
  if (params?.status) qs.set('status', params.status)
  if (params?.gender) qs.set('gender', params.gender)
  if (params?.hasLabs != null) qs.set('has_labs', String(params.hasLabs))
  if (params?.hasMeds != null) qs.set('has_meds', String(params.hasMeds))
  if (params?.hasConsent != null) qs.set('has_consent', String(params.hasConsent))
  if (params?.createdFrom) qs.set('created_from', params.createdFrom)
  if (params?.createdTo) qs.set('created_to', params.createdTo)
  if (params?.ageGroup) qs.set('age_group', params.ageGroup)
  if (params?.sort) qs.set('sort', params.sort)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('skip', String(params.offset))
  const query = qs.toString()
  return api.get<AdminPatientListResponse>(`/admin/patients${query ? `?${query}` : ''}`)
}

export async function getPatientDetail(patientId: string): Promise<AdminPatientDetail> {
  return api.get<AdminPatientDetail>(`/admin/patients/${patientId}`)
}

export async function updatePatientStatus(
  patientId: string,
  isActive: boolean,
): Promise<AdminPatientListItem> {
  return api.patch<AdminPatientListItem>(`/admin/patients/${patientId}/status`, {
    is_active: isActive,
  })
}

/** Uses the generic admin notification endpoint (POST /notifications). */
export async function requestPatientProfileUpdate(
  userId: string,
  message?: string,
): Promise<void> {
  await api.post('/notifications', {
    user_id: userId,
    type: 'profile_update_requested',
    title: 'Yêu cầu cập nhật thông tin',
    body: message?.trim() || 'Vui lòng cập nhật thông tin hồ sơ của bạn trong ứng dụng.',
  })
}

// ── Audit Logs ─────────────────────────────────────────────────────────────────

export interface AuditLog {
  id: string
  actor_type: string
  actor_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  outcome: string | null
  occurred_at: string | null
}

export interface AuditLogListResponse {
  total: number
  items: AuditLog[]
}

/** Raw row shape returned by backend GET /admin/audit-logs (plain array). */
interface AuditLogRow {
  id: string
  actor_type: string
  actor_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  outcome: string | null
  timestamp: string | null
}

/**
 * Backend supports `limit` only and returns a plain array sorted newest-first —
 * action/resource_type are filtered client-side; `offset` is accepted for
 * caller compatibility but ignored (no server-side pagination).
 */
export async function getAuditLogs(params?: {
  limit?: number
  offset?: number
  action?: string
  resource_type?: string
}): Promise<AuditLogListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit) qs.set('limit', String(params.limit))
  const query = qs.toString()
  const rows = await api.get<AuditLogRow[]>(`/admin/audit-logs${query ? `?${query}` : ''}`)
  const action = params?.action?.trim().toLowerCase()
  const resourceType = params?.resource_type?.trim().toLowerCase()
  const items = rows
    .filter(
      (r) =>
        (!action || r.action.toLowerCase().includes(action)) &&
        (!resourceType || r.resource_type.toLowerCase().includes(resourceType)),
    )
    .map(({ timestamp, ...rest }) => ({ ...rest, occurred_at: timestamp }))
  return { total: items.length, items }
}

// ── AI Safety Monitoring ───────────────────────────────────────────────────────

export type AiSafetyLevel = 'safe' | 'caution' | 'urgent'
export type AiSessionFlag = 'none' | 'urgent_response' | 'off_topic' | 'clinical_claim' | 'review_requested'

export interface AiSession {
  id: string
  patient_id: string
  patient_name: string | null
  explanation_type: string
  safety_level: AiSafetyLevel
  flag: AiSessionFlag
  created_at: string
  reviewed_by: string | null
  reviewed_at: string | null
}

export interface AiSessionListResponse {
  total: number
  flagged_count: number
  items: AiSession[]
}

export async function getAiSessions(params?: {
  safety_level?: AiSafetyLevel
  flag?: AiSessionFlag
  reviewed?: boolean
  limit?: number
  offset?: number
}): Promise<AiSessionListResponse> {
  const qs = new URLSearchParams()
  if (params?.safety_level) qs.set('safety_level', params.safety_level)
  if (params?.flag) qs.set('flag', params.flag)
  if (params?.reviewed != null) qs.set('reviewed', String(params.reviewed))
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<AiSessionListResponse>(`/admin/ai-sessions${query ? `?${query}` : ''}`)
}

export async function reviewAiSession(sessionId: string): Promise<AiSession> {
  return api.patch<AiSession>(`/admin/ai-sessions/${sessionId}/review`, {})
}

// ── Feature Flags ──────────────────────────────────────────────────────────────

export interface FeatureFlag {
  key: string
  label: string
  description: string
  enabled: boolean
  rollout_pct: number
  updated_at: string
  updated_by: string | null
}

export async function getFeatureFlags(): Promise<FeatureFlag[]> {
  return api.get<FeatureFlag[]>('/admin/feature-flags')
}

export async function updateFeatureFlag(
  key: string,
  data: { enabled?: boolean; rollout_pct?: number },
): Promise<FeatureFlag> {
  return api.patch<FeatureFlag>(`/admin/feature-flags/${key}`, data)
}
