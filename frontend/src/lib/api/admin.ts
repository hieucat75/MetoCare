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
  email: string
  full_name: string | null
  role: AdminUserRole
  is_active: boolean
  mfa_enabled: boolean
  created_at: string
  last_login_at: string | null
}

export interface AdminUserListResponse {
  total: number
  items: AdminUser[]
}

export async function getUsers(params?: {
  role?: AdminUserRole
  search?: string
  limit?: number
  offset?: number
}): Promise<AdminUserListResponse> {
  const qs = new URLSearchParams()
  if (params?.role) qs.set('role', params.role)
  if (params?.search) qs.set('search', params.search)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<AdminUserListResponse>(`/admin/users${query ? `?${query}` : ''}`)
}

export async function toggleUserActive(userId: string, isActive: boolean): Promise<AdminUser> {
  return api.patch<AdminUser>(`/admin/users/${userId}`, { is_active: isActive })
}

// ── Audit Logs ─────────────────────────────────────────────────────────────────

export interface AuditLog {
  id: string
  actor_id: string
  actor_email: string | null
  action: string
  resource_type: string
  resource_id: string | null
  ip_address: string | null
  occurred_at: string
  metadata: Record<string, unknown> | null
}

export interface AuditLogListResponse {
  total: number
  items: AuditLog[]
}

export async function getAuditLogs(params?: {
  actor_id?: string
  action?: string
  resource_type?: string
  limit?: number
  offset?: number
}): Promise<AuditLogListResponse> {
  const qs = new URLSearchParams()
  if (params?.actor_id) qs.set('actor_id', params.actor_id)
  if (params?.action) qs.set('action', params.action)
  if (params?.resource_type) qs.set('resource_type', params.resource_type)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<AuditLogListResponse>(`/admin/audit-logs${query ? `?${query}` : ''}`)
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
