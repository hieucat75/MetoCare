import { useCallback, useEffect, useMemo, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import {
  type DoseOut,
  getRemindersDue,
  markDoseSkipped,
  markDoseTaken,
} from '../../api/medication'
import { vi } from '../../i18n/vi'

type Phase = 'loading' | 'ready' | 'error'

export interface RemindersState {
  phase: Phase
  errorMsg?: string
  doses: DoseOut[]
  /** dose id currently being marked (row is busy), or null. */
  pendingId: string | null
  /** Count of doses acted-on this session — the live adherence summary. */
  takenCount: number
  skippedCount: number
  reload: () => Promise<void>
  markTaken: (doseId: string) => Promise<void>
  markSkipped: (doseId: string, reason: string) => Promise<void>
}

/**
 * Drives the reminder / today surface: loads the doses due now and lets the
 * patient mark each taken or skipped. On success the dose's state is patched in
 * place (so the row flips to "Đã uống"/"Đã bỏ qua" without a full reload) and the
 * live taken/skipped tally updates — this tally is the on-screen adherence
 * summary. Skipping requires a non-empty reason (rejected before any request).
 */
export function useReminders(
  client: ApiClient,
  patientId: string | null | undefined
): RemindersState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [doses, setDoses] = useState<DoseOut[]>([])
  const [pendingId, setPendingId] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    if (!patientId) {
      setErrorMsg(vi.errors.generic)
      setPhase('error')
      return
    }
    try {
      const due = await getRemindersDue(client, patientId)
      setDoses(due.items)
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

  const _patchState = useCallback((doseId: string, state: string) => {
    setDoses((prev) => prev.map((d) => (d.id === doseId ? { ...d, state } : d)))
  }, [])

  const markTaken = useCallback(
    async (doseId: string) => {
      if (!patientId) return
      setErrorMsg(undefined)
      setPendingId(doseId)
      try {
        const dose = await markDoseTaken(client, patientId, doseId)
        _patchState(doseId, dose.state)
      } catch (err) {
        setErrorMsg(toPageError(err).message)
      } finally {
        setPendingId(null)
      }
    },
    [client, patientId, _patchState]
  )

  const markSkipped = useCallback(
    async (doseId: string, reason: string) => {
      if (!patientId) return
      const trimmed = reason.trim()
      if (!trimmed) {
        setErrorMsg(vi.medication.skipReasonRequired)
        return
      }
      setErrorMsg(undefined)
      setPendingId(doseId)
      try {
        const dose = await markDoseSkipped(client, patientId, doseId, trimmed)
        _patchState(doseId, dose.state)
      } catch (err) {
        setErrorMsg(toPageError(err).message)
      } finally {
        setPendingId(null)
      }
    },
    [client, patientId, _patchState]
  )

  const takenCount = useMemo(() => doses.filter((d) => d.state === 'taken').length, [doses])
  const skippedCount = useMemo(
    () => doses.filter((d) => d.state === 'skipped').length,
    [doses]
  )

  return {
    phase,
    errorMsg,
    doses,
    pendingId,
    takenCount,
    skippedCount,
    reload,
    markTaken,
    markSkipped,
  }
}
