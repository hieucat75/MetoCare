import { useCallback, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import { vi } from '../../i18n/vi'
import { deleteAccountData, exportAccountData, type ExportBundle } from './accountApi'

type Phase = 'idle' | 'exporting' | 'deleting'

export interface ExportSection {
  key: string
  label: string
  count: number
}

export interface AccountActionsState {
  phase: Phase
  errorMsg?: string
  bundle: ExportBundle | null
  /** Per-section row counts — what the patient is actually taking with them. */
  exportSummary: ExportSection[] | null
  exportData: () => Promise<boolean>
  deleteAccount: () => Promise<boolean>
}

/** Turn the raw export envelope into a readable "what's in it" summary. */
export function summarizeBundle(bundle: ExportBundle): ExportSection[] {
  const sections: ExportSection[] = []
  for (const [key, value] of Object.entries(bundle)) {
    const label = vi.account.exportSection[key]
    if (!label) continue // scalars like generated_at / patient_id
    const count = Array.isArray(value) ? value.length : value ? 1 : 0
    sections.push({ key, label, count })
  }
  return sections
}

/**
 * Data export + account deletion for the signed-in patient (WS11-F5).
 *
 * `patientId` is the caller's own PatientProfile id; when it is missing the
 * actions fail loudly rather than calling a malformed path — a store-policy
 * feature must never fail silently.
 */
export function useAccountActions(
  client: ApiClient,
  patientId: string | null
): AccountActionsState {
  const [phase, setPhase] = useState<Phase>('idle')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [bundle, setBundle] = useState<ExportBundle | null>(null)
  const [exportSummary, setExportSummary] = useState<ExportSection[] | null>(null)

  const exportData = useCallback(async (): Promise<boolean> => {
    if (!patientId) {
      setErrorMsg(vi.errors.generic)
      return false
    }
    setPhase('exporting')
    setErrorMsg(undefined)
    try {
      const data = await exportAccountData(client, patientId)
      setBundle(data)
      setExportSummary(summarizeBundle(data))
      return true
    } catch (err) {
      setErrorMsg(toPageError(err).message)
      return false
    } finally {
      setPhase('idle')
    }
  }, [client, patientId])

  const deleteAccount = useCallback(async (): Promise<boolean> => {
    if (!patientId) {
      setErrorMsg(vi.errors.generic)
      return false
    }
    setPhase('deleting')
    setErrorMsg(undefined)
    try {
      await deleteAccountData(client, patientId)
      return true
    } catch (err) {
      setErrorMsg(toPageError(err).message)
      return false
    } finally {
      setPhase('idle')
    }
  }, [client, patientId])

  return { phase, errorMsg, bundle, exportSummary, exportData, deleteAccount }
}
