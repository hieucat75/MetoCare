import { createApiClient } from '../src/api/client'
import { createTokenStore } from '../src/storage/tokenStore'
import { login, register, logout, me } from '../src/api/auth'
import type { SecureStorageAdapter } from '../src/storage/secureStore'
import type { TokenResponse, UserResponse } from '../src/api/types'

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

const TOKENS: TokenResponse = {
  access_token: 'access-1',
  refresh_token: 'refresh-1',
  token_type: 'bearer',
  role: 'patient',
  user_id: 'u1',
  mfa: false,
}

const PROFILE: UserResponse = {
  id: 'u1',
  email: 'p@metocare.me',
  phone: null,
  role: 'patient',
  full_name: 'Người Dùng',
  mfa_enabled: false,
  notify_medication: true,
  notify_lab_results: true,
  notify_doctor_messages: true,
}

describe('auth contract: login → store → refresh → logout', () => {
  it('login stores rotated tokens and sends email/password only (no phone/OTP)', async () => {
    const tokens = createTokenStore(memSecure())
    const fetchImpl = jest.fn(async () => jsonRes(200, TOKENS)) as unknown as typeof fetch
    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })

    const res = await login(client, { email: 'p@metocare.me', password: 'secret6' })

    expect(res.role).toBe('patient')
    await expect(tokens.getAccess()).resolves.toBe('access-1')
    await expect(tokens.getRefresh()).resolves.toBe('refresh-1')

    const call = (fetchImpl as jest.Mock).mock.calls[0]!
    expect(call[0]).toBe(`${BASE}/auth/login`)
    const sentBody = JSON.parse(call[1].body as string)
    expect(sentBody).toEqual({ email: 'p@metocare.me', password: 'secret6' })
    expect(sentBody).not.toHaveProperty('phone')
    expect(sentBody).not.toHaveProperty('totp_code')
  })

  it('register posts consent-less email/password and stores tokens', async () => {
    const tokens = createTokenStore(memSecure())
    const fetchImpl = jest.fn(async () => jsonRes(201, TOKENS)) as unknown as typeof fetch
    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })

    await register(client, { email: 'p@metocare.me', password: 'secret6' }, 'Người Dùng')

    const call = (fetchImpl as jest.Mock).mock.calls[0]!
    expect(call[0]).toBe(`${BASE}/auth/register`)
    const body = JSON.parse(call[1].body as string)
    expect(body.email).toBe('p@metocare.me')
    expect(body.full_name).toBe('Người Dùng')
    await expect(tokens.getAccess()).resolves.toBe('access-1')
  })

  it('authenticated me() sends the Bearer access token', async () => {
    const tokens = createTokenStore(memSecure())
    await tokens.setTokens('access-1', 'refresh-1')
    const fetchImpl = jest.fn(async () => jsonRes(200, PROFILE)) as unknown as typeof fetch
    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })

    const profile = await me(client)
    expect(profile.id).toBe('u1')
    const call = (fetchImpl as jest.Mock).mock.calls[0]!
    expect(call[1].headers.Authorization).toBe('Bearer access-1')
  })

  it('logout posts the refresh token then clears storage', async () => {
    const tokens = createTokenStore(memSecure())
    await tokens.setTokens('access-1', 'refresh-1')
    const fetchImpl = jest.fn(async () => jsonRes(204, null)) as unknown as typeof fetch
    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })

    await logout(client)

    const call = (fetchImpl as jest.Mock).mock.calls[0]!
    expect(call[0]).toBe(`${BASE}/auth/logout`)
    expect(JSON.parse(call[1].body as string)).toEqual({ refresh_token: 'refresh-1' })
    await expect(tokens.getAccess()).resolves.toBeNull()
    await expect(tokens.getRefresh()).resolves.toBeNull()
  })

  it('clears tokens even if the logout request fails', async () => {
    const tokens = createTokenStore(memSecure())
    await tokens.setTokens('access-1', 'refresh-1')
    const fetchImpl = jest.fn(async () => {
      throw new Error('network down')
    }) as unknown as typeof fetch
    const client = createApiClient({ baseUrl: BASE, tokens, fetchImpl })

    await expect(logout(client)).resolves.toBeUndefined()
    await expect(tokens.getRefresh()).resolves.toBeNull()
  })
})
