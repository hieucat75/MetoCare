import { useCallback, useEffect, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { ApiError, toPageError } from '../../api/client'
import {
  type ConsultationOut,
  getConsultation,
  listNotes,
  type NoteOut,
  submitReview as apiSubmitReview,
} from '../../api/consultations'

type Phase = 'loading' | 'ready' | 'error'
type ReviewPhase = 'idle' | 'submitting' | 'submitted' | 'error'

export interface ConsultationDetailState {
  phase: Phase
  errorMsg?: string
  consultation: ConsultationOut | null
  notes: NoteOut[]
  reviewPhase: ReviewPhase
  reviewError?: string
  reload: () => Promise<void>
  submitReview: (rating: number, feedback?: string) => Promise<void>
}

/**
 * Loads one consultation plus its doctor notes (read-only for the patient), and
 * lets the patient submit a review. On a successful review the state flips to
 * 'submitted' in place (like useDocumentReview's per-item update) — no full
 * reload needed.
 */
export function useConsultationDetail(
  client: ApiClient,
  consultationId: string
): ConsultationDetailState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [consultation, setConsultation] = useState<ConsultationOut | null>(null)
  const [notes, setNotes] = useState<NoteOut[]>([])
  const [reviewPhase, setReviewPhase] = useState<ReviewPhase>('idle')
  const [reviewError, setReviewError] = useState<string | undefined>(undefined)

  const reload = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    try {
      // The consultation itself is the primary resource. Notes are OPTIONAL
      // ONLY for the documented 403 case: the backend returns 403 ("available
      // only after the consultation is completed") until completion, which must
      // NOT fail the whole detail view for a freshly-booked (REQUESTED)
      // consultation — just show no notes yet. Any OTHER failure (5xx, network,
      // 401 forced-logout) is a genuine error and must surface via the outer
      // catch, not be silently masked as an empty "no notes" state.
      const detail = await getConsultation(client, consultationId)
      setConsultation(detail)
      let noteRows: NoteOut[] = []
      try {
        noteRows = await listNotes(client, consultationId)
      } catch (err) {
        if (err instanceof ApiError && err.status === 403) {
          noteRows = []
        } else {
          throw err
        }
      }
      setNotes(noteRows)
      setPhase('ready')
    } catch (err) {
      setErrorMsg(toPageError(err).message)
      setPhase('error')
    }
  }, [client, consultationId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload()
  }, [reload])

  const submitReview = useCallback(
    async (rating: number, feedback?: string) => {
      setReviewPhase('submitting')
      setReviewError(undefined)
      try {
        const trimmed = feedback?.trim()
        await apiSubmitReview(client, consultationId, {
          rating,
          feedback: trimmed ? trimmed : null,
        })
        setReviewPhase('submitted')
      } catch (err) {
        setReviewError(toPageError(err).message)
        setReviewPhase('error')
      }
    },
    [client, consultationId]
  )

  return {
    phase,
    errorMsg,
    consultation,
    notes,
    reviewPhase,
    reviewError,
    reload,
    submitReview,
  }
}
