import React from 'react'
import { renderHook, act, waitFor } from '@testing-library/react-native'
import { AuthProvider, useAuth } from '../src/auth/AuthContext'
import { NotPatientError } from '../src/api/auth'
import { tokenStore } from '../src/storage/tokenStore'
import type { TokenResponse, UserResponse, UserRole } from '../src/api/types'

/**
 * Regression for the patient-only role gate (independent-review P1): a
 * non-patient account must NOT be admitted to this patient app — the session
 * issued during login is revoked and the context stays unauthenticated.
 */

function jsonRes(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

function tokensFor(role: UserRole, userId: string): TokenResponse {
  return { access_token: 'a', refresh_token: 'r', token_type: 'bearer', role, user_id: userId, mfa: false }
}

function profileFor(role: UserRole, userId: string): UserResponse {
  return {
    id: userId,
    email: `${userId}@metocare.me`,
    phone: null,
    role,
    full_name: 'Người Dùng',
    mfa_enabled: false,
    notify_medication: true,
    notify_lab_results: true,
    notify_doctor_messages: true,
  }
}

const wrapper = ({ children }: { children: React.ReactNode }) => <AuthProvider>{children}</AuthProvider>

describe('patient-only role gate', () => {
  beforeEach(async () => {
    await tokenStore.clear()
  })

  it('rejects a non-patient login: revokes the session and stays unauthenticated', async () => {
    const fetchMock = jest.fn(async (url: string) => {
      if (url.endsWith('/auth/login')) return jsonRes(200, tokensFor('doctor', 'd1'))
      if (url.endsWith('/auth/me')) return jsonRes(200, profileFor('doctor', 'd1'))
      if (url.endsWith('/auth/logout')) return jsonRes(204, null)
      return jsonRes(404, {})
    })
    global.fetch = fetchMock as unknown as typeof fetch

    const { result } = await renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('unauthenticated'))

    let caught: unknown
    await act(async () => {
      try {
        await result.current.login('d1@metocare.me', 'secret6')
      } catch (err) {
        caught = err
      }
    })

    expect(caught).toBeInstanceOf(NotPatientError)
    expect(result.current.status).toBe('unauthenticated')
    expect(result.current.user).toBeNull()
    // The just-issued session was revoked server-side + locally.
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith('/auth/logout'))).toBe(true)
    await expect(tokenStore.getAccess()).resolves.toBeNull()
    await expect(tokenStore.getRefresh()).resolves.toBeNull()
  })

  it('admits a patient login through to authenticated', async () => {
    const fetchMock = jest.fn(async (url: string) => {
      if (url.endsWith('/auth/login')) return jsonRes(200, tokensFor('patient', 'u1'))
      if (url.endsWith('/auth/me')) return jsonRes(200, profileFor('patient', 'u1'))
      return jsonRes(404, {})
    })
    global.fetch = fetchMock as unknown as typeof fetch

    const { result } = await renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('unauthenticated'))

    await act(async () => {
      await result.current.login('u1@metocare.me', 'secret6')
    })

    expect(result.current.status).toBe('authenticated')
    expect(result.current.user?.role).toBe('patient')
    // No logout was issued on the happy path.
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith('/auth/logout'))).toBe(false)
  })
})
