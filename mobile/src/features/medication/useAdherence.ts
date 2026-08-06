import { useCallback, useEffect, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import { type AdherenceOut, getScheduleAdherence } from '../../api/medication'
import { vi } from '../../i18n/vi'

type Phase = 'loading' | 'ready' | 'error'

export interface AdherenceState {
  phase: Phase
  errorMsg?: string
  adherence: AdherenceOut | null
  reload: () => Promise<void>
}

/**
 * Loads the dose-occurrence-based adherence summary for a single schedule. Used
 * per-schedule on the medication detail screen so each schedule instance owns
 * one hook call (no hooks-in-a-loop).
 */
export function useAdherence(
  client: ApiClient,
  patientId: string | null | undefined,
  scheduleId: string
): AdherenceState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [adherence, setAdherence] = useState<AdherenceOut | null>(null)

  const reload = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    if (!patientId || !scheduleId) {
      setErrorMsg(vi.errors.generic)
      setPhase('error')
      return
    }
    try {
      const summary = await getScheduleAdherence(client, patientId, scheduleId)
      setAdherence(summary)
      setPhase('ready')
    } catch (err) {
      setErrorMsg(toPageError(err).message)
      setPhase('error')
    }
  }, [client, patientId, scheduleId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload()
  }, [reload])

  return { phase, errorMsg, adherence, reload }
}
