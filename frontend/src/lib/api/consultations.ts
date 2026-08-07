import { api } from './client'
import type { ConsultationStatus, ConsultationType, PaymentStatus } from './marketplace'

// ── DTOs ──────────────────────────────────────────────────────────────────────

export interface ConsultationOut {
  id: string
  patient_id: string
  doctor_id: string
  consultation_type: ConsultationType
  status: ConsultationStatus
  consultation_price: number
  data_consent_accepted: boolean
  data_consent_accepted_at?: string | null
  chief_complaint?: string | null
  patient_note?: string | null
  booking_appointment_id?: string | null
  confirmed_at?: string | null
  paid_at?: string | null
  started_at?: string | null
  completed_at?: string | null
  cancelled_at?: string | null
  cancel_reason?: string | null
  created_at?: string | null
  disclaimer?: string | null
}

export interface PatientPaymentOut {
  consultation_id: string
  consultation_price: number
  currency: string
  payment_status: PaymentStatus
  paid_at?: string | null
}

export type NoteStatus = 'draft' | 'finalized'

export interface NoteOut {
  id: string
  consultation_id: string
  doctor_id: string
  content: string
  note_type: string
  status: NoteStatus
  finalized_at?: string | null
  created_at?: string | null
}

export interface ReviewOut {
  id: string
  consultation_id: string
  patient_id: string
  doctor_id: string
  rating: number
  feedback?: string | null
  created_at?: string | null
}

// ── Request payloads ──────────────────────────────────────────────────────────

/**
 * The patient's explicit, consultation-specific data-sharing consent.
 *
 * `accepted` is `true` and nothing else — the type has no room for a declined
 * value, because a declined modal must never produce a booking request at all.
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
  consultation_type?: ConsultationType
  data_consent_accepted: boolean
  data_sharing_consent: DataSharingConsentIn
  chief_complaint?: string
  patient_note?: string
  booking_appointment_id?: string
}

export interface ConsentCategory {
  key: string
  label: string
}

/** Server-authored copy for the consent modal — rendered verbatim, never re-worded client-side. */
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
  revoked_at?: string | null
  is_active: boolean
  source?: string | null
}

export interface ReviewCreate {
  rating: number
  feedback?: string
}

/** Append-only clinical note body (content 1..8000, note_type defaults recommendation). */
export interface NoteCreate {
  content: string
  note_type?: string
  /** 'draft' (Lưu nháp) or 'finalized' (Hoàn tất). Defaults to 'finalized'. */
  status?: NoteStatus
}

// ── Patient summary (DOCTOR, MFA, scoped) ─────────────────────────────────────
// Field names below mirror the documented PatientSummaryOut contract. Sub-item
// shapes are typed leniently (all optional) and rendered defensively, so any
// backend field-naming drift degrades to "not shown" rather than a crash.

export interface SummaryVital {
  id?: string
  metric_type?: string | null
  value?: number | string | null
  unit?: string | null
  measured_at?: string | null
  status?: string | null
}

export interface SummaryVitals {
  latest: SummaryVital[]
  trend?: string | null
}

export interface SummaryMetabolicScore {
  latest_score?: number | null
  trend?: string | null
  recorded_at?: string | null
}

export interface SummaryLabDocument {
  id?: string
  lab_name?: string | null
  file_type?: string | null
  ocr_status?: string | null
  status?: string | null
  created_at?: string | null
}

export interface SummaryMedication {
  id?: string
  name?: string | null
  dose?: string | null
  note?: string | null
  created_at?: string | null
}

export interface SummarySymptom {
  id?: string
  description?: string | null
  severity?: string | null
  reported_at?: string | null
}

export interface SummaryNutrition {
  id?: string
  description?: string | null
  meal_type?: string | null
  calories_kcal?: number | null
  logged_at?: string | null
}

export interface SummaryAppointment {
  id?: string
  doctor_id?: string | null
  status?: string | null
  notes?: string | null
  slot_start?: string | null
  created_at?: string | null
}

export interface SummaryCarePlan {
  id?: string
  title?: string | null
  version?: number | null
}

export interface PatientSummaryOut {
  patient_id: string
  generated_at: string
  vitals: SummaryVitals
  lab_documents: SummaryLabDocument[]
  metabolic_score: SummaryMetabolicScore
  medications: SummaryMedication[]
  symptoms: SummarySymptom[]
  nutrition: SummaryNutrition[]
  upcoming_appointments: SummaryAppointment[]
  active_care_plans: SummaryCarePlan[]
}

// ── Typed functions ───────────────────────────────────────────────────────────

/** PATIENT: create a consultation request (status REQUESTED). 422 if consent false. */
export async function createConsultation(payload: ConsultationCreate): Promise<ConsultationOut> {
  return api.post<ConsultationOut>('/consultations', payload)
}

/**
 * PATIENT: the consent copy + grantable categories the modal must render.
 *
 * Fetched rather than hardcoded so the words shown to the patient are exactly
 * the words versioned against the grant the server records.
 */
export async function getDataSharingPolicy(): Promise<DataSharingConsentPolicy> {
  return api.get<DataSharingConsentPolicy>('/consultations/data-sharing-policy')
}

/** PATIENT: read their own recorded sharing consent for a consultation. */
export async function getDataSharingConsent(id: string): Promise<DataSharingConsent> {
  return api.get<DataSharingConsent>(`/consultations/${id}/data-sharing-consent`)
}

/**
 * PATIENT: withdraw sharing. Takes effect immediately — the doctor's next read
 * is refused. Does not cancel the consultation or delete anything already
 * recorded. Idempotent.
 */
export async function revokeDataSharingConsent(id: string): Promise<{ message: string }> {
  return api.del<{ message: string }>(`/consultations/${id}/data-sharing-consent`)
}

/** List consultations scoped to the caller (PATIENT own / DOCTOR own / admin). */
export async function listConsultations(): Promise<ConsultationOut[]> {
  return api.get<ConsultationOut[]>('/consultations')
}

/** Fetch a single consultation (ownership-scoped; 403 if not owner). */
export async function getConsultation(id: string): Promise<ConsultationOut> {
  return api.get<ConsultationOut>(`/consultations/${id}`)
}

/** PATIENT: mock-pay ("Thanh toán thử") → payment_status PAID. */
export async function payConsultation(id: string): Promise<PatientPaymentOut> {
  return api.post<PatientPaymentOut>(`/consultations/${id}/pay`, {})
}

/** PATIENT or DOCTOR: cancel a consultation with an optional reason (<=255). */
export async function cancelConsultation(id: string, reason?: string): Promise<ConsultationOut> {
  return api.post<ConsultationOut>(`/consultations/${id}/cancel`, { reason })
}

/**
 * List doctor notes for a consultation. Patient may only read AFTER COMPLETED —
 * the API enforces this (403 before completion); callers should handle gracefully.
 */
export async function listNotes(id: string): Promise<NoteOut[]> {
  return api.get<NoteOut[]>(`/consultations/${id}/notes`)
}

/** PATIENT: submit a review (rating 1..5 + optional feedback) after COMPLETED. */
export async function createReview(id: string, payload: ReviewCreate): Promise<ReviewOut> {
  return api.post<ReviewOut>(`/consultations/${id}/review`, payload)
}

// ── Doctor-side consultation functions (DOCTOR, MFA) ──────────────────────────

/** DOCTOR: list the caller's own consultations. */
export async function listMyConsultations(): Promise<ConsultationOut[]> {
  return api.get<ConsultationOut[]>('/doctors/me/consultations')
}

/**
 * DOCTOR: fetch the scoped + audited patient summary for a consultation.
 * Returns 403 before payment and after complete/cancel (access window is
 * PAID → IN_PROGRESS); callers must render a "no access" state on 403.
 */
export async function getPatientSummary(id: string): Promise<PatientSummaryOut> {
  return api.get<PatientSummaryOut>(`/consultations/${id}/patient-summary`)
}

/** DOCTOR: confirm a REQUESTED consultation → CONFIRMED (409 if invalid transition). */
export async function confirmConsultation(id: string): Promise<ConsultationOut> {
  return api.post<ConsultationOut>(`/consultations/${id}/confirm`, {})
}

/** DOCTOR: start a PAID consultation → IN_PROGRESS (409 if not PAID). */
export async function startConsultation(id: string): Promise<ConsultationOut> {
  return api.post<ConsultationOut>(`/consultations/${id}/start`, {})
}

/** DOCTOR: complete an IN_PROGRESS consultation → COMPLETED (409 if invalid transition). */
export async function completeConsultation(id: string): Promise<ConsultationOut> {
  return api.post<ConsultationOut>(`/consultations/${id}/complete`, {})
}

/** DOCTOR: append an immutable clinical note (content 1..8000). Notes cannot be edited/deleted. */
export async function createNote(id: string, payload: NoteCreate): Promise<NoteOut> {
  return api.post<NoteOut>(`/consultations/${id}/notes`, payload)
}
