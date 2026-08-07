import { useCallback, useRef, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import {
  type ConsultationTypeValue,
  createConsultation,
  payConsultation,
} from '../../api/consultations'
import type { ConsentGrant } from '../../components/DataSharingConsentModal'

type Phase = 'idle' | 'submitting' | 'error'

export interface BookConsultationInput {
  chiefComplaint?: string
  patientNote?: string
}

export interface BookConsultationState {
  phase: Phase
  errorMsg?: string
  /** True while no submit is in flight. Consent is not tracked here — it arrives with submit. */
  canSubmit: boolean
  /** Creates the consultation then pays it. Returns the consultation id or null. */
  submit: (grant: ConsentGrant, input: BookConsultationInput) => Promise<string | null>
  /** Clears a previous failure so a dismissed dialog does not reopen showing it. */
  reset: () => void
}

/**
 * Drives the book flow: create consultation → pay.
 *
 * Consent is not a boolean this hook holds and later trusts. `submit` requires
 * a `ConsentGrant` — the categories and versions the patient actually saw — so
 * there is no state that could drift out of sync with the dialog, and no way to
 * book without having gone through it.
 */
export function useBookConsultation(
  client: ApiClient,
  doctorId: string,
  consultationType: ConsultationTypeValue = 'CHAT',
  appVersion?: string
): BookConsultationState {
  const [phase, setPhase] = useState<Phase>('idle')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  // Synchronous re-entrancy lock: setPhase('submitting') only takes effect after
  // the current call stack unwinds, so a fast double-tap could otherwise pass the
  // `disabled`/phase check twice and create+pay two consultations (duplicate
  // charge). A ref flips synchronously, closing that window.
  const inFlightRef = useRef(false)

  const canSubmit = phase !== 'submitting'

  const reset = useCallback(() => {
    setErrorMsg(undefined)
    setPhase('idle')
  }, [])

  const submit = useCallback(
    async (grant: ConsentGrant, input: BookConsultationInput): Promise<string | null> => {
      if (inFlightRef.current) return null
      // A grant with no categories is not consent — refuse rather than send it.
      if (!grant || grant.categories.length === 0) return null
      inFlightRef.current = true
      setPhase('submitting')
      setErrorMsg(undefined)
      try {
        const chief = input.chiefComplaint?.trim()
        const note = input.patientNote?.trim()
        const consultation = await createConsultation(client, {
          doctor_id: doctorId,
          consultation_type: consultationType,
          data_consent_accepted: true,
          data_sharing_consent: {
            accepted: true,
            categories: grant.categories,
            consent_version: grant.consentVersion,
            policy_version: grant.policyVersion,
            source: 'mobile',
            client_app_version: appVersion,
          },
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
    [client, doctorId, consultationType, appVersion]
  )

  return { phase, errorMsg, canSubmit, submit, reset }
}
