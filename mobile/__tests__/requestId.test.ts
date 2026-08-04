/**
 * WS4-F2 — client↔server correlation.
 *
 * The backend reads and echoes `X-Request-ID`
 * (backend/app/core/middleware.py:18,66,107). The mobile client must send it
 * and retain a PHI-free trail so a pilot bug report can cite an id that joins
 * to a backend access-log line (12-PILOT-OPERATIONS-RUNBOOK.md:35).
 */
import { createApiClient } from '../src/api/client'
import { createTokenStore } from '../src/storage/tokenStore'
import { _resetForTest, getRequestLog } from '../src/lib/monitor'
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

function jsonRes(status: number, body: unknown, requestId?: string): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) =>
        name.toLowerCase() === 'x-request-id' ? (requestId ?? null) : null,
    },
    json: async () => body,
  } as unknown as Response
}

const BASE = 'http://api.test/api/v1'

function headersOf(call: [string, RequestInit?] | undefined): Record<string, string> {
  return (call?.[1]?.headers ?? {}) as Record<string, string>
}

beforeEach(() => _resetForTest())

describe('X-Request-ID correlation', () => {
  it('sends a unique X-Request-ID header on every outgoing request', async () => {
    const tokens = createTokenStore(memSecure())
    const fetchImpl = jest
      .fn<Promise<Response>, [string, RequestInit?]>()
      .mockResolvedValue(jsonRes(200, { ok: true }))

    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })
    await client.get('/patients/me')
    await client.get('/patients/me')

    const first = headersOf(fetchImpl.mock.calls[0])['X-Request-ID']
    const second = headersOf(fetchImpl.mock.calls[1])['X-Request-ID']
    expect(first).toBeTruthy()
    expect(second).toBeTruthy()
    expect(first).not.toBe(second)
  })

  it('records the request id, method, path and status for a successful call', async () => {
    const tokens = createTokenStore(memSecure())
    const fetchImpl = jest
      .fn<Promise<Response>, [string, RequestInit?]>()
      .mockResolvedValue(jsonRes(200, { ok: true }))

    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })
    await client.get('/patients/me')

    const log = getRequestLog()
    expect(log).toHaveLength(1)
    expect(log[0]?.method).toBe('GET')
    expect(log[0]?.path).toBe('/patients/me')
    expect(log[0]?.status).toBe(200)
    expect(log[0]?.requestId).toBe(headersOf(fetchImpl.mock.calls[0])['X-Request-ID'])
  })

  it('prefers the request id the backend echoes back', async () => {
    const tokens = createTokenStore(memSecure())
    const fetchImpl = jest
      .fn<Promise<Response>, [string, RequestInit?]>()
      .mockResolvedValue(jsonRes(200, { ok: true }, 'server-side-rid'))

    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })
    await client.get('/patients/me')

    expect(getRequestLog()[0]?.requestId).toBe('server-side-rid')
  })

  it('records failed requests so an error report can cite the id', async () => {
    const tokens = createTokenStore(memSecure())
    const fetchImpl = jest
      .fn<Promise<Response>, [string, RequestInit?]>()
      .mockResolvedValue(jsonRes(500, { detail: 'nổ' }))

    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })
    await expect(client.get('/documents')).rejects.toThrow()

    const log = getRequestLog()
    expect(log).toHaveLength(1)
    expect(log[0]?.status).toBe(500)
    expect(log[0]?.path).toBe('/documents')
  })

  it('records transport failures with status 0', async () => {
    const tokens = createTokenStore(memSecure())
    const fetchImpl = jest
      .fn<Promise<Response>, [string, RequestInit?]>()
      .mockRejectedValue(new Error('network down'))

    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })
    await expect(client.get('/documents')).rejects.toThrow()

    expect(getRequestLog()[0]?.status).toBe(0)
  })

  it('never records the request body, auth header, or query PHI', async () => {
    const tokens = createTokenStore(memSecure())
    await tokens.setTokens('access-secret', 'refresh-secret')
    const fetchImpl = jest
      .fn<Promise<Response>, [string, RequestInit?]>()
      .mockResolvedValue(jsonRes(200, { ok: true }))

    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })
    await client.post('/lab-results?patient_email=user@example.com', {
      glucose: 9.1,
      note: 'bệnh nhân Nguyễn Văn A, 0912345678',
    })

    const serialized = JSON.stringify(getRequestLog())
    expect(serialized).not.toContain('Nguyễn')
    expect(serialized).not.toContain('0912345678')
    expect(serialized).not.toContain('glucose')
    expect(serialized).not.toContain('access-secret')
    expect(serialized).not.toContain('user@example.com')
    expect(getRequestLog()[0]?.path).toBe('/lab-results')
    expect(getRequestLog()[0]?.method).toBe('POST')
  })

  it('keeps the 401 → refresh → retry flow intact and logs each attempt', async () => {
    const tokens = createTokenStore(memSecure())
    await tokens.setTokens('old-access', 'refresh-1')

    const fetchImpl = jest
      .fn<Promise<Response>, [string, RequestInit?]>()
      .mockResolvedValueOnce(jsonRes(401, { detail: 'expired' }))
      .mockResolvedValueOnce(
        jsonRes(200, { access_token: 'new-access', refresh_token: 'refresh-2' })
      )
      .mockResolvedValueOnce(jsonRes(200, { value: 42 }))

    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })
    await expect(client.get<{ value: number }>('/protected')).resolves.toEqual({ value: 42 })

    const log = getRequestLog()
    // The original 401 attempt and the successful retry are both correlatable.
    expect(log.map((e) => e.status)).toEqual(expect.arrayContaining([401, 200]))
    expect(log.every((e) => e.requestId.length > 0)).toBe(true)
  })
})
