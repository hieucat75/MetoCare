import { useCallback, useEffect, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import {
  listMedications,
  listSchedules,
  type MedicationOut,
  type ScheduleOut,
} from '../../api/medication'
import { vi } from '../../i18n/vi'

type Phase = 'loading' | 'ready' | 'error'

/** A medication record enriched with its structured schedules (all versions). */
export interface MedicationWithSchedules extends MedicationOut {
  schedules: ScheduleOut[]
}

export interface MedicationListState {
  phase: Phase
  errorMsg?: string
  medications: MedicationWithSchedules[]
  reload: () => Promise<void>
}

/**
 * Loads the patient's active medications and, for each, its schedules so the
 * list can show a dosing summary ("next due"). A missing patientId (unresolved
 * session profile) lands in the error phase rather than issuing a bad request.
 */
export function useMedicationList(
  client: ApiClient,
  patientId: string | null | undefined
): MedicationListState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [medications, setMedications] = useState<MedicationWithSchedules[]>([])

  const reload = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    if (!patientId) {
      setErrorMsg(vi.errors.generic)
      setPhase('error')
      return
    }
    try {
      const list = await listMedications(client, patientId)
      const enriched = await Promise.all(
        list.items.map(async (med) => ({
          ...med,
          schedules: await listSchedules(client, patientId, med.id),
        }))
      )
      setMedications(enriched)
      setPhase('ready')
    } catch (err) {
      setErrorMsg(toPageError(err).message)
      setPhase('error')
    }
  }, [client, patientId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload()
  }, [reload])

  return { phase, errorMsg, medications, reload }
}
