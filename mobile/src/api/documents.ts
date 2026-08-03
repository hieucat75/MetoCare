import { API_BASE_URL } from '../config/env'
import type { ApiClient, FetchLike } from './client'

/**
 * Medical Document Intelligence (Journey 2) API — secure upload-session →
 * blob PUT → finalize → per-candidate review. Mirrors the backend contract in
 * backend/app/api/v1/routes/documents.py.
 *
 * Upload note: the backend returns a HOST-ABSOLUTE signed PUT url
 * (`/api/v1/documents/blob/<token>`). The ApiClient's baseUrl already ends in
 * `/api/v1`, so the blob PUT must resolve the signed url against the HOST ORIGIN
 * (baseUrl minus the `/api/v1` suffix), never against the api base — otherwise
 * the prefix doubles. `uploadToSignedUrl` does exactly that.
 */

export type DocTypeHint = 'prescription' | 'lab_report' | 'general'

export interface UploadSessionOut {
  upload_id: string
  signed_put_url: string
  method: string
  expires_at: string
  status: string
}

export interface DocumentOut {
  id: string
  doc_type: string | null
  status: string
  object_state: string
  mime: string | null
  size_bytes: number | null
  page_count: number | null
  classification_confidence: number | null
  sha256: string | null
  scan_status: string | null
  failure_reason: string | null
  superseded_by: string | null
  created_at: string
}

export interface CandidateOut {
  id: string
  document_id: string
  candidate_type: string
  ordinal: number
  fields: Record<string, unknown>
  field_confidence: Record<string, number> | null
  status: string
  dedupe_key: string
  reviewed_at: string | null
}

export interface CandidateListOut {
  document_id: string
  total: number
  items: CandidateOut[]
}

export interface PromotionOut {
  candidate_id: string
  canonical_type: string
  canonical_id: string
  action: string
}

export interface ConfirmResultOut {
  candidate: CandidateOut
  promotion: PromotionOut
}

export interface SignedFileOut {
  url: string
  method: string
  expires_at: string
}

/** Strip the trailing `/api/v1` so a host-absolute signed url resolves correctly. */
export function hostOrigin(apiBaseUrl: string = API_BASE_URL): string {
  return apiBaseUrl.replace(/\/api\/v1\/?$/, '')
}

export function createUploadSession(
  client: ApiClient,
  input: {
    declaredMime: string
    docTypeHint?: DocTypeHint
    declaredSha256?: string
    declaredSize?: number
  }
): Promise<UploadSessionOut> {
  return client.post<UploadSessionOut>('/documents/upload-session', {
    declared_mime: input.declaredMime,
    doc_type_hint: input.docTypeHint,
    declared_sha256: input.declaredSha256,
    declared_size: input.declaredSize,
  })
}

/**
 * PUT raw bytes to the signed url. `body` is anything RN fetch accepts as a PUT
 * body (Blob, ArrayBuffer, or a `{ uri }`-style file object). `fetchImpl` is
 * injectable for tests. Resolves on 2xx, throws otherwise.
 */
export async function uploadToSignedUrl(
  signedPutUrl: string,
  body: BodyInit,
  mime: string,
  opts: { apiBaseUrl?: string; fetchImpl?: FetchLike } = {}
): Promise<void> {
  const origin = hostOrigin(opts.apiBaseUrl ?? API_BASE_URL)
  const doFetch = opts.fetchImpl ?? fetch
  const res = await doFetch(`${origin}${signedPutUrl}`, {
    method: 'PUT',
    headers: { 'Content-Type': mime },
    body,
  })
  if (!res.ok) {
    throw new Error(`Tải tệp lên thất bại (HTTP ${res.status}).`)
  }
}

export function finalizeUpload(client: ApiClient, uploadId: string): Promise<DocumentOut> {
  return client.post<DocumentOut>(`/documents/${uploadId}/finalize`)
}

/**
 * QA-only: ask the backend to ingest a bundled synthetic document through the
 * real pipeline and return the resulting needs_review document. Only reachable
 * on dev/staging builds where the backend has `qa_fixture_enabled` on; the
 * endpoint 404s otherwise (and can never be enabled in production).
 */
export function createQaFixtureDocument(client: ApiClient): Promise<DocumentOut> {
  return client.post<DocumentOut>('/documents/qa-fixture')
}

export function listCandidates(client: ApiClient, documentId: string): Promise<CandidateListOut> {
  return client.get<CandidateListOut>(`/documents/${documentId}/candidates`)
}

export function getDocument(client: ApiClient, documentId: string): Promise<DocumentOut> {
  return client.get<DocumentOut>(`/documents/${documentId}`)
}

export function confirmCandidate(
  client: ApiClient,
  candidateId: string,
  corrections?: Record<string, string | number | null>
): Promise<ConfirmResultOut> {
  return client.post<ConfirmResultOut>(`/candidates/${candidateId}/confirm`, {
    corrections: corrections ?? null,
  })
}

export function rejectCandidate(client: ApiClient, candidateId: string): Promise<CandidateOut> {
  return client.post<CandidateOut>(`/candidates/${candidateId}/reject`)
}

export function mergeCandidate(
  client: ApiClient,
  candidateId: string,
  mergeTargetId: string,
  corrections?: Record<string, string | number | null>
): Promise<ConfirmResultOut> {
  return client.post<ConfirmResultOut>(`/candidates/${candidateId}/merge`, {
    merge_target_id: mergeTargetId,
    corrections: corrections ?? null,
  })
}

export function getDocumentFileUrl(client: ApiClient, documentId: string): Promise<SignedFileOut> {
  return client.get<SignedFileOut>(`/documents/${documentId}/file`)
}
