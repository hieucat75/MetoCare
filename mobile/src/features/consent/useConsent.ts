import { useCallback, useEffect, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import { type ConsentStatus, listConsent, updateConsent } from '../../api/consent'

type Phase = 'loading' | 'ready' | 'error'

export interface ConsentState {
  phase: Phase
  errorMsg?: string
  items: ConsentStatus[]
  /** context_type currently being toggled (row is busy), or null. */
  pendingType: string | null
  reload: () => Promise<void>
  toggle: (contextType: string, granted: boolean) => Promise<void>
}

/**
 * Drives the per-category Meto consent screen (Journey 4). Loads the five
 * consent statuses, and grants/revokes an individual category — optimistically
 * flipping that row's `granted` in place, then silently re-syncing from the
 * server so `granted_at` / `policy_version` reflect the write. On failure it
 * reverts the optimistic flip and surfaces the error. Everything routes through
 * the injected ApiClient so it is unit-testable.
 */
export function useConsent(client: ApiClient): ConsentState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [items, setItems] = useState<ConsentStatus[]>([])
  const [pendingType, setPendingType] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    try {
      const rows = await listConsent(client)
      setItems(rows)
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

  const _patchGranted = useCallback((contextType: string, granted: boolean) => {
    setItems((prev) =>
      prev.map((it) => (it.context_type === contextType ? { ...it, granted } : it))
    )
  }, [])

  const toggle = useCallback(
    async (contextType: string, granted: boolean) => {
      setErrorMsg(undefined)
      setPendingType(contextType)
      _patchGranted(contextType, granted) // optimistic
      try {
        await updateConsent(client, contextType, granted)
      } catch (err) {
        // Only a FAILED mutation means the change didn't happen — revert then.
        _patchGranted(contextType, !granted)
        setErrorMsg(toPageError(err).message)
        setPendingType(null)
        return
      }
      // Mutation committed server-side. Re-sync granted_at/policy_version as a
      // best effort — a failure here must NOT revert the successful toggle
      // (that would show a consent state contradicting the server).
      try {
        const rows = await listConsent(client)
        setItems(rows)
      } catch {
        // keep the optimistic value; metadata refreshes on next load
      } finally {
        setPendingType(null)
      }
    },
    [client, _patchGranted]
  )

  return { phase, errorMsg, items, pendingType, reload, toggle }
}
