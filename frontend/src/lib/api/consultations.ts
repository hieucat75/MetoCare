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

export interface NoteOut {
  id: string
  consultation_id: string
  doctor_id: string
  content: string
  note_type: string
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

export interface ConsultationCreate {
  doctor_id: string
  consultation_type?: ConsultationType
  data_consent_accepted: boolean
  chief_complaint?: string
  patient_note?: string
  booking_appointment_id?: string
}

export interface ReviewCreate {
  rating: number
  feedback?: string
}

/** Append-only clinical note body (content 1..8000, note_type defaults recommendation). */
export interface NoteCreate {
  content: string
  note_type?: string
}

// ── Patient summary (DOCTOR, MFA, scoped) ─────────────────────────────────────
// Field names below mirror the documented PatientSummaryOut contract. Sub-item
// shapes are typed leniently (all optional) and rendered defensively, so any
// backend field-naming drift degrades to "not shown" rather than a crash.

export interface SummaryVital {
  metric_type?: string | null
  label?: string | null
  value?: number | string | null
  unit?: string | null
  recorded_at?: string | null
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
  title?: string | null
  document_type?: string | null
  test_date?: string | null
  uploaded_at?: string | null
  status?: string | null
}

export interface SummaryMedication {
  id?: string
  name?: string | null
  dosage?: string | null
  frequency?: string | null
  status?: string | null
}

export interface SummarySymptom {
  id?: string
  name?: string | null
  severity?: string | null
  note?: string | null
  recorded_at?: string | null
}

export interface SummaryNutrition {
  id?: string
  label?: string | null
  summary?: string | null
  recorded_at?: string | null
}

export interface SummaryAppointment {
  id?: string
  title?: string | null
  scheduled_at?: string | null
  status?: string | null
}

export interface SummaryCarePlan {
  id?: string
  title?: string | null
  status?: string | null
  summary?: string | null
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
