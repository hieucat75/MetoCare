import { act, renderHook, waitFor } from '@testing-library/react-native'

import type { ApiClient } from '../src/api/client'
import { useAddDocument } from '../src/features/documents/useAddDocument'
import { useDocumentReview } from '../src/features/documents/useDocumentReview'

function fakeClient(overrides: Partial<Record<keyof ApiClient, unknown>> = {}): ApiClient {
  return {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    put: jest.fn(),
    del: jest.fn(),
    apiFetch: jest.fn(),
    tokens: {} as ApiClient['tokens'],
    ...overrides,
  } as ApiClient
}

describe('useDocumentReview', () => {
  it('loads candidates then confirms one, updating its status in place', async () => {
    const get = jest.fn(async () => ({
      document_id: 'doc-1',
      total: 2,
      items: [
        { id: 'c1', status: 'needs_review', fields: { name: 'Metformin' } },
        { id: 'c2', status: 'needs_review', fields: { name: 'Amlodipine' } },
      ],
    }))
    const post = jest.fn(async () => ({
      candidate: { id: 'c1', status: 'confirmed' },
      promotion: { action: 'created', canonical_id: 'med-1', canonical_type: 'medication' },
    }))
    const client = fakeClient({ get, post })

    const { result } = await renderHook(() => useDocumentReview(client, 'doc-1'))
    await waitFor(() => expect(result.current.phase).toBe('ready'))
    expect(result.current.candidates).toHaveLength(2)

    await act(async () => {
      await result.current.confirm('c1')
    })
    expect(post).toHaveBeenCalledWith('/candidates/c1/confirm', { corrections: null })
    expect(result.current.candidates.find((c) => c.id === 'c1')?.status).toBe('confirmed')
    expect(result.current.candidates.find((c) => c.id === 'c2')?.status).toBe('needs_review')
  })

  it('reject updates status to rejected', async () => {
    const get = jest.fn(async () => ({
      document_id: 'doc-1',
      total: 1,
      items: [{ id: 'c1', status: 'needs_review', fields: {} }],
    }))
    const post = jest.fn(async () => ({ id: 'c1', status: 'rejected' }))
    const client = fakeClient({ get, post })
    const { result } = await renderHook(() => useDocumentReview(client, 'doc-1'))
    await waitFor(() => expect(result.current.phase).toBe('ready'))
    await act(async () => {
      await result.current.reject('c1')
    })
    expect(post).toHaveBeenCalledWith('/candidates/c1/reject')
    expect(result.current.candidates[0]!.status).toBe('rejected')
  })
})

describe('useAddDocument', () => {
  it('runs session → upload → finalize and returns the document id', async () => {
    const post = jest.fn(async (path: string) => {
      if (path === '/documents/upload-session')
        return { upload_id: 'doc-9', signed_put_url: '/api/v1/documents/blob/tok', method: 'PUT' }
      if (path === '/documents/doc-9/finalize') return { id: 'doc-9', status: 'needs_review' }
      return {}
    })
    const client = fakeClient({ post })
    // fetchImpl: first call reads the local file → blob; second is the PUT.
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce({ ok: true, blob: async () => 'BYTES' })
      .mockResolvedValueOnce({ ok: true, status: 204 }) as unknown as typeof fetch

    const { result } = await renderHook(() => useAddDocument(client, fetchImpl))
    let docId: string | null = null
    await act(async () => {
      docId = await result.current.submit(
        { uri: 'file:///x.jpg', mimeType: 'image/jpeg' },
        'prescription'
      )
    })
    expect(docId).toBe('doc-9')
    expect(result.current.phase).toBe('idle')
    expect(post).toHaveBeenCalledWith('/documents/upload-session', {
      declared_mime: 'image/jpeg',
      doc_type_hint: 'prescription',
      declared_sha256: undefined,
      declared_size: undefined,
    })
  })

  it('sets error phase and returns null when upload fails', async () => {
    const post = jest.fn(async () => ({
      upload_id: 'doc-9',
      signed_put_url: '/api/v1/documents/blob/tok',
      method: 'PUT',
    }))
    const client = fakeClient({ post })
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce({ ok: true, blob: async () => 'B' })
      .mockResolvedValueOnce({ ok: false, status: 500 }) as unknown as typeof fetch

    const { result } = await renderHook(() => useAddDocument(client, fetchImpl))
    let docId: string | null = 'x'
    await act(async () => {
      docId = await result.current.submit(
        { uri: 'file:///x.jpg', mimeType: 'image/jpeg' },
        'prescription'
      )
    })
    expect(docId).toBeNull()
    expect(result.current.phase).toBe('error')
  })
})
