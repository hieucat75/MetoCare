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

// ── Typed functions ───────────────────────────────────────────────────────────

/** PATIENT: create a consultation request (status REQUESTED). 422 if consent false. */
export async function createConsultation(
  payload: ConsultationCreate,
): Promise<ConsultationOut> {
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
export async function cancelConsultation(
  id: string,
  reason?: string,
): Promise<ConsultationOut> {
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
export async function createReview(
  id: string,
  payload: ReviewCreate,
): Promise<ReviewOut> {
  return api.post<ReviewOut>(`/consultations/${id}/review`, payload)
}
