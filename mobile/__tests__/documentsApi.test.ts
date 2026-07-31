import { createApiClient } from '../src/api/client'
import { createTokenStore } from '../src/storage/tokenStore'
import {
  confirmCandidate,
  createUploadSession,
  finalizeUpload,
  hostOrigin,
  listCandidates,
  mergeCandidate,
  uploadToSignedUrl,
} from '../src/api/documents'
import type { SecureStorageAdapter } from '../src/storage/secureStore'

function memSecure(): SecureStorageAdapter {
  const mem = new Map<string, string>()
  return {
    getItem: async (k) => (mem.has(k) ? mem.get(k)! : null),
    setItem: async (k, v) => {
      mem.set(k, v)
    },
    removeItem: async (k) => {
      mem.delete(k)
    },
    getJSON: async () => null,
    setJSON: async () => {},
    isAvailable: async () => true,
  }
}

function jsonRes(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

const BASE = 'http://api.test/api/v1'

function tokensWithAccess() {
  return createTokenStore(memSecure())
}

describe('MDI documents API contract', () => {
  it('hostOrigin strips the /api/v1 suffix', () => {
    expect(hostOrigin('http://api.test/api/v1')).toBe('http://api.test')
    expect(hostOrigin('http://api.test/api/v1/')).toBe('http://api.test')
    expect(hostOrigin('http://h:8000/api/v1')).toBe('http://h:8000')
  })

  it('createUploadSession posts declared_mime + doc_type_hint and returns the session', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, {
        upload_id: 'doc-1',
        signed_put_url: '/api/v1/documents/blob/tok-123',
        method: 'PUT',
        expires_at: '2026-07-31T00:00:00Z',
        status: 'uploaded',
      })
    }) as unknown as typeof fetch
    const client = createApiClient({ baseUrl: BASE, tokens: tokensWithAccess(), fetchImpl })

    const session = await createUploadSession(client, {
      declaredMime: 'image/jpeg',
      docTypeHint: 'prescription',
    })
    expect(session.upload_id).toBe('doc-1')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/documents/upload-session')
    const sent = JSON.parse(String(calls[0]!.init?.body))
    expect(sent.declared_mime).toBe('image/jpeg')
    expect(sent.doc_type_hint).toBe('prescription')
  })

  it('uploadToSignedUrl PUTs to the HOST ORIGIN (no doubled /api/v1) with the mime', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return { ok: true, status: 204 } as Response
    }) as unknown as typeof fetch

    await uploadToSignedUrl(
      '/api/v1/documents/blob/tok-123',
      'BYTES' as unknown as BodyInit,
      'image/jpeg',
      { apiBaseUrl: BASE, fetchImpl }
    )
    // Resolved against origin, NOT the api base → exactly one /api/v1, from the token url.
    expect(calls[0]!.url).toBe('http://api.test/api/v1/documents/blob/tok-123')
    expect(calls[0]!.init?.method).toBe('PUT')
    expect((calls[0]!.init?.headers as Record<string, string>)['Content-Type']).toBe('image/jpeg')
  })

  it('uploadToSignedUrl throws on a non-2xx response', async () => {
    const fetchImpl = jest.fn(
      async () => ({ ok: false, status: 403 }) as Response
    ) as unknown as typeof fetch
    await expect(
      uploadToSignedUrl('/api/v1/documents/blob/x', 'B' as unknown as BodyInit, 'image/png', {
        apiBaseUrl: BASE,
        fetchImpl,
      })
    ).rejects.toThrow(/403/)
  })

  it('finalize / listCandidates / confirm / merge hit the right paths + bodies', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (url.endsWith('/finalize')) return jsonRes(200, { id: 'doc-1', status: 'needs_review' })
      if (url.endsWith('/candidates'))
        return jsonRes(200, { document_id: 'doc-1', total: 1, items: [{ id: 'c1' }] })
      if (url.endsWith('/confirm'))
        return jsonRes(200, {
          candidate: { id: 'c1', status: 'confirmed' },
          promotion: { action: 'created' },
        })
      if (url.endsWith('/merge'))
        return jsonRes(200, {
          candidate: { id: 'c1', status: 'merged' },
          promotion: { action: 'merged_into' },
        })
      return jsonRes(200, {})
    }) as unknown as typeof fetch
    const client = createApiClient({ baseUrl: BASE, tokens: tokensWithAccess(), fetchImpl })

    await finalizeUpload(client, 'doc-1')
    await listCandidates(client, 'doc-1')
    const confirmed = await confirmCandidate(client, 'c1', { strength: '850mg' })
    const merged = await mergeCandidate(client, 'c1', 'med-9')

    expect(calls.map((c) => c.url)).toEqual([
      'http://api.test/api/v1/documents/doc-1/finalize',
      'http://api.test/api/v1/documents/doc-1/candidates',
      'http://api.test/api/v1/candidates/c1/confirm',
      'http://api.test/api/v1/candidates/c1/merge',
    ])
    expect(confirmed.promotion.action).toBe('created')
    expect(merged.promotion.action).toBe('merged_into')
    expect(JSON.parse(String(calls[2]!.init?.body)).corrections).toEqual({ strength: '850mg' })
    expect(JSON.parse(String(calls[3]!.init?.body)).merge_target_id).toBe('med-9')
  })
})
