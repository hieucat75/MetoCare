import type { ApiClient } from './client'

/**
 * Meto per-category consent API (Journey 4) — patient-facing read + toggle of
 * the five consent categories that gate what data Meto (and downstream flows)
 * may use. Mirrors the backend contract in
 * backend/app/api/v1/routes/meto.py (GET/POST /meto/consent).
 *
 * The ApiClient baseUrl already ends in `/api/v1`, so paths are `/meto/consent`.
 * `purpose` copy is authored server-side (per policy version) and rendered
 * verbatim — it is NOT duplicated in i18n.
 */

/** The five consent categories the backend recognises. */
export type ConsentContextType =
  | 'ai_processing'
  | 'health_records'
  | 'medications'
  | 'documents'
  | 'doctor_consultation'

export interface ConsentStatus {
  context_type: string
  granted: boolean
  granted_at: string | null
  policy_version: string | null
  purpose: string
}

export interface ConsentUpdateResult {
  status: string
  context_type: string
  action: string
}

/** Load the current patient's consent status for all categories. */
export function listConsent(client: ApiClient): Promise<ConsentStatus[]> {
  return client.get<ConsentStatus[]>('/meto/consent')
}

/** Grant or revoke consent for a single category. */
export function updateConsent(
  client: ApiClient,
  context_type: string,
  granted: boolean
): Promise<ConsentUpdateResult> {
  return client.post<ConsentUpdateResult>('/meto/consent', { context_type, granted })
}
