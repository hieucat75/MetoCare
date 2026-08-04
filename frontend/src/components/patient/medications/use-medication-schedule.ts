'use client'

import * as React from 'react'
import {
  getMedicationSchedules,
  getRemindersDue,
  getScheduleAdherence,
  markDoseSkipped,
  markDoseTaken,
  type DoseOccurrence,
  type MedicationSchedule,
  type ScheduleAdherence,
} from '@/lib/api/medication-schedule'
import { ApiError } from '@/lib/api/client'

export type SchedulePhase = 'loading' | 'ready' | 'error'

export interface MedicationScheduleState {
  phase: SchedulePhase
  errorMessage: string | null
  schedules: MedicationSchedule[]
  /** Doses due NOW that belong to THIS medication, earliest first. */
  dueDoses: DoseOccurrence[]
  /** Earliest due dose for this medication, or `null` when nothing is due. */
  nextDue: DoseOccurrence | null
  /** Counts summed across this medication's schedules; `null` while unavailable. */
  adherence: ScheduleAdherence | null
  /** True while a taken/skipped write is in flight — blocks re-entrant submits. */
  isSubmitting: boolean
  actionError: string | null
  markTaken: (doseId: string) => Promise<void>
  markSkipped: (doseId: string, reason?: string) => Promise<void>
  reload: () => Promise<void>
}

const GENERIC_LOAD_ERROR = 'Không thể tải lịch uống thuốc. Vui lòng thử lại.'
const GENERIC_ACTION_ERROR = 'Không ghi được liều. Vui lòng thử lại.'

/**
 * Resolve the message shown to the patient for a failed dose action.
 *
 * Distinguishing the statuses matters clinically: a 409 means the backend already
 * recorded this dose, so telling the patient "thử lại" would invite a double entry
 * they cannot see. A 403/404 means the dose is not actionable at all.
 */
function actionErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return 'Liều này đã được ghi nhận trước đó.'
    if (err.status === 404) return 'Không tìm thấy liều này. Hãy tải lại trang.'
    if (err.status === 403) return 'Bạn không có quyền ghi nhận liều này.'
    if (err.status === 429) return 'Bạn thao tác quá nhanh. Vui lòng thử lại sau giây lát.'
    if (err.status >= 500) return 'Hệ thống đang bận. Vui lòng thử lại sau.'
    return err.detail || GENERIC_ACTION_ERROR
  }
  return GENERIC_ACTION_ERROR
}

/**
 * Sum per-schedule adherence into one figure for the medication.
 *
 * The backend deliberately scopes `AdherenceOut` to a single schedule; a medication
 * can carry several (an edit creates a new version rather than mutating history).
 * The rate is recomputed from the summed RESOLVED doses — averaging the per-schedule
 * rates would weight a 1-dose schedule the same as a 90-dose one.
 */
function combineAdherence(parts: ScheduleAdherence[]): ScheduleAdherence | null {
  if (parts.length === 0) return null
  const total = parts.reduce((n, p) => n + p.total, 0)
  const taken = parts.reduce((n, p) => n + p.taken, 0)
  const skipped = parts.reduce((n, p) => n + p.skipped, 0)
  const missed = parts.reduce((n, p) => n + p.missed, 0)
  const resolved = taken + skipped + missed
  return {
    total,
    taken,
    skipped,
    missed,
    adherence_rate: resolved > 0 ? Math.round((taken / resolved) * 1000) / 1000 : null,
  }
}

/**
 * Loads the Journey-3 schedule / due-dose / adherence view for one medication.
 *
 * `/reminders/due` is patient-wide and has server-side effects (materialize, sweep
 * to missed, deliver reminders), so it is fetched once per load and then filtered
 * down to this medication's schedule ids — the same derivation the mobile client
 * uses in `useMedicationDetail`. It is never polled.
 */
export function useMedicationSchedule(
  patientId: string | null | undefined,
  medicationId: string
): MedicationScheduleState {
  const [phase, setPhase] = React.useState<SchedulePhase>('loading')
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)
  const [schedules, setSchedules] = React.useState<MedicationSchedule[]>([])
  const [dueDoses, setDueDoses] = React.useState<DoseOccurrence[]>([])
  const [adherence, setAdherence] = React.useState<ScheduleAdherence | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const [actionError, setActionError] = React.useState<string | null>(null)

  // Guards a re-entrant submit even before React has flushed `isSubmitting`
  // (double-click / Enter-repeat land in the same tick).
  const submitLock = React.useRef(false)

  const reload = React.useCallback(async () => {
    if (!patientId || !medicationId) {
      setPhase('error')
      setErrorMessage(GENERIC_LOAD_ERROR)
      return
    }
    setPhase('loading')
    setErrorMessage(null)
    try {
      const [scheduleRows, due] = await Promise.all([
        getMedicationSchedules(patientId, medicationId),
        getRemindersDue(patientId),
      ])

      const scheduleIds = new Set(scheduleRows.map((s) => s.id))
      const mine = due.items
        .filter((d) => scheduleIds.has(d.schedule_id))
        .sort((a, b) => a.scheduled_utc.localeCompare(b.scheduled_utc))

      // Adherence is per-schedule; one failed part must not blank the whole figure.
      const parts = await Promise.all(
        scheduleRows.map((s) => getScheduleAdherence(patientId, s.id).catch(() => null))
      )

      setSchedules(scheduleRows)
      setDueDoses(mine)
      setAdherence(combineAdherence(parts.filter((p): p is ScheduleAdherence => p !== null)))
      setPhase('ready')
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.detail : GENERIC_LOAD_ERROR)
      setPhase('error')
    }
  }, [patientId, medicationId])

  React.useEffect(() => {
    void reload()
  }, [reload])

  const submit = React.useCallback(
    async (run: () => Promise<unknown>) => {
      if (submitLock.current || !patientId) return
      submitLock.current = true
      setIsSubmitting(true)
      setActionError(null)
      try {
        await run()
        // Re-read rather than patching local state: the backend owns the dose state
        // machine, and a taken dose also moves the adherence denominator.
        await reload()
      } catch (err) {
        setActionError(actionErrorMessage(err))
      } finally {
        submitLock.current = false
        setIsSubmitting(false)
      }
    },
    [patientId, reload]
  )

  const markTaken = React.useCallback(
    async (doseId: string) => {
      if (!patientId) return
      await submit(() => markDoseTaken(patientId, doseId))
    },
    [patientId, submit]
  )

  const markSkipped = React.useCallback(
    async (doseId: string, reason?: string) => {
      if (!patientId) return
      await submit(() => markDoseSkipped(patientId, doseId, reason))
    },
    [patientId, submit]
  )

  return {
    phase,
    errorMessage,
    schedules,
    dueDoses,
    nextDue: dueDoses[0] ?? null,
    adherence,
    isSubmitting,
    actionError,
    markTaken,
    markSkipped,
    reload,
  }
}
