import type { ApiClient } from './client'

/**
 * Consultation bounded-context (Journey 5) API — patient-facing booking, payment,
 * notes (read-only for the patient) and reviews. Mirrors the backend contract in
 * backend/app/api/v1/routes/consultations.py and the schemas in
 * backend/app/schemas/consultation.py.
 *
 * The doctor-only surfaces (confirm/start/complete transitions, note creation,
 * scoped patient-summary) are intentionally NOT exposed here — this is the
 * patient client. There is no live patient<->doctor messaging in the backend, so
 * none is fabricated.
 */

export type ConsultationTypeValue = 'CHAT' | 'VIDEO' | 'IN_PERSON'

/**
 * The patient's explicit, consultation-specific data-sharing consent.
 *
 * `accepted` is typed as `true` and nothing else — there is no representation
 * for a declined consent, because declining must not produce a request at all.
 */
export interface DataSharingConsentIn {
  accepted: true
  categories: string[]
  consent_version?: string
  policy_version?: string
  source?: string
  client_app_version?: string
  locale?: string
}

export interface ConsultationCreate {
  doctor_id: string
  consultation_type?: ConsultationTypeValue
  data_consent_accepted: boolean
  data_sharing_consent: DataSharingConsentIn
  chief_complaint?: string | null
  patient_note?: string | null
  booking_appointment_id?: string | null
}

export interface ConsentCategory {
  key: string
  label: string
}

/**
 * Server-authored consent copy. Rendered verbatim and NOT duplicated in i18n —
 * the words the patient reads must be the words versioned against their grant.
 */
export interface DataSharingConsentPolicy {
  consent_version: string
  policy_version: string
  purpose: string
  title: string
  body: string
  accept_label: string
  decline_label: string
  categories: ConsentCategory[]
}

export interface DataSharingConsent {
  id: string
  consultation_id: string
  doctor_id: string
  purpose: string
  consent_version: string
  policy_version: string
  categories: string[]
  granted_at: string
  revoked_at: string | null
  is_active: boolean
  source: string | null
}

export interface ConsultationOut {
  id: string
  patient_id: string
  doctor_id: string
  consultation_type: string
  status: string
  consultation_price: number
  data_consent_accepted: boolean
  data_consent_accepted_at: string | null
  chief_complaint: string | null
  patient_note: string | null
  booking_appointment_id: string | null
  confirmed_at: string | null
  paid_at: string | null
  started_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  cancel_reason: string | null
  created_at: string | null
  disclaimer: string | null
}

export interface ConsultationCancel {
  reason?: string | null
}

/** Patient-facing payment view — omits platform-fee / doctor-payout internals. */
export interface PatientPaymentOut {
  consultation_id: string
  consultation_price: number
  currency: string
  payment_status: string
  paid_at: string | null
}

export interface NoteOut {
  id: string
  consultation_id: string
  doctor_id: string
  content: string
  note_type: string
  status: string
  finalized_at: string | null
  created_at: string | null
}

export interface ReviewCreate {
  rating: number
  feedback?: string | null
}

export interface ReviewOut {
  id: string
  consultation_id: string
  patient_id: string
  doctor_id: string
  rating: number
  feedback: string | null
  created_at: string | null
}

export function createConsultation(
  client: ApiClient,
  body: ConsultationCreate
): Promise<ConsultationOut> {
  return client.post<ConsultationOut>('/consultations', body)
}

/** The consent copy + grantable categories the booking modal must render. */
export function getDataSharingPolicy(client: ApiClient): Promise<DataSharingConsentPolicy> {
  return client.get<DataSharingConsentPolicy>('/consultations/data-sharing-policy')
}

/** The patient's own recorded sharing consent for a consultation. */
export function getDataSharingConsent(
  client: ApiClient,
  id: string
): Promise<DataSharingConsent> {
  return client.get<DataSharingConsent>(`/consultations/${id}/data-sharing-consent`)
}

/**
 * Withdraw sharing. Immediate — the doctor's next read is refused. Does not
 * cancel the consultation or delete anything already recorded. Idempotent.
 */
export function revokeDataSharingConsent(
  client: ApiClient,
  id: string
): Promise<{ message: string }> {
  return client.del<{ message: string }>(`/consultations/${id}/data-sharing-consent`)
}

/**
 * Re-grant sharing the patient previously withdrew, so revoking is never a trap
 * on a paid session. Omitting `categories` re-grants exactly what was granted
 * before. Only ever called from an explicit patient action.
 */
export function restoreDataSharingConsent(
  client: ApiClient,
  id: string,
  body: DataSharingConsentIn
): Promise<DataSharingConsent> {
  return client.post<DataSharingConsent>(`/consultations/${id}/data-sharing-consent`, body)
}

export function listConsultations(client: ApiClient): Promise<ConsultationOut[]> {
  return client.get<ConsultationOut[]>('/consultations')
}

export function getConsultation(client: ApiClient, id: string): Promise<ConsultationOut> {
  return client.get<ConsultationOut>(`/consultations/${id}`)
}

export function payConsultation(client: ApiClient, id: string): Promise<PatientPaymentOut> {
  return client.post<PatientPaymentOut>(`/consultations/${id}/pay`)
}

export function cancelConsultation(
  client: ApiClient,
  id: string,
  body?: ConsultationCancel
): Promise<ConsultationOut> {
  return client.post<ConsultationOut>(`/consultations/${id}/cancel`, body)
}

export function submitReview(
  client: ApiClient,
  id: string,
  body: ReviewCreate
): Promise<ReviewOut> {
  return client.post<ReviewOut>(`/consultations/${id}/review`, body)
}

export function listNotes(client: ApiClient, id: string): Promise<NoteOut[]> {
  return client.get<NoteOut[]>(`/consultations/${id}/notes`)
}
