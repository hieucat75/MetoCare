import { createApiClient } from '../src/api/client'
import { createTokenStore } from '../src/storage/tokenStore'
import { buildDoctorQuery, getDoctor, listDoctors } from '../src/api/marketplace'
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

describe('marketplace API contract', () => {
  it('buildDoctorQuery omits empty filters and encodes provided ones in order', () => {
    expect(buildDoctorQuery()).toBe('')
    expect(buildDoctorQuery({})).toBe('')
    expect(buildDoctorQuery({ specialty: 'Nội tiết' })).toBe(
      `?specialty=${encodeURIComponent('Nội tiết')}`
    )
    expect(
      buildDoctorQuery({ specialty: 'Tim mạch', name: 'An', min_price: 100000, max_price: 500000, method: 'chat' })
    ).toBe(
      `?specialty=${encodeURIComponent('Tim mạch')}&name=An&min_price=100000&max_price=500000&method=chat`
    )
  })

  it('listDoctors builds the correct query string, path, and GET method', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, [{ id: 'doc-1', full_name: 'BS. An', rating_avg: 0, rating_count: 0 }])
    }) as unknown as typeof fetch
    const client = createApiClient({ baseUrl: BASE, tokens: createTokenStore(memSecure()), fetchImpl })

    const rows = await listDoctors(client, { specialty: 'Nội tiết', name: 'An', method: 'chat' })

    expect(rows[0]!.id).toBe('doc-1')
    expect(calls[0]!.url).toBe(
      `http://api.test/api/v1/marketplace/doctors?specialty=${encodeURIComponent('Nội tiết')}&name=An&method=chat`
    )
    expect(calls[0]!.init?.method).toBe('GET')
  })

  it('listDoctors with no filters hits the bare doctors path', async () => {
    const calls: Array<{ url: string }> = []
    const fetchImpl = jest.fn(async (url: string) => {
      calls.push({ url })
      return jsonRes(200, [])
    }) as unknown as typeof fetch
    const client = createApiClient({ baseUrl: BASE, tokens: createTokenStore(memSecure()), fetchImpl })

    await listDoctors(client)
    expect(calls[0]!.url).toBe('http://api.test/api/v1/marketplace/doctors')
  })

  it('getDoctor requests the detail path by id', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, { id: 'doc-9', full_name: 'BS. Bình', rating_avg: 4.5, rating_count: 3 })
    }) as unknown as typeof fetch
    const client = createApiClient({ baseUrl: BASE, tokens: createTokenStore(memSecure()), fetchImpl })

    const doctor = await getDoctor(client, 'doc-9')
    expect(doctor.id).toBe('doc-9')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/marketplace/doctors/doc-9')
    expect(calls[0]!.init?.method).toBe('GET')
  })
})
