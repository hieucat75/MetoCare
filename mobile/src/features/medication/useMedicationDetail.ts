import { useCallback, useEffect, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import {
  type DoseOut,
  getRemindersDue,
  listMedications,
  listSchedules,
  type MedicationOut,
  type ScheduleOut,
} from '../../api/medication'
import { vi } from '../../i18n/vi'

type Phase = 'loading' | 'ready' | 'error'

export interface MedicationDetailState {
  phase: Phase
  errorMsg?: string
  medication: MedicationOut | null
  schedules: ScheduleOut[]
  /** Earliest due-now dose belonging to any of this medication's schedules. */
  nextDue: DoseOut | null
  reload: () => Promise<void>
}

/**
 * Loads one medication's detail. The backend exposes no single-medication GET,
 * so the record is resolved from the list; schedules come from the schedule
 * endpoint, and the next due dose is derived by intersecting the patient's due
 * doses with this medication's schedule ids.
 */
export function useMedicationDetail(
  client: ApiClient,
  patientId: string | null | undefined,
  medicationId: string
): MedicationDetailState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [medication, setMedication] = useState<MedicationOut | null>(null)
  const [schedules, setSchedules] = useState<ScheduleOut[]>([])
  const [nextDue, setNextDue] = useState<DoseOut | null>(null)

  const reload = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    if (!patientId || !medicationId) {
      setErrorMsg(vi.errors.generic)
      setPhase('error')
      return
    }
    try {
      const [list, scheduleRows, due] = await Promise.all([
        listMedications(client, patientId),
        listSchedules(client, patientId, medicationId),
        getRemindersDue(client, patientId),
      ])
      const med = list.items.find((m) => m.id === medicationId) ?? null
      if (!med) {
        setErrorMsg(vi.errors.generic)
        setPhase('error')
        return
      }
      const scheduleIds = new Set(scheduleRows.map((s) => s.id))
      const dueForMed = due.items
        .filter((d) => scheduleIds.has(d.schedule_id))
        .sort((a, b) => a.scheduled_utc.localeCompare(b.scheduled_utc))
      setMedication(med)
      setSchedules(scheduleRows)
      setNextDue(dueForMed[0] ?? null)
      setPhase('ready')
    } catch (err) {
      setErrorMsg(toPageError(err).message)
      setPhase('error')
    }
  }, [client, patientId, medicationId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload()
  }, [reload])

  return { phase, errorMsg, medication, schedules, nextDue, reload }
}
