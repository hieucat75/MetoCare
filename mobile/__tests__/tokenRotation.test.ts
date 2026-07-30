import { createApiClient } from '../src/api/client'
import { createTokenStore } from '../src/storage/tokenStore'
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
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const BASE = 'http://api.test/api/v1'

describe('token rotation (transparent refresh)', () => {
  it('refreshes on 401 then retries the original request', async () => {
    const tokens = createTokenStore(memSecure())
    await tokens.setTokens('old-access', 'refresh-1')

    const fetchImpl = jest
      .fn<Promise<Response>, [string, RequestInit?]>()
      // 1) original call → 401
      .mockResolvedValueOnce(jsonRes(401, { detail: 'expired' }))
      // 2) refresh → new pair
      .mockResolvedValueOnce(
        jsonRes(200, { access_token: 'new-access', refresh_token: 'refresh-2' })
      )
      // 3) retry → success
      .mockResolvedValueOnce(jsonRes(200, { value: 42 }))

    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })
    const data = await client.get<{ value: number }>('/protected')

    expect(data).toEqual({ value: 42 })
    // Retry carried the rotated access token.
    const retryCall = fetchImpl.mock.calls[2]!
    expect((retryCall[1]?.headers as Record<string, string>).Authorization).toBe('Bearer new-access')
    await expect(tokens.getAccess()).resolves.toBe('new-access')
    await expect(tokens.getRefresh()).resolves.toBe('refresh-2')
  })

  it('forces logout + clears tokens when refresh fails (reuse/expired family)', async () => {
    const tokens = createTokenStore(memSecure())
    await tokens.setTokens('old-access', 'refresh-1')
    const onForcedLogout = jest.fn()

    const fetchImpl = jest
      .fn<Promise<Response>, [string, RequestInit?]>()
      .mockResolvedValueOnce(jsonRes(401, { detail: 'expired' }))
      .mockResolvedValueOnce(jsonRes(401, { detail: 'refresh reuse' }))

    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl, onForcedLogout })

    await expect(client.get('/protected')).rejects.toMatchObject({ status: 401 })
    expect(onForcedLogout).toHaveBeenCalledTimes(1)
    await expect(tokens.getAccess()).resolves.toBeNull()
    await expect(tokens.getRefresh()).resolves.toBeNull()
  })

  it('single-flights concurrent 401s into ONE refresh call', async () => {
    const tokens = createTokenStore(memSecure())
    await tokens.setTokens('old-access', 'refresh-1')

    let refreshCalls = 0
    const fetchImpl = jest.fn(async (url: string) => {
      if (url.endsWith('/auth/refresh')) {
        refreshCalls += 1
        return jsonRes(200, { access_token: 'new-access', refresh_token: 'refresh-2' })
      }
      // Protected endpoints: 401 while token is old, 200 once rotated.
      const access = await tokens.getAccess()
      if (access === 'old-access') return jsonRes(401, { detail: 'expired' })
      return jsonRes(200, { ok: true })
    }) as unknown as typeof fetch

    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })
    const [a, b] = await Promise.all([client.get('/a'), client.get('/b')])

    expect(a).toEqual({ ok: true })
    expect(b).toEqual({ ok: true })
    expect(refreshCalls).toBe(1)
  })

  it('does not attempt refresh when skipAuth is set', async () => {
    const tokens = createTokenStore(memSecure())
    const fetchImpl = jest
      .fn<Promise<Response>, [string, RequestInit?]>()
      .mockResolvedValueOnce(jsonRes(401, { detail: 'nope' }))
    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })

    await expect(client.post('/auth/login', { email: 'x' }, { skipAuth: true })).rejects.toMatchObject(
      { status: 401 }
    )
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })
})
