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
  /**
   * True when at least one per-schedule adherence read failed, so `adherence` is
   * computed from an incomplete set. The figure must then be qualified in the UI:
   * a missing part is usually a schedule carrying MISSED doses, so silently
   * dropping it inflates the rate.
   */
  isAdherencePartial: boolean
  /** First day of the period the figure actually covers (`period_start`). */
  adherenceSince: string | null
  /** Last day of that period (`period_end`). */
  adherenceUntil: string | null
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
 * Distinguishing the statuses matters clinically: telling a patient "thử lại" when
 * the dose was in fact already recorded invites a double entry they cannot see.
 *
 * Note on the already-recorded case: `mark_dose` raises `InvalidSchedule("Liều đã
 * được ghi nhận.")`, and `_map_err` maps every non-NotFound/non-AccessDenied
 * ScheduleError to **422** — not 409 (backend/app/api/v1/routes/
 * medication_schedule.py::_map_err). So that case arrives as a 422 and is surfaced
 * through the backend's own Vietnamese `detail`, which already says exactly that.
 * The 409 branch is kept as a forward-compatible mapping in case the backend later
 * adopts the more conventional conflict status; it does not fire today.
 */
function actionErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return 'Liều này đã được ghi nhận trước đó.'
    if (err.status === 404) return 'Không tìm thấy liều này. Hãy tải lại trang.'
    if (err.status === 403) return 'Bạn không có quyền ghi nhận liều này.'
    if (err.status === 429) return 'Bạn thao tác quá nhanh. Vui lòng thử lại sau giây lát.'
    if (err.status >= 500) return 'Hệ thống đang bận. Vui lòng thử lại sau.'
    // 422 lands here: the backend detail is the authoritative, already-localised
    // explanation (e.g. "Liều đã được ghi nhận.").
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
  const sum = (pick: (p: ScheduleAdherence) => number) => parts.reduce((n, p) => n + pick(p), 0)

  const taken = sum((p) => p.taken_count)
  const skipped = sum((p) => p.skipped_count)
  const missed = sum((p) => p.missed_count)
  const resolved = taken + skipped + missed

  // A combined figure is only as trustworthy as its LEAST trustworthy part. If
  // any schedule could not be reconciled its doses are missing from the sum, and
  // dividing by what remains publishes exactly the engagement-derived number the
  // backend now withholds — under an aggregate that looks complete.
  const reconciled = parts.every((p) => p.reconciled)
  const unreconciled = parts.find((p) => !p.reconciled)

  const sorted = (pick: (p: ScheduleAdherence) => string) =>
    parts.map(pick).filter(Boolean).sort()
  const floors = parts
    .map((p) => p.tracking_start_at)
    .filter((v): v is string => Boolean(v))
    .sort()

  return {
    expected_count: sum((p) => p.expected_count),
    taken_count: taken,
    skipped_count: skipped,
    missed_count: missed,
    future_count: sum((p) => p.future_count),
    excluded_paused_count: sum((p) => p.excluded_paused_count),
    excluded_cancelled_count: sum((p) => p.excluded_cancelled_count),
    adherence_rate:
      reconciled && resolved > 0 ? Math.round((taken / resolved) * 1000) / 1000 : null,
    // The union of the parts' windows — the period the summed figure describes.
    period_start: sorted((p) => p.period_start)[0] ?? '',
    period_end: sorted((p) => p.period_end).slice(-1)[0] ?? '',
    timezone: parts[0].timezone,
    calculation_version: parts[0].calculation_version,
    reconciled,
    reconciliation_reason: unreconciled?.reconciliation_reason ?? 'reconciled',
    tracking_start_at: floors[0] ?? null,
    grace_policy: parts[0].grace_policy,

    total: sum((p) => p.expected_count),
    taken,
    skipped,
    missed,
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
  const [isAdherencePartial, setIsAdherencePartial] = React.useState(false)
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const [actionError, setActionError] = React.useState<string | null>(null)

  // Guards a re-entrant submit even before React has flushed `isSubmitting`
  // (double-click / Enter-repeat land in the same tick).
  const submitLock = React.useRef(false)

  // Monotonic request token. The App Router REUSES this page component when only
  // the [id] segment changes, so navigating medication A -> B keeps the same hook
  // instance alive with two loads in flight. Without this guard a slow A response
  // landing after a fast B response would leave B's name in the header above A's
  // schedule, due dose and adherence — and "Đã uống" would then act on A's dose.
  const requestToken = React.useRef(0)

  const reload = React.useCallback(async () => {
    if (!patientId || !medicationId) {
      setPhase('error')
      setErrorMessage(GENERIC_LOAD_ERROR)
      return
    }
    const token = ++requestToken.current
    const isStale = () => requestToken.current !== token

    setPhase('loading')
    setErrorMessage(null)
    try {
      const [scheduleRows, due] = await Promise.all([
        getMedicationSchedules(patientId, medicationId),
        getRemindersDue(patientId),
      ])
      if (isStale()) return

      const scheduleIds = new Set(scheduleRows.map((s) => s.id))
      const mine = due.items
        .filter((d) => scheduleIds.has(d.schedule_id))
        .sort((a, b) => a.scheduled_utc.localeCompare(b.scheduled_utc))

      // Adherence is per-schedule; one failed part must not blank the whole figure.
      const parts = await Promise.all(
        scheduleRows.map((s) => getScheduleAdherence(patientId, s.id).catch(() => null))
      )
      if (isStale()) return

      const resolved = parts.filter((p): p is ScheduleAdherence => p !== null)
      setSchedules(scheduleRows)
      setDueDoses(mine)
      setAdherence(combineAdherence(resolved))
      setIsAdherencePartial(resolved.length < parts.length)
      setPhase('ready')
    } catch (err) {
      if (isStale()) return
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

  // The period the figure ACTUALLY covers, taken from the response.
  //
  // This used to be the earliest `start_date` across the schedules, and the card
  // rendered "kể từ {that date}". The backend computes over a bounded window
  // floored at `tracking_start_at`, so the label claimed a span the number never
  // described — a patient whose prescription began in March read "kể từ 01/03"
  // over a 30-day figure. `start_date` is when the PRESCRIPTION began; it is not
  // when this app started counting, and only the response knows the difference.
  const adherenceSince = adherence?.period_start ?? null
  const adherenceUntil = adherence?.period_end ?? null

  return {
    phase,
    errorMessage,
    schedules,
    dueDoses,
    nextDue: dueDoses[0] ?? null,
    adherence,
    isAdherencePartial,
    adherenceSince,
    adherenceUntil,
    isSubmitting,
    actionError,
    markTaken,
    markSkipped,
    reload,
  }
}
