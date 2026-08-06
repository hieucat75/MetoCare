import type { ApiClient } from './client'

/**
 * Medication Daily Care (Journey B) API — patient-facing medication list,
 * structured schedules, the due-dose reminder loop (mark taken / skipped) and
 * per-schedule adherence. Mirrors the backend contracts in:
 *   - backend/app/api/v1/routes/patients.py            (medication records)
 *   - backend/app/api/v1/routes/medication_schedule.py (schedules/reminders/adherence)
 * and the schemas in backend/app/schemas/medication.py + the ScheduleOut/DoseOut/
 * AdherenceOut Pydantic models declared inline in the medication_schedule route.
 *
 * Every endpoint is patient-owned: the path `patientId` MUST equal the caller's
 * own PatientProfile.id (UserResponse.patient_profile_id). The backend enforces
 * self-ownership (403 otherwise). There is NO single-medication GET on the
 * backend — the detail view derives its record from the list, so none is
 * fabricated here.
 */

/** MedicationOut — a canonical medication record (schemas/medication.py). */
export interface MedicationOut {
  id: string
  patient_id: string
  name: string
  dose: string | null
  frequency: string | null
  note: string | null
  created_at: string
  lifecycle_status: string
  verification_status: string
  source_type: string
  medication_category: string
  status_reason: string | null
}

/** Envelope returned by GET /patients/{id}/medications. */
export interface MedicationListOut {
  patient_id: string
  total: number
  items: MedicationOut[]
}

/** ScheduleOut — a structured dosing schedule (medication_schedule route). */
export interface ScheduleOut {
  id: string
  medication_id: string
  schedule_type: string
  local_dose_times: string[] | null
  status: string
  version: number
  patient_timezone: string
  start_date: string | null
  end_date: string | null
}

/** DoseOut — a single materialized dose occurrence. */
export interface DoseOut {
  id: string
  schedule_id: string
  scheduled_utc: string
  local_render: string | null
  state: string
  /** Present only on a dose the patient corrected — the system's original
   * classification is kept beside the human's. */
  corrected_from_state?: string | null
  corrected_at?: string | null
  correction_reason?: string | null
}

/** DueOut — the reminder sweep result: delivered count + due dose items. */
export interface DueOut {
  delivered: number
  items: DoseOut[]
}

/**
 * AdherenceOut — dose-occurrence-based adherence for one schedule.
 *
 * The legacy `total/taken/skipped/missed` quartet is still sent, but it cannot
 * describe the period it was computed over and cannot say whether that period
 * was reconcilable at all. NEVER render `adherence_rate` when `reconciled` is
 * false: an unreconciled rate is not a rougher version of the same number, it is
 * a different quantity — how often the patient opened the app.
 */
export interface AdherenceOut {
  expected_count: number
  taken_count: number
  skipped_count: number
  missed_count: number
  future_count: number
  /**
   * Doses excluded because the schedule was PAUSED — a hold the patient was
   * instructed to observe. Must never be shown as non-adherence: a patient who
   * followed a doctor's instruction did not miss anything.
   */
  excluded_paused_count: number
  /** Doses excluded because the prescription was withdrawn or superseded. */
  excluded_cancelled_count: number
  adherence_rate: number | null
  period_start: string
  period_end: string
  timezone: string
  calculation_version: string
  reconciled: boolean
  reconciliation_reason: string
  /** The backfill floor applied — adherence starts here, not at `start_date`. */
  tracking_start_at: string | null
  grace_policy: { version: string; missed_after_hours: number | null }

  /** Legacy aliases, same numbers. */
  total: number
  taken: number
  skipped: number
  missed: number
}

/**
 * Reasons a patient may give for correcting a missed dose. Closed vocabulary:
 * free text would put their account of their own symptoms into an audit trail
 * built to avoid PHI. Every label records what happened; none advises whether to
 * take a late dose.
 */
export const DOSE_CORRECTION_REASONS = [
  { code: 'taken_late', label: 'Tôi đã uống muộn hơn giờ nhắc' },
  { code: 'taken_not_recorded', label: 'Tôi đã uống nhưng quên ghi nhận' },
  { code: 'deliberately_skipped', label: 'Tôi chủ động bỏ liều này' },
  { code: 'recorded_in_error', label: 'Ghi nhận này không đúng' },
  { code: 'other', label: 'Lý do khác' },
] as const

export type DoseCorrectionReason = (typeof DOSE_CORRECTION_REASONS)[number]['code']

/** List the patient's active medication records. */
export function listMedications(
  client: ApiClient,
  patientId: string
): Promise<MedicationListOut> {
  return client.get<MedicationListOut>(`/patients/${patientId}/medications`)
}

/** List every schedule (all versions) for one medication, newest first. */
export function listSchedules(
  client: ApiClient,
  patientId: string,
  medicationId: string
): Promise<ScheduleOut[]> {
  return client.get<ScheduleOut[]>(
    `/patients/${patientId}/medications/${medicationId}/schedule`
  )
}

/**
 * Fetch the doses due now across all active schedules. NOTE: this endpoint has
 * side effects server-side (materializes newly-due doses, sweeps overdue ones to
 * MISSED, and delivers in-app reminders) — it is the canonical read for the
 * reminder surface.
 */
export function getRemindersDue(client: ApiClient, patientId: string): Promise<DueOut> {
  return client.get<DueOut>(`/patients/${patientId}/reminders/due`)
}

/** Mark a due dose as taken. */
export function markDoseTaken(
  client: ApiClient,
  patientId: string,
  doseId: string
): Promise<DoseOut> {
  return client.post<DoseOut>(`/patients/${patientId}/doses/${doseId}/taken`)
}

/** Mark a due dose as skipped, with the patient's reason. */
export function markDoseSkipped(
  client: ApiClient,
  patientId: string,
  doseId: string,
  skipReason: string
): Promise<DoseOut> {
  return client.post<DoseOut>(`/patients/${patientId}/doses/${doseId}/skipped`, {
    skip_reason: skipReason,
  })
}

/** Per-schedule adherence summary (reflects the taken/skipped/missed doses). */
export function getScheduleAdherence(
  client: ApiClient,
  patientId: string,
  scheduleId: string
): Promise<AdherenceOut> {
  return client.get<AdherenceOut>(
    `/patients/${patientId}/schedules/${scheduleId}/adherence`
  )
}

/**
 * Doses the system classified as MISSED, newest first.
 *
 * MISSED is assigned by a clock — nobody asserted it. Until this existed the row
 * appeared in no list, so the client could not obtain its id and the patient had
 * no way to say "I took that". An adherence figure a patient cannot correct is
 * not a measurement of the patient.
 */
export function listMissedDoses(
  client: ApiClient,
  patientId: string,
  scheduleId?: string,
  limit = 100
): Promise<DoseOut[]> {
  const query = scheduleId
    ? `?schedule_id=${encodeURIComponent(scheduleId)}&limit=${limit}`
    : `?limit=${limit}`
  return client.get<DoseOut[]>(`/patients/${patientId}/doses/missed${query}`)
}

/**
 * Record what actually happened to a dose the system marked missed.
 *
 * Records; does not advise. Whether to take a late dose is a clinical decision
 * this app does not make. Only a MISSED dose is correctable and a correction
 * cannot be corrected — the backend answers 422 rather than silently overwriting.
 */
export function correctDose(
  client: ApiClient,
  patientId: string,
  doseId: string,
  state: 'taken' | 'skipped',
  reasonCode: DoseCorrectionReason = 'other'
): Promise<DoseOut> {
  return client.post<DoseOut>(`/patients/${patientId}/doses/${doseId}/correct`, {
    state,
    reason_code: reasonCode,
  })
}
