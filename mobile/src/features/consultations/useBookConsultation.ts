import { useCallback, useRef, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import {
  type ConsultationTypeValue,
  createConsultation,
  payConsultation,
} from '../../api/consultations'

type Phase = 'idle' | 'submitting' | 'error'

export interface BookConsultationInput {
  chiefComplaint?: string
  patientNote?: string
}

export interface BookConsultationState {
  phase: Phase
  errorMsg?: string
  consentAccepted: boolean
  /** True only when consent is ticked and no submit is in flight. */
  canSubmit: boolean
  setConsentAccepted: (value: boolean) => void
  /** Creates the consultation then pays it. Returns the consultation id or null. */
  submit: (input: BookConsultationInput) => Promise<string | null>
}

/**
 * Drives the book flow: create consultation → pay. The data-sharing consent is
 * a hard gate — `canSubmit` is false and `submit` is a no-op (returns null)
 * until the patient has accepted it, matching the backend's required
 * `data_consent_accepted` field. Trims free-text and omits empty values.
 */
export function useBookConsultation(
  client: ApiClient,
  doctorId: string,
  consultationType: ConsultationTypeValue = 'CHAT'
): BookConsultationState {
  const [phase, setPhase] = useState<Phase>('idle')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [consentAccepted, setConsentAccepted] = useState(false)
  // Synchronous re-entrancy lock: setPhase('submitting') only takes effect after
  // the current call stack unwinds, so a fast double-tap could otherwise pass the
  // `disabled`/phase check twice and create+pay two consultations (duplicate
  // charge). A ref flips synchronously, closing that window.
  const inFlightRef = useRef(false)

  const canSubmit = consentAccepted && phase !== 'submitting'

  const submit = useCallback(
    async (input: BookConsultationInput): Promise<string | null> => {
      // Hard guard: never call the API without accepted consent.
      if (!consentAccepted) return null
      if (inFlightRef.current) return null
      inFlightRef.current = true
      setPhase('submitting')
      setErrorMsg(undefined)
      try {
        const chief = input.chiefComplaint?.trim()
        const note = input.patientNote?.trim()
        const consultation = await createConsultation(client, {
          doctor_id: doctorId,
          consultation_type: consultationType,
          // Transmit the actual checkbox state (guaranteed true past the guard
          // above) — never a decoupled literal, so this stays correct if the
          // guard is ever refactored.
          data_consent_accepted: consentAccepted,
          chief_complaint: chief ? chief : null,
          patient_note: note ? note : null,
        })
        await payConsultation(client, consultation.id)
        setPhase('idle')
        return consultation.id
      } catch (err) {
        setErrorMsg(toPageError(err).message)
        setPhase('error')
        return null
      } finally {
        inFlightRef.current = false
      }
    },
    [client, doctorId, consultationType, consentAccepted]
  )

  return { phase, errorMsg, consentAccepted, canSubmit, setConsentAccepted, submit }
}
