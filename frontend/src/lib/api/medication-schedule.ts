/**
 * Journey-3 medication API for the web client: structured schedules, the due-dose
 * reminder loop (mark taken / skipped with a reason), dose-occurrence adherence,
 * and BRD §F source-document provenance.
 *
 * These endpoints already existed and are already consumed by the mobile app
 * (`mobile/src/api/medication.ts`). The web client had no binding for any of them,
 * which is why the medication detail page still wrote to the LEGACY
 * `medication_adherence` model (`logAdherence` in `./patient`). This module is the
 * web-side binding — the contracts below mirror the backend Pydantic models in
 * `backend/app/api/v1/routes/medication_schedule.py` and
 * `backend/app/api/v1/routes/medication_source.py`, not a parallel model.
 *
 * Every endpoint is patient-owned: `patientId` MUST be the caller's own
 * `patient_profile_id`. The backend answers 403 otherwise.
 */

import { api } from './client'

// ── Contracts (mirror the backend Pydantic models 1:1) ───────────────────────

/** `ScheduleOut` — one structured dosing schedule. */
export interface MedicationSchedule {
  id: string
  medication_id: string
  /** e.g. `fixed_daily`. Free-form on the backend — never switch exhaustively. */
  schedule_type: string
  /** Local wall-clock times, e.g. `["08:00","20:00"]`. */
  local_dose_times: string[] | null
  /** `active` | `paused` | `stopped` (backend-owned vocabulary). */
  status: string
  version: number
  /** IANA zone the doses are rendered in, e.g. `Asia/Ho_Chi_Minh`. */
  patient_timezone: string
  start_date: string | null
  end_date: string | null
}

/** `DoseOut` — one materialized dose occurrence. */
export interface DoseOccurrence {
  id: string
  schedule_id: string
  scheduled_utc: string
  /** Backend-rendered local time string; authoritative over client formatting. */
  local_render: string | null
  /** `pending` | `notified` | `taken` | `skipped` | `missed`. */
  state: string
  /**
   * Present only on a dose the patient corrected. The system's original
   * classification is kept beside the human's, so a 100% figure containing late
   * self-reports is distinguishable from one that never needed correcting.
   */
  corrected_from_state?: string | null
  corrected_at?: string | null
  correction_reason?: string | null
}

/** Reasons a patient may give for correcting a missed dose. Closed vocabulary:
 * free text here would put their account of their own symptoms into an audit
 * trail built to avoid PHI. Every label records what happened; none advises
 * whether to take a late dose. */
export const DOSE_CORRECTION_REASONS = [
  { code: 'taken_late', label: 'Tôi đã uống muộn hơn giờ nhắc' },
  { code: 'taken_not_recorded', label: 'Tôi đã uống nhưng quên ghi nhận' },
  { code: 'deliberately_skipped', label: 'Tôi chủ động bỏ liều này' },
  { code: 'recorded_in_error', label: 'Ghi nhận này không đúng' },
  { code: 'other', label: 'Lý do khác' },
] as const

export type DoseCorrectionReason = (typeof DOSE_CORRECTION_REASONS)[number]['code']

/** `DueOut` — the reminder sweep result. */
export interface RemindersDue {
  delivered: number
  items: DoseOccurrence[]
}

/**
 * `AdherenceOut` — dose-occurrence-based adherence for ONE schedule.
 *
 * The legacy `total/taken/skipped/missed` quartet is still sent, but it cannot
 * describe the period it was computed over — and the UI rendered "kể từ
 * {earliest start_date}" over what is in fact a bounded 30-day window. Read the
 * `*_count` fields and the period, and NEVER render `adherence_rate` when
 * `reconciled` is false: an unreconciled rate is not a less precise number, it
 * is a different quantity (how often the patient opened the app).
 */
export interface ScheduleAdherence {
  expected_count: number
  taken_count: number
  skipped_count: number
  missed_count: number
  future_count: number
  /**
   * Doses excluded because the schedule was PAUSED — a hold the patient was
   * instructed to observe. Must never be presented as non-adherence: a patient
   * who followed a doctor's instruction did not miss anything.
   */
  excluded_paused_count: number
  /** Doses excluded because the prescription was withdrawn or superseded. */
  excluded_cancelled_count: number
  /** `null` whenever `reconciled` is false. Never substitute 0. */
  adherence_rate: number | null
  /** Inclusive local dates the figure actually covers. */
  period_start: string
  period_end: string
  timezone: string
  /** Bumped when the denominator SEMANTICS change, not when the code moves. */
  calculation_version: string
  /** False ⇒ hide the percentage and render the unavailable state. */
  reconciled: boolean
  /** Machine-readable reason, so the UI can say WHY rather than merely "no data". */
  reconciliation_reason: string
  /** The backfill floor applied — adherence starts here, not at `start_date`. */
  tracking_start_at: string | null
  grace_policy: { version: string; missed_after_hours: number | null }

  /** Legacy aliases, same numbers. Retained so an un-migrated caller keeps working. */
  total: number
  taken: number
  skipped: number
  missed: number
}

/** `SourceDocumentOut` — one document this medication was promoted from. */
export interface MedicationSourceDocument {
  document_id: string
  doc_type: string | null
  document_status: string
  document_source: string
  page_count: number | null
  uploaded_at: string | null
  promotion_action: string
  promoted_at: string | null
  candidate_id: string
  candidate_status: string
  candidate_reviewed_at: string | null
  /** Allowlisted prescription-line fields. A missing key means OCR never produced it. */
  prescription_fields: Record<string, string>
  /** Allowlisted header context: facility / prescriber / prescribed_date. */
  prescription_context: Record<string, string>
  ocr_provider: string | null
  ocr_model: string | null
  ocr_prompt_version: string | null
  ocr_schema_version: string | null
  extraction_review_state: string | null
}

/** `MedicationSourceOut` — provenance envelope for one medication. */
export interface MedicationSource {
  medication_id: string
  source_type: string
  verification_status: string
  has_document_source: boolean
  documents: MedicationSourceDocument[]
}

// ── Reads ────────────────────────────────────────────────────────────────────

/** Every schedule (all versions) for one medication, newest first. */
export async function getMedicationSchedules(
  patientId: string,
  medicationId: string
): Promise<MedicationSchedule[]> {
  return api.get<MedicationSchedule[]>(
    `/patients/${patientId}/medications/${medicationId}/schedule`
  )
}

/**
 * Doses due NOW across all of the patient's active schedules.
 *
 * NOT a pure read — server-side this materializes newly-due doses, sweeps overdue
 * ones to `missed`, and delivers in-app reminders. It is the canonical read for any
 * reminder surface, but must never be called on a render loop.
 */
export async function getRemindersDue(patientId: string): Promise<RemindersDue> {
  return api.get<RemindersDue>(`/patients/${patientId}/reminders/due`)
}

/** Dose-occurrence adherence for one schedule (taken / skipped / missed / rate). */
export async function getScheduleAdherence(
  patientId: string,
  scheduleId: string
): Promise<ScheduleAdherence> {
  return api.get<ScheduleAdherence>(`/patients/${patientId}/schedules/${scheduleId}/adherence`)
}

/**
 * Source document(s) + OCR provenance for one medication.
 *
 * Answers 403 when the patient has not granted `documents` consent (PRIV-F1
 * fail-closed). Callers MUST treat that as "source unavailable", not as a page
 * failure — the rest of the medication detail does not depend on it.
 */
export async function getMedicationSource(
  patientId: string,
  medicationId: string
): Promise<MedicationSource> {
  return api.get<MedicationSource>(`/patients/${patientId}/medications/${medicationId}/source`)
}

// ── Writes ───────────────────────────────────────────────────────────────────

/** Mark one due dose as taken. */
export async function markDoseTaken(patientId: string, doseId: string): Promise<DoseOccurrence> {
  return api.post<DoseOccurrence>(`/patients/${patientId}/doses/${doseId}/taken`)
}

/**
 * Mark one due dose as skipped. `skipReason` is optional on the wire (backend
 * `MarkDoseIn.skip_reason`, max 255) but the UI should always offer one — an
 * unexplained skip is clinically less useful than an explained one.
 */
export async function markDoseSkipped(
  patientId: string,
  doseId: string,
  skipReason?: string
): Promise<DoseOccurrence> {
  return api.post<DoseOccurrence>(`/patients/${patientId}/doses/${doseId}/skipped`, {
    skip_reason: skipReason?.trim() || null,
  })
}

/**
 * Doses the system classified as MISSED, newest first.
 *
 * MISSED is assigned by a clock — nobody asserted it. Until this existed the row
 * appeared in no list, so the patient could not obtain its id and had no way to
 * say "I took that". An adherence figure a patient cannot correct is not a
 * measurement of the patient.
 */
export async function getMissedDoses(
  patientId: string,
  scheduleId?: string,
  limit = 100
): Promise<DoseOccurrence[]> {
  const query = new URLSearchParams({ limit: String(limit) })
  if (scheduleId) query.set('schedule_id', scheduleId)
  return api.get<DoseOccurrence[]>(`/patients/${patientId}/doses/missed?${query}`)
}

/**
 * Record what actually happened to a dose the system marked missed.
 *
 * Records; does not advise. Whether to take a late dose is a clinical decision
 * this app does not make, so no caller should pair this with guidance about it.
 * Only a MISSED dose is correctable and a correction cannot be corrected — the
 * backend answers 422 rather than silently overwriting.
 */
export async function correctDose(
  patientId: string,
  doseId: string,
  state: 'taken' | 'skipped',
  reasonCode: DoseCorrectionReason = 'other'
): Promise<DoseOccurrence> {
  return api.post<DoseOccurrence>(`/patients/${patientId}/doses/${doseId}/correct`, {
    state,
    reason_code: reasonCode,
  })
}
