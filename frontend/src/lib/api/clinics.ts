import { api } from './client'

// ── Enums (exact backend string values — app/models/clinic.py) ───────────────

export type ClinicRole =
  | 'owner'
  | 'admin'
  | 'doctor'
  | 'nurse'
  | 'receptionist'
  | 'care_coordinator'
  | 'accountant'

export type ClinicStatus = 'trial' | 'active' | 'suspended' | 'expired' | 'deactivated'
export type ClinicBranchStatus = 'active' | 'paused' | 'archived'
export type ClinicMembershipStatus = 'invited' | 'active' | 'suspended' | 'removed'
export type ClinicInvitationStatus = 'pending' | 'accepted' | 'revoked' | 'expired'
export type ClinicServiceStatus = 'active' | 'inactive'

/** Request header used to select among the caller's own active clinic
 * memberships (app/api/deps_tenant.py get_tenant_context). Never a source of
 * authorization truth by itself — the backend validates it against the
 * caller's own membership rows. */
const CLINIC_HEADER = 'X-Clinic-Id'

function clinicHeaders(clinicId?: string): Record<string, string> | undefined {
  return clinicId ? { [CLINIC_HEADER]: clinicId } : undefined
}

// ── Clinic DTOs (app/schemas/clinic.py) ───────────────────────────────────────

export interface ClinicOut {
  id: string
  name: string
  legal_name: string | null
  tax_code: string | null
  license_no: string | null
  clinic_type: string | null
  status: ClinicStatus
  address: string | null
  phone: string | null
  email: string | null
  branding: Record<string, unknown> | null
  cancellation_policy: Record<string, unknown> | null
  queue_config: Record<string, unknown> | null
  overbooking_policy: Record<string, unknown> | null
  deactivated_at: string | null
  restored_at: string | null
  created_at: string
  updated_at: string
}

export interface ClinicListOut {
  total: number
  items: ClinicOut[]
}

export interface ClinicCreatePayload {
  name: string
  legal_name?: string | null
  tax_code?: string | null
  license_no?: string | null
  clinic_type?: string | null
  address?: string | null
  phone?: string | null
  email?: string | null
}

export interface ClinicSettingsUpdatePayload {
  name?: string
  legal_name?: string | null
  tax_code?: string | null
  license_no?: string | null
  clinic_type?: string | null
  address?: string | null
  phone?: string | null
  email?: string | null
  branding?: Record<string, unknown> | null
  cancellation_policy?: Record<string, unknown> | null
  queue_config?: Record<string, unknown> | null
  overbooking_policy?: Record<string, unknown> | null
}

export interface ClinicBranchOut {
  id: string
  clinic_id: string
  name: string
  address: Record<string, unknown> | null
  phone: string | null
  working_hours: Record<string, unknown>
  status: ClinicBranchStatus
  created_at: string
  updated_at: string
}

export interface ClinicBranchListOut {
  total: number
  items: ClinicBranchOut[]
}

export interface ClinicBranchCreatePayload {
  name: string
  working_hours: Record<string, unknown>
  address?: Record<string, unknown> | null
  phone?: string | null
}

export interface ClinicBranchUpdatePayload {
  name?: string
  working_hours?: Record<string, unknown>
  address?: Record<string, unknown> | null
  phone?: string | null
}

// ── Membership / invitation DTOs (app/schemas/clinic_membership.py) ──────────

export interface ClinicMembershipOut {
  id: string
  user_id: string
  clinic_id: string
  roles: ClinicRole[]
  branch_ids: string[]
  doctor_profile_id: string | null
  status: ClinicMembershipStatus
  is_primary: boolean
  joined_at: string | null
  left_at: string | null
  created_at: string
  updated_at: string
}

export interface ClinicMembershipListOut {
  total: number
  items: ClinicMembershipOut[]
}

export interface ClinicMembershipUpdatePayload {
  roles?: ClinicRole[]
  branch_ids?: string[]
  status?: ClinicMembershipStatus
}

/** One entry in the caller's own clinic-switcher list (`GET
 * /clinics/memberships/mine`) — distinct from `ClinicMembershipOut`, which is
 * the Owner/Admin staff-management view of one clinic's members. */
export interface MyClinicMembershipOut {
  id: string
  clinic_id: string
  clinic_name: string
  clinic_status: ClinicStatus
  roles: ClinicRole[]
  branch_ids: string[]
  is_primary: boolean
}

export interface MyClinicMembershipListOut {
  items: MyClinicMembershipOut[]
}

export interface ClinicInvitationOut {
  id: string
  clinic_id: string
  invited_email: string | null
  invited_phone: string | null
  roles: ClinicRole[]
  branch_ids: string[]
  status: ClinicInvitationStatus
  expires_at: string
  invited_by_user_id: string
  accepted_by_user_id: string | null
  created_at: string
}

export interface ClinicInvitationCreateOut extends ClinicInvitationOut {
  /** Present only once, at creation — never returned again after. */
  raw_token: string
}

export interface ClinicInvitationListOut {
  total: number
  items: ClinicInvitationOut[]
}

export interface ClinicInvitationCreatePayload {
  roles: ClinicRole[]
  branch_ids?: string[]
  invited_email?: string | null
  invited_phone?: string | null
}

// ── Service catalog DTOs (app/schemas/clinic_service.py) ──────────────────────

export type ClinicServiceType = 'single' | 'package'

export interface ClinicServiceOut {
  id: string
  clinic_id: string
  name: string
  code: string | null
  specialty: string | null
  duration_minutes: number | null
  // Backend serializes Decimal as a JSON string (precision-safe) — Codex
  // second-pass review P1, backend/app/schemas/clinic_service.py.
  price: string
  type: ClinicServiceType
  branch_ids: string[] | null
  doctor_ids: string[] | null
  package_visit_count: number | null
  duration_months: number | null
  included_items: Record<string, unknown> | null
  benefits: Record<string, unknown> | null
  cancellation_refund_policy: Record<string, unknown> | null
  status: ClinicServiceStatus
  created_at: string
  updated_at: string
}

export interface ClinicServiceListOut {
  total: number
  items: ClinicServiceOut[]
}

export interface ClinicServiceCreatePayload {
  name: string
  code: string
  specialty: string
  duration_minutes: number
  price: number
  type?: ClinicServiceType
  branch_ids?: string[] | null
  doctor_ids?: string[] | null
  package_visit_count?: number | null
  duration_months?: number | null
  included_items?: Record<string, unknown> | null
  benefits?: Record<string, unknown> | null
  cancellation_refund_policy?: Record<string, unknown> | null
}

export interface ClinicServiceUpdatePayload {
  name?: string
  code?: string
  specialty?: string
  duration_minutes?: number
  price?: number
  type?: ClinicServiceType
  branch_ids?: string[] | null
  doctor_ids?: string[] | null
  package_visit_count?: number | null
  duration_months?: number | null
  included_items?: Record<string, unknown> | null
  benefits?: Record<string, unknown> | null
  cancellation_refund_policy?: Record<string, unknown> | null
  status?: ClinicServiceStatus
}

// ── Subscription DTOs (app/schemas/clinic_subscription.py) ───────────────────

export interface SubscriptionPlanOut {
  id: string
  code: string
  name: string
  entitlements: Record<string, unknown>
}

export interface ClinicSubscriptionOut {
  id: string
  clinic_id: string
  plan_id: string
  started_at: string
  expires_at: string | null
  status: string
}

export interface EntitlementsOut {
  max_branches: number
  max_doctors: number
  max_active_patients: number
  copilot_quota_per_month: number
  crm_automation_enabled: boolean
  advanced_reports_enabled: boolean
  api_sso_enabled: boolean
}

export interface ClinicSubscriptionDetailOut {
  subscription: ClinicSubscriptionOut | null
  plan: SubscriptionPlanOut | null
  entitlements: EntitlementsOut
}

// ── Pagination helper ─────────────────────────────────────────────────────────

export interface PageParams {
  skip?: number
  limit?: number
}

function pageQuery(params: PageParams = {}): string {
  const qs = new URLSearchParams()
  if (params.skip != null) qs.set('skip', String(params.skip))
  if (params.limit != null) qs.set('limit', String(params.limit))
  const query = qs.toString()
  return query ? `?${query}` : ''
}

// ── Clinics (M01) ─────────────────────────────────────────────────────────────

/** Self-serve onboarding — caller becomes the new clinic's Owner (trial status). */
export async function createClinic(payload: ClinicCreatePayload): Promise<ClinicOut> {
  return api.post<ClinicOut>('/clinics', payload)
}

/** The caller's current active clinic (clinic-portal bootstrap call). */
export async function getMyClinic(clinicId?: string): Promise<ClinicOut> {
  return api.get<ClinicOut>('/clinics/me', { headers: clinicHeaders(clinicId) })
}

export async function getClinic(clinicId: string): Promise<ClinicOut> {
  return api.get<ClinicOut>(`/clinics/${clinicId}`, { headers: clinicHeaders(clinicId) })
}

/** The caller's own membership row (roles/branch scope) at their current
 * active clinic — pairs with `getMyClinic`, gives real RBAC_MATRIX.md role
 * data instead of probing 403s. */
export async function getMyMembership(clinicId?: string): Promise<ClinicMembershipOut> {
  return api.get<ClinicMembershipOut>('/clinics/me/membership', {
    headers: clinicHeaders(clinicId),
  })
}

/** Every clinic the caller is an active member of — the clinic-switcher's
 * data source. Not clinic-scoped (no X-Clinic-Id needed/sent). */
export async function listMyMemberships(): Promise<MyClinicMembershipListOut> {
  return api.get<MyClinicMembershipListOut>('/clinics/memberships/mine')
}

export async function updateClinicSettings(
  clinicId: string,
  payload: ClinicSettingsUpdatePayload
): Promise<ClinicOut> {
  return api.patch<ClinicOut>(`/clinics/${clinicId}`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

/** Owner-only voluntary closure — terminal state, never a hard delete. */
export async function deactivateClinic(clinicId: string): Promise<ClinicOut> {
  return api.post<ClinicOut>(`/clinics/${clinicId}/deactivate`, undefined, {
    headers: clinicHeaders(clinicId),
  })
}

// ── Branches (M02) ────────────────────────────────────────────────────────────

export async function listBranches(
  clinicId: string,
  params: PageParams = {}
): Promise<ClinicBranchListOut> {
  return api.get<ClinicBranchListOut>(`/clinics/${clinicId}/branches${pageQuery(params)}`, {
    headers: clinicHeaders(clinicId),
  })
}

export async function createBranch(
  clinicId: string,
  payload: ClinicBranchCreatePayload
): Promise<ClinicBranchOut> {
  return api.post<ClinicBranchOut>(`/clinics/${clinicId}/branches`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

export async function updateBranch(
  clinicId: string,
  branchId: string,
  payload: ClinicBranchUpdatePayload
): Promise<ClinicBranchOut> {
  return api.patch<ClinicBranchOut>(`/clinics/${clinicId}/branches/${branchId}`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

export async function setBranchStatus(
  clinicId: string,
  branchId: string,
  status: ClinicBranchStatus
): Promise<ClinicBranchOut> {
  return api.post<ClinicBranchOut>(
    `/clinics/${clinicId}/branches/${branchId}/status`,
    { status },
    { headers: clinicHeaders(clinicId) }
  )
}

// ── Membership + invitations (M03) ────────────────────────────────────────────

export async function listMembers(
  clinicId: string,
  params: PageParams = {}
): Promise<ClinicMembershipListOut> {
  return api.get<ClinicMembershipListOut>(`/clinics/${clinicId}/members${pageQuery(params)}`, {
    headers: clinicHeaders(clinicId),
  })
}

export async function updateMember(
  clinicId: string,
  membershipId: string,
  payload: ClinicMembershipUpdatePayload
): Promise<ClinicMembershipOut> {
  return api.patch<ClinicMembershipOut>(`/clinics/${clinicId}/members/${membershipId}`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

export async function listInvitations(
  clinicId: string,
  params: PageParams = {}
): Promise<ClinicInvitationListOut> {
  return api.get<ClinicInvitationListOut>(`/clinics/${clinicId}/invitations${pageQuery(params)}`, {
    headers: clinicHeaders(clinicId),
  })
}

export async function createInvitation(
  clinicId: string,
  payload: ClinicInvitationCreatePayload
): Promise<ClinicInvitationCreateOut> {
  return api.post<ClinicInvitationCreateOut>(`/clinics/${clinicId}/invitations`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

export async function revokeInvitation(
  clinicId: string,
  invitationId: string
): Promise<ClinicInvitationOut> {
  return api.post<ClinicInvitationOut>(
    `/clinics/${clinicId}/invitations/${invitationId}/revoke`,
    undefined,
    { headers: clinicHeaders(clinicId) }
  )
}

/** Not clinic-scoped — the invitee has no membership yet; auth is the token itself. */
export async function acceptInvitation(token: string): Promise<ClinicMembershipOut> {
  return api.post<ClinicMembershipOut>('/clinic-invitations/accept', { token })
}

// ── Services & pricing (M05) ──────────────────────────────────────────────────

export async function listServices(
  clinicId: string,
  params: PageParams = {}
): Promise<ClinicServiceListOut> {
  return api.get<ClinicServiceListOut>(`/clinics/${clinicId}/services${pageQuery(params)}`, {
    headers: clinicHeaders(clinicId),
  })
}

export async function createService(
  clinicId: string,
  payload: ClinicServiceCreatePayload
): Promise<ClinicServiceOut> {
  return api.post<ClinicServiceOut>(`/clinics/${clinicId}/services`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

export async function updateService(
  clinicId: string,
  serviceId: string,
  payload: ClinicServiceUpdatePayload
): Promise<ClinicServiceOut> {
  return api.patch<ClinicServiceOut>(`/clinics/${clinicId}/services/${serviceId}`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

// ── Subscription (M04) ────────────────────────────────────────────────────────

/** Platform-wide plan catalog — no clinic scope needed. */
export async function listSubscriptionPlans(): Promise<SubscriptionPlanOut[]> {
  return api.get<SubscriptionPlanOut[]>('/subscription-plans')
}

export async function getClinicSubscription(
  clinicId: string
): Promise<ClinicSubscriptionDetailOut> {
  return api.get<ClinicSubscriptionDetailOut>(`/clinics/${clinicId}/subscription`, {
    headers: clinicHeaders(clinicId),
  })
}
