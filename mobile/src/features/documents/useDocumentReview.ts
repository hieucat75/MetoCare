import { useCallback, useEffect, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { isConsentDenied, toPageError } from '../../api/client'
import {
  type CandidateOut,
  confirmCandidate,
  listCandidates,
  rejectCandidate,
} from '../../api/documents'

type Phase = 'loading' | 'ready' | 'error'

export interface DocumentReviewState {
  phase: Phase
  candidates: CandidateOut[]
  errorMsg?: string
  /** The failure was the fail-closed `documents` consent gate — offer the consent route. */
  consentDenied: boolean
  pendingId: string | null
  reload: () => Promise<void>
  /**
   * Confirm one candidate. `corrections` carries the patient's inline edits of
   * the extracted values (e.g. a mis-read lab value/unit); the backend merges
   * them into `fields_json` and keeps the pre-correction snapshot in the
   * candidate's audit history before promoting.
   */
  confirm: (candidateId: string, corrections?: CandidateCorrections) => Promise<void>
  reject: (candidateId: string) => Promise<void>
}

export type CandidateCorrections = Record<string, string | number | null>

/**
 * Drives the per-candidate review of one document (BRD §D review screen). Loads
 * candidates, and confirms/rejects individual candidates — updating that
 * candidate's status in place on success so the UI reflects the per-item
 * decision without a full reload. Everything routes through the injected
 * ApiClient so it is unit-testable.
 */
export function useDocumentReview(client: ApiClient, documentId: string): DocumentReviewState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [candidates, setCandidates] = useState<CandidateOut[]>([])
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [consentDenied, setConsentDenied] = useState(false)

  const reload = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    setConsentDenied(false)
    try {
      const res = await listCandidates(client, documentId)
      setCandidates(res.items)
      setPhase('ready')
    } catch (err) {
      setConsentDenied(isConsentDenied(err))
      setErrorMsg(toPageError(err).message)
      setPhase('error')
    }
  }, [client, documentId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload()
  }, [reload])

  const _patchStatus = useCallback(
    (candidateId: string, status: string, fields?: Record<string, unknown>) => {
      setCandidates((prev) =>
        prev.map((c) =>
          c.id === candidateId ? { ...c, status, fields: fields ?? c.fields } : c
        )
      )
    },
    []
  )

  const confirm = useCallback(
    async (candidateId: string, corrections?: CandidateCorrections) => {
      setPendingId(candidateId)
      try {
        const res = await confirmCandidate(client, candidateId, corrections)
        // The backend returns the post-correction candidate — reflect the values
        // that were actually promoted, not the pre-correction ones.
        _patchStatus(candidateId, res.candidate.status, res.candidate.fields)
      } catch (err) {
        setConsentDenied(isConsentDenied(err))
        setErrorMsg(toPageError(err).message)
      } finally {
        setPendingId(null)
      }
    },
    [client, _patchStatus]
  )

  const reject = useCallback(
    async (candidateId: string) => {
      setPendingId(candidateId)
      try {
        const res = await rejectCandidate(client, candidateId)
        _patchStatus(candidateId, res.status)
      } catch (err) {
        setConsentDenied(isConsentDenied(err))
        setErrorMsg(toPageError(err).message)
      } finally {
        setPendingId(null)
      }
    },
    [client, _patchStatus]
  )

  return { phase, candidates, errorMsg, consentDenied, pendingId, reload, confirm, reject }
}
