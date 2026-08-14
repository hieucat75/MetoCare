/** Backend API contract types — mirrored from frontend/src/lib/api/auth.ts. */

export type UserRole =
  | 'patient'
  | 'doctor'
  | 'medical_reviewer'
  | 'internal_admin'
  | 'super_admin'
  | 'ai_service'
  | 'clinic_admin'

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  role: UserRole
  user_id: string
  mfa: boolean
}

export interface UserResponse {
  id: string
  email: string | null
  phone: string | null
  role: UserRole
  full_name: string | null
  mfa_enabled: boolean
  notify_medication: boolean
  notify_lab_results: boolean
  notify_doctor_messages: boolean
  patient_profile_id?: string | null
  accepted_terms_version?: string | null
}

/** Consent payload accepted by /auth/register and /auth/accept-terms. */
export interface ConsentPayload {
  accepted: boolean
  terms_version: string
  privacy_version: string
  app_version?: string
  locale?: string
  timezone?: string
  device_platform?: string
  accepted_source?: string
  accepted_language?: string
}

// ── Unified LabResult contract (Phase A, mirrored from backend
// app/schemas/lab.py::LabResultOut / app/schemas/health.py::MetricOut).
// Mobile has no lab/metric-rendering screen yet — these types exist so the
// first screen that adds one builds on the authoritative contract fields
// from day one, instead of a future author reinventing local classification
// (the exact mistake Phase B removed from the web frontend). A future
// consumer MUST render `status`/`severity`/`reference_display` verbatim and
// must NOT recompute them from `value`/`unit`. `null`/absent contract fields
// (non-lab vitals, or an old cached response) must render a neutral
// "unknown" state, never a locally-inferred normal/high/critical.

export type LabInterpretationState = 'confirmed' | 'needs_review'

export type LabReferenceSource =
  | 'source_report'
  | 'validated_lab_range'
  | 'canonical_fallback'
  | 'unavailable'

/** `status`/`severity` enum resolved by app.domain.lab_semantics.resolve_lab_semantics. */
export type LabStatus = 'normal' | 'low' | 'high' | 'critical' | 'unknown'

export interface LabResultOut {
  id: string
  patient_id: string
  document_id: string | null
  batch_id: string | null
  test_name: string
  canonical_name: string | null
  value: number | null
  unit: string | null
  reference_range: string | null
  status: LabStatus | null
  clinical_message: string | null
  test_date: string | null
  verified_by_user: boolean
  original_value: number | null
  original_unit: string | null
  original_reference_range: string | null
  original_test_name: string | null
  display: string | null
  normalized_value_si: number | null
  normalized_unit_si: string | null
  data_quality_flag?: string | null
  created_at: string
  // Contract fields — see module doc comment above.
  display_name: string | null
  reference_low: number | null
  reference_high: number | null
  reference_unit: string | null
  reference_display: string | null
  reference_source: LabReferenceSource | null
  severity: LabStatus | null
  interpretation_state: LabInterpretationState | null
  needs_review: boolean
  rule_version: string | null
}

export interface MetricOut {
  id: string
  metric_type: string
  value: number
  unit: string | null
  original_value: number | null
  original_unit: string | null
  display: string | null
  measured_at: string
  // Non-lab vitals (BP, weight, ...) use their own legacy status vocabulary
  // ('normal'|'borderline'|'abnormal'|'critical') — resolve_lab_semantics
  // never touches those, so this field is wider than LabStatus alone.
  status: LabStatus | 'borderline' | 'abnormal' | null
  source: string | null
  clinical_message: string | null
  is_critical: boolean
  // Contract fields — null/absent for non-lab vitals; see module doc comment.
  display_name: string | null
  reference_low: number | null
  reference_high: number | null
  reference_unit: string | null
  reference_display: string | null
  reference_source: LabReferenceSource | null
  severity: LabStatus | null
  interpretation_state: LabInterpretationState | null
  needs_review: boolean
  rule_version: string | null
}
