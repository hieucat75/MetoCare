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
