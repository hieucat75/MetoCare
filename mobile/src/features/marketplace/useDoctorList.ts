import { useCallback, useEffect, useMemo, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import { type DoctorCardOut, listDoctors } from '../../api/marketplace'

type Phase = 'loading' | 'ready' | 'error'

export interface DoctorListState {
  phase: Phase
  errorMsg?: string
  /** All doctors returned by the server (unfiltered). */
  doctors: DoctorCardOut[]
  /** Doctors after the local name + specialty filter is applied. */
  visible: DoctorCardOut[]
  /** Distinct specialties present in the loaded set (for filter chips). */
  specialties: string[]
  search: string
  specialty: string | null
  setSearch: (value: string) => void
  setSpecialty: (value: string | null) => void
  reload: () => Promise<void>
}

/**
 * Loads the verified-doctor list once, then filters client-side by name
 * (case-insensitive substring) and specialty so search/filter feel instant.
 * Everything routes through the injected ApiClient so it is unit-testable.
 */
export function useDoctorList(client: ApiClient): DoctorListState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [doctors, setDoctors] = useState<DoctorCardOut[]>([])
  const [search, setSearch] = useState('')
  const [specialty, setSpecialty] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    try {
      const rows = await listDoctors(client)
      setDoctors(rows)
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

  const specialties = useMemo(() => {
    const set = new Set<string>()
    for (const d of doctors) {
      if (d.specialty) set.add(d.specialty)
    }
    return Array.from(set).sort()
  }, [doctors])

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    return doctors.filter((d) => {
      if (specialty && d.specialty !== specialty) return false
      if (q && !d.full_name.toLowerCase().includes(q)) return false
      return true
    })
  }, [doctors, search, specialty])

  return {
    phase,
    errorMsg,
    doctors,
    visible,
    specialties,
    search,
    specialty,
    setSearch,
    setSpecialty,
    reload,
  }
}
