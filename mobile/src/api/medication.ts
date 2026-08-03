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
}

/** DueOut — the reminder sweep result: delivered count + due dose items. */
export interface DueOut {
  delivered: number
  items: DoseOut[]
}

/** AdherenceOut — dose-occurrence-based adherence for one schedule. */
export interface AdherenceOut {
  total: number
  taken: number
  skipped: number
  missed: number
  adherence_rate: number | null
}

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
