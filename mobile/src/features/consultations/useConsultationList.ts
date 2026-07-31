import { useCallback, useEffect, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import { type ConsultationOut, listConsultations } from '../../api/consultations'

type Phase = 'loading' | 'ready' | 'error'

export interface ConsultationListState {
  phase: Phase
  errorMsg?: string
  consultations: ConsultationOut[]
  reload: () => Promise<void>
}

/** Loads the current patient's consultations (backend scopes by caller). */
export function useConsultationList(client: ApiClient): ConsultationListState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [consultations, setConsultations] = useState<ConsultationOut[]>([])

  const reload = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    try {
      const rows = await listConsultations(client)
      setConsultations(rows)
      setPhase('ready')
    } catch (err) {
      setErrorMsg(toPageError(err).message)
      setPhase('error')
    }
  }, [client])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload()
  }, [reload])

  return { phase, errorMsg, consultations, reload }
}
