import type { ApiClient } from '../../api/client'

/**
 * Patient self-service account API (GDPR data-subject rights).
 * Mirrors backend/app/api/v1/routes/account.py:
 *   GET    /patients/{patient_id}/export   → full JSON bundle of the caller's data
 *   DELETE /patients/{patient_id}/account  → soft-delete + anonymize, idempotent
 *
 * Both endpoints are strictly self-scoped: `patientId` MUST be the caller's own
 * `UserResponse.patient_profile_id` (the backend 403s otherwise).
 */

/** The export bundle is an open envelope of section → rows (plus scalars). */
export type ExportBundle = Record<string, unknown>

export interface DeleteAccountResult {
  status: string
  patient_id: string
}

export function exportAccountData(client: ApiClient, patientId: string): Promise<ExportBundle> {
  return client.get<ExportBundle>(`/patients/${patientId}/export`)
}

export function deleteAccountData(
  client: ApiClient,
  patientId: string
): Promise<DeleteAccountResult> {
  return client.del<DeleteAccountResult>(`/patients/${patientId}/account`)
}
