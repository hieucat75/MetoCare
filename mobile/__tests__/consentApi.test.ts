import { createApiClient } from '../src/api/client'
import { createTokenStore } from '../src/storage/tokenStore'
import { listConsent, updateConsent } from '../src/api/consent'
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

function clientWith(fetchImpl: typeof fetch) {
  return createApiClient({ baseUrl: BASE, tokens: createTokenStore(memSecure()), fetchImpl })
}

describe('consent API contract', () => {
  it('listConsent GETs the /meto/consent path and returns the categories', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, [
        {
          context_type: 'ai_processing',
          granted: true,
          granted_at: '2026-07-31T00:00:00Z',
          policy_version: 'v1',
          purpose: 'Cho phép Meto xử lý dữ liệu của bạn.',
        },
      ])
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const rows = await listConsent(client)

    expect(calls[0]!.url).toBe('http://api.test/api/v1/meto/consent')
    expect(calls[0]!.init?.method).toBe('GET')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.context_type).toBe('ai_processing')
    expect(rows[0]!.granted).toBe(true)
    expect(rows[0]!.purpose).toBe('Cho phép Meto xử lý dữ liệu của bạn.')
  })

  it('updateConsent POSTs context_type + granted to /meto/consent', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, { status: 'ok', context_type: 'medications', action: 'granted' })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const out = await updateConsent(client, 'medications', true)

    expect(out.action).toBe('granted')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/meto/consent')
    expect(calls[0]!.init?.method).toBe('POST')
    const sent = JSON.parse(String(calls[0]!.init?.body))
    expect(sent.context_type).toBe('medications')
    expect(sent.granted).toBe(true)
  })

  it('updateConsent sends granted:false when revoking', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, { status: 'ok', context_type: 'documents', action: 'revoked' })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    await updateConsent(client, 'documents', false)

    const sent = JSON.parse(String(calls[0]!.init?.body))
    expect(sent.context_type).toBe('documents')
    expect(sent.granted).toBe(false)
  })
})
