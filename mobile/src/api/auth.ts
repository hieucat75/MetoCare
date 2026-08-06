import type { ApiClient } from './client'
import type { TokenResponse, UserResponse, ConsentPayload, UserRole } from './types'

/**
 * Auth endpoints — email/password ONLY (ADR-02; OTP/phone DEFERRED for
 * Journey 1). Each call takes the ApiClient so token storage + rotation are
 * shared with the rest of the app and the flow stays unit-testable.
 */

export interface EmailCredentials {
  email: string
  password: string
}

export async function login(
  client: ApiClient,
  creds: EmailCredentials
): Promise<TokenResponse> {
  const res = await client.post<TokenResponse>(
    '/auth/login',
    { email: creds.email, password: creds.password },
    { skipAuth: true }
  )
  await client.tokens.setTokens(res.access_token, res.refresh_token)
  return res
}

export async function register(
  client: ApiClient,
  creds: EmailCredentials,
  fullName?: string,
  consent?: ConsentPayload
): Promise<TokenResponse> {
  const res = await client.post<TokenResponse>(
    '/auth/register',
    {
      email: creds.email,
      password: creds.password,
      full_name: fullName,
      ...(consent ? { consent } : {}),
    },
    { skipAuth: true }
  )
  await client.tokens.setTokens(res.access_token, res.refresh_token)
  return res
}

export async function logout(client: ApiClient): Promise<void> {
  const refresh = await client.tokens.getRefresh()
  try {
    if (refresh) {
      await client.post('/auth/logout', { refresh_token: refresh }, { skipAuth: true })
    }
  } catch {
    // Best-effort server revoke — never block local sign-out on a network error.
  } finally {
    await client.tokens.clear()
  }
}

export async function me(client: ApiClient): Promise<UserResponse> {
  return client.get<UserResponse>('/auth/me')
}

/** Only patients use this mobile app; other roles are redirected out. */
export function isPatientRole(role: UserRole): boolean {
  return role === 'patient'
}

/**
 * Thrown by AuthContext when a non-patient account authenticates on this
 * patient-only app. Screens map it to `vi.errors.patientsOnly`. The caller has
 * already revoked the just-issued session before this is thrown.
 */
export class NotPatientError extends Error {
  constructor() {
    super('This application is for patients only.')
    this.name = 'NotPatientError'
  }
}
