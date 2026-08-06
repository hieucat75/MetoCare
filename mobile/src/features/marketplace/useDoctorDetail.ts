import { useCallback, useEffect, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import { type DoctorDetailOut, getDoctor } from '../../api/marketplace'

type Phase = 'loading' | 'ready' | 'error'

export interface DoctorDetailState {
  phase: Phase
  errorMsg?: string
  doctor: DoctorDetailOut | null
  reload: () => Promise<void>
}

/** Loads a single verified doctor's detail by id. */
export function useDoctorDetail(client: ApiClient, doctorId: string): DoctorDetailState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [doctor, setDoctor] = useState<DoctorDetailOut | null>(null)

  const reload = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    try {
      const row = await getDoctor(client, doctorId)
      setDoctor(row)
      setPhase('ready')
    } catch (err) {
      setErrorMsg(toPageError(err).message)
      setPhase('error')
    }
  }, [client, doctorId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload()
  }, [reload])

  return { phase, errorMsg, doctor, reload }
}
