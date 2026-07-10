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
export type ClinicPatientRelationshipStatus = 'active' | 'inactive' | 'merged'
export type ClinicAppointmentStatus =
  | 'pending'
  | 'confirmed'
  | 'arrived'
  | 'in_queue'
  | 'in_consultation'
  | 'completed'
  | 'cancelled'
  | 'no_show'

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

// ── Patient management DTOs (app/schemas/clinic_patient.py, M06) ─────────────

/** Full administrative record — Owner/Admin/Doctor/Nurse/Reception. Fields
 * tied to the clinic relationship (id/patient_code/status/internal_notes/
 * first_seen_at/created_at/updated_at) are `null` when the caller sees this
 * patient only via a cross-clinic Consent grant, with no own-clinic
 * relationship row (M06 plan §1's consent-shared read path). */
export interface ClinicPatientAdminOut {
  id: string | null
  patient_id: string
  clinic_id: string
  patient_code: string | null
  status: ClinicPatientRelationshipStatus | null
  internal_notes: string | null
  first_seen_at: string | null
  full_name: string | null
  dob: string | null
  gender: string | null
  address: string | null
  phone: string | null
  created_at: string | null
  updated_at: string | null
}

/** Care Coordinator's narrow "care context" shape — no dob/address/
 * internal_notes (RBAC_MATRIX.md M06 row: field-level filtering, not just
 * route-level gating). */
export interface ClinicPatientCareContextOut {
  id: string
  patient_id: string
  patient_code: string
  status: ClinicPatientRelationshipStatus
  full_name: string | null
  phone: string | null
  first_seen_at: string
}

export type ClinicPatientListItem = ClinicPatientAdminOut | ClinicPatientCareContextOut

export interface ClinicPatientListOut {
  total: number
  items: ClinicPatientListItem[]
}

export interface PatientCandidateOut {
  patient_id: string
  full_name: string | null
  dob: string | null
  phone: string | null
  already_linked: boolean
}

export interface ClinicPatientLinkPayload {
  patient_id: string
  /** Required proof-of-contact — must match the patient's real phone
   * (the value `searchPatientCandidate` matched on); the backend
   * re-verifies this server-side before linking (Codex review P0). */
  phone: string
  patient_code?: string | null
}

export interface ClinicPatientCreatePayload {
  full_name: string
  phone: string
  dob: string
  gender: string
  address?: string | null
  patient_code?: string | null
  override_dedup_reason?: string | null
}

export interface ClinicPatientUpdatePayload {
  status?: ClinicPatientRelationshipStatus
  internal_notes?: string
}

export interface ClinicPatientListParams extends PageParams {
  search?: string
}

// ── Appointment management DTOs (app/schemas/clinic_appointment.py, M07) ─────

export interface ClinicAppointmentOut {
  id: string
  clinic_id: string
  branch_id: string
  patient_id: string
  doctor_id: string | null
  service_id: string
  // Backend serializes Decimal as a JSON string (precision-safe), same
  // convention as ClinicServiceOut.price.
  price_snapshot: string
  start_time: string
  end_time: string
  status: ClinicAppointmentStatus
  created_by_user_id: string
  created_by_source: string
  linked_care_plan_item_id: string | null
  cancellation_reason: string | null
  cancelled_by_user_id: string | null
  cancelled_at: string | null
  reschedule_of_id: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface ClinicAppointmentListOut {
  total: number
  items: ClinicAppointmentOut[]
}

export interface ClinicAppointmentCreatePayload {
  branch_id: string
  patient_id: string
  doctor_id?: string | null
  service_id: string
  start_time: string
  notes?: string | null
  /** Owner/Admin-only — ignored server-side for any other caller (the
   * backend still enforces the real working-hours check either way). */
  override_working_hours_reason?: string | null
}

export interface ClinicAppointmentCancelPayload {
  reason: string
}

export interface ClinicAppointmentReschedulePayload {
  start_time: string
  reason: string
  branch_id?: string | null
  doctor_id?: string | null
}

export interface ClinicAppointmentNoShowPayload {
  reason?: string | null
}

export interface ClinicAppointmentArrivedOverridePayload {
  reason: string
}

export interface ClinicAppointmentListParams extends PageParams {
  branch_id?: string
  doctor_id?: string
  status?: ClinicAppointmentStatus
  date_from?: string
  date_to?: string
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

// ── Patient management (M06) ──────────────────────────────────────────────────

function patientListQuery(params: ClinicPatientListParams = {}): string {
  const qs = new URLSearchParams()
  if (params.skip != null) qs.set('skip', String(params.skip))
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.search) qs.set('search', params.search)
  const query = qs.toString()
  return query ? `?${query}` : ''
}

export async function listClinicPatients(
  clinicId: string,
  params: ClinicPatientListParams = {}
): Promise<ClinicPatientListOut> {
  return api.get<ClinicPatientListOut>(`/clinics/${clinicId}/patients${patientListQuery(params)}`, {
    headers: clinicHeaders(clinicId),
  })
}

/** Exact-phone-match dedup helper (BR-M06-02) — `null` when no candidate
 * matches. No partial/fuzzy search: never a patient-enumeration oracle. */
export async function searchPatientCandidate(
  clinicId: string,
  phone: string
): Promise<PatientCandidateOut | null> {
  return api.get<PatientCandidateOut | null>(
    `/clinics/${clinicId}/patients/search-candidates?phone=${encodeURIComponent(phone)}`,
    { headers: clinicHeaders(clinicId) }
  )
}

export async function linkClinicPatient(
  clinicId: string,
  payload: ClinicPatientLinkPayload
): Promise<ClinicPatientAdminOut> {
  return api.post<ClinicPatientAdminOut>(`/clinics/${clinicId}/patients/link`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

/** Throws `ApiError(409, ...)` with a JSON-stringified
 * `{code: 'DUPLICATE_CANDIDATE', candidate: PatientCandidateOut}` body when a
 * phone-exact-match candidate exists and `override_dedup_reason` was not
 * supplied — callers should `JSON.parse(err.detail)` on a 409 to surface the
 * AC-M06-02 duplicate-warning UI. */
export async function createClinicPatient(
  clinicId: string,
  payload: ClinicPatientCreatePayload
): Promise<ClinicPatientAdminOut> {
  return api.post<ClinicPatientAdminOut>(`/clinics/${clinicId}/patients`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

export async function getClinicPatient(
  clinicId: string,
  patientId: string
): Promise<ClinicPatientAdminOut | ClinicPatientCareContextOut> {
  return api.get<ClinicPatientAdminOut | ClinicPatientCareContextOut>(
    `/clinics/${clinicId}/patients/${patientId}`,
    { headers: clinicHeaders(clinicId) }
  )
}

export async function updateClinicPatient(
  clinicId: string,
  patientId: string,
  payload: ClinicPatientUpdatePayload
): Promise<ClinicPatientAdminOut> {
  return api.patch<ClinicPatientAdminOut>(`/clinics/${clinicId}/patients/${patientId}`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

// ── Appointment management (M07) ──────────────────────────────────────────────

function appointmentListQuery(params: ClinicAppointmentListParams = {}): string {
  const qs = new URLSearchParams()
  if (params.skip != null) qs.set('skip', String(params.skip))
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.branch_id) qs.set('branch_id', params.branch_id)
  if (params.doctor_id) qs.set('doctor_id', params.doctor_id)
  if (params.status) qs.set('status', params.status)
  if (params.date_from) qs.set('date_from', params.date_from)
  if (params.date_to) qs.set('date_to', params.date_to)
  const query = qs.toString()
  return query ? `?${query}` : ''
}

export async function listClinicAppointments(
  clinicId: string,
  params: ClinicAppointmentListParams = {}
): Promise<ClinicAppointmentListOut> {
  return api.get<ClinicAppointmentListOut>(
    `/clinics/${clinicId}/appointments${appointmentListQuery(params)}`,
    { headers: clinicHeaders(clinicId) }
  )
}

export async function createClinicAppointment(
  clinicId: string,
  payload: ClinicAppointmentCreatePayload
): Promise<ClinicAppointmentOut> {
  return api.post<ClinicAppointmentOut>(`/clinics/${clinicId}/appointments`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

export async function getClinicAppointment(
  clinicId: string,
  appointmentId: string
): Promise<ClinicAppointmentOut> {
  return api.get<ClinicAppointmentOut>(`/clinics/${clinicId}/appointments/${appointmentId}`, {
    headers: clinicHeaders(clinicId),
  })
}

export async function confirmClinicAppointment(
  clinicId: string,
  appointmentId: string
): Promise<ClinicAppointmentOut> {
  return api.post<ClinicAppointmentOut>(
    `/clinics/${clinicId}/appointments/${appointmentId}/confirm`,
    undefined,
    { headers: clinicHeaders(clinicId) }
  )
}

export async function cancelClinicAppointment(
  clinicId: string,
  appointmentId: string,
  payload: ClinicAppointmentCancelPayload
): Promise<ClinicAppointmentOut> {
  return api.post<ClinicAppointmentOut>(
    `/clinics/${clinicId}/appointments/${appointmentId}/cancel`,
    payload,
    { headers: clinicHeaders(clinicId) }
  )
}

export async function rescheduleClinicAppointment(
  clinicId: string,
  appointmentId: string,
  payload: ClinicAppointmentReschedulePayload
): Promise<ClinicAppointmentOut> {
  return api.post<ClinicAppointmentOut>(
    `/clinics/${clinicId}/appointments/${appointmentId}/reschedule`,
    payload,
    { headers: clinicHeaders(clinicId) }
  )
}

export async function markNoShow(
  clinicId: string,
  appointmentId: string,
  payload: ClinicAppointmentNoShowPayload = {}
): Promise<ClinicAppointmentOut> {
  return api.post<ClinicAppointmentOut>(
    `/clinics/${clinicId}/appointments/${appointmentId}/no-show`,
    payload,
    { headers: clinicHeaders(clinicId) }
  )
}

export async function markArrivedOverride(
  clinicId: string,
  appointmentId: string,
  payload: ClinicAppointmentArrivedOverridePayload
): Promise<ClinicAppointmentOut> {
  return api.post<ClinicAppointmentOut>(
    `/clinics/${clinicId}/appointments/${appointmentId}/arrived-override`,
    payload,
    { headers: clinicHeaders(clinicId) }
  )
}

// ── Check-in & queue (M08 — app/schemas/clinic_queue.py) ─────────────────────

export type ClinicQueueEntryStatus =
  | 'waiting'
  | 'called'
  | 'in_consultation'
  | 'completed'
  | 'left'

export type ClinicQueueEntrySource = 'scheduled' | 'walk_in'

/** Staff view — full operational fields (QUEUE-02) incl. the server-side-
 * decrypted patient display name. Mirrors `ClinicQueueEntryOut` exactly. */
export interface ClinicQueueEntryOut {
  id: string
  clinic_id: string
  branch_id: string
  patient_id: string
  appointment_id: string
  doctor_id: string | null
  service_date: string
  queue_number: number
  status: ClinicQueueEntryStatus
  is_priority: boolean
  priority_reason: string | null
  missed_call_count: number
  source: ClinicQueueEntrySource
  checked_in_at: string
  called_at: string | null
  consultation_started_at: string | null
  completed_at: string | null
  left_at: string | null
  // Enrichment (QUEUE-02 staff fields), computed server-side.
  patient_display_name: string | null
  doctor_name: string | null
  service_name: string | null
  appointment_start_time: string
  waiting_minutes: number
  /** BR-M08-04: over the missed-call cap — reception must resolve. */
  requires_reception_action: boolean
  created_at: string
  updated_at: string
}

export interface ClinicQueueListOut {
  total: number
  items: ClinicQueueEntryOut[]
}

/** Public-screen payload (AC-M08-03): number + masked initials + status +
 * doctor name ONLY — the backend schema shape itself excludes PHI. */
export interface ClinicQueueDisplayEntryOut {
  queue_number: number
  patient_initials: string
  status: string
  doctor_name: string | null
}

export interface ClinicQueueDisplayOut {
  items: ClinicQueueDisplayEntryOut[]
}

export interface ClinicQueueWalkInPayload {
  branch_id: string
  patient_id: string
  service_id: string
  doctor_id?: string | null
  notes?: string | null
}

export interface ClinicQueuePriorityPayload {
  is_priority: boolean
  /** Required (min 1 char) for BOTH set and unset — BR-M08-02/AC-M08-04. */
  reason: string
}

export interface ClinicQueueListParams {
  branch_id?: string
  doctor_id?: string
  /** ISO date (YYYY-MM-DD); backend defaults to the clinic's operational today. */
  service_date?: string
  status?: ClinicQueueEntryStatus
}

function queueListQuery(params: ClinicQueueListParams = {}): string {
  const qs = new URLSearchParams()
  if (params.branch_id) qs.set('branch_id', params.branch_id)
  if (params.doctor_id) qs.set('doctor_id', params.doctor_id)
  if (params.service_date) qs.set('service_date', params.service_date)
  if (params.status) qs.set('status', params.status)
  const query = qs.toString()
  return query ? `?${query}` : ''
}

/** Check-in a scheduled appointment (manage roles) — creates the queue entry. */
export async function checkInAppointment(
  clinicId: string,
  appointmentId: string
): Promise<ClinicQueueEntryOut> {
  return api.post<ClinicQueueEntryOut>(
    `/clinics/${clinicId}/appointments/${appointmentId}/check-in`,
    undefined,
    { headers: clinicHeaders(clinicId) }
  )
}

/** Walk-in (US-M08-02) — creates a `walk_in` appointment + queue entry in one call. */
export async function walkInCheckIn(
  clinicId: string,
  payload: ClinicQueueWalkInPayload
): Promise<ClinicQueueEntryOut> {
  return api.post<ClinicQueueEntryOut>(`/clinics/${clinicId}/queue/walk-in`, payload, {
    headers: clinicHeaders(clinicId),
  })
}

export async function listQueue(
  clinicId: string,
  params: ClinicQueueListParams = {}
): Promise<ClinicQueueListOut> {
  return api.get<ClinicQueueListOut>(`/clinics/${clinicId}/queue${queueListQuery(params)}`, {
    headers: clinicHeaders(clinicId),
  })
}

export async function getQueueDisplay(
  clinicId: string,
  branchId?: string
): Promise<ClinicQueueDisplayOut> {
  const query = branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''
  return api.get<ClinicQueueDisplayOut>(`/clinics/${clinicId}/queue/display${query}`, {
    headers: clinicHeaders(clinicId),
  })
}

function queueEntryAction(
  clinicId: string,
  entryId: string,
  action: 'call' | 'missed-call' | 'start-consultation' | 'complete' | 'leave'
): Promise<ClinicQueueEntryOut> {
  return api.post<ClinicQueueEntryOut>(
    `/clinics/${clinicId}/queue/${entryId}/${action}`,
    undefined,
    { headers: clinicHeaders(clinicId) }
  )
}

export async function callQueueEntry(
  clinicId: string,
  entryId: string
): Promise<ClinicQueueEntryOut> {
  return queueEntryAction(clinicId, entryId, 'call')
}

export async function markMissedCall(
  clinicId: string,
  entryId: string
): Promise<ClinicQueueEntryOut> {
  return queueEntryAction(clinicId, entryId, 'missed-call')
}

export async function startConsultation(
  clinicId: string,
  entryId: string
): Promise<ClinicQueueEntryOut> {
  return queueEntryAction(clinicId, entryId, 'start-consultation')
}

export async function completeQueueEntry(
  clinicId: string,
  entryId: string
): Promise<ClinicQueueEntryOut> {
  return queueEntryAction(clinicId, entryId, 'complete')
}

export async function leaveQueue(
  clinicId: string,
  entryId: string
): Promise<ClinicQueueEntryOut> {
  return queueEntryAction(clinicId, entryId, 'leave')
}

export async function setQueuePriority(
  clinicId: string,
  entryId: string,
  payload: ClinicQueuePriorityPayload
): Promise<ClinicQueueEntryOut> {
  return api.post<ClinicQueueEntryOut>(`/clinics/${clinicId}/queue/${entryId}/priority`, payload, {
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
