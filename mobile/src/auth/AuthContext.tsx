import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { createApiClient, ApiError, type ApiClient } from '../api/client'
import {
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  me as apiMe,
  isPatientRole,
  NotPatientError,
} from '../api/auth'
import type { UserResponse } from '../api/types'
import { getOrCreateInstallId, unlinkInstallId } from '../storage/installId'

/**
 * Session-probe retry: a valid stored session must survive a transient
 * transport error at launch (offline/DNS blip). A real auth failure surfaces as
 * an ApiError (401 already cleared tokens) and is NOT retried.
 */
const SESSION_PROBE_ATTEMPTS = 3
const SESSION_PROBE_BACKOFF_MS = 500
const delay = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Central auth state + session lifecycle.
 *
 * - Boots by ensuring an install UUID exists (ADR-03) and probing stored
 *   tokens (`/auth/me`) to restore a session.
 * - Owns a single ApiClient whose `onForcedLogout` flips the context to
 *   unauthenticated when refresh/reuse fails — the transparent-refresh
 *   forced-logout path from the web contract.
 * - Exposes email/password login/register/logout only (ADR-02).
 */

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

interface AuthContextValue {
  status: AuthStatus
  user: UserResponse | null
  installId: string | null
  client: ApiClient
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName?: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  /** True if a refresh token is persisted (a returning user to biometric-unlock). */
  hasStoredSession: () => Promise<boolean>
  /** Re-validate stored tokens and, if valid, mark the session authenticated. */
  restoreSession: () => Promise<boolean>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<UserResponse | null>(null)
  const [installId, setInstallId] = useState<string | null>(null)

  // useState setters are guaranteed stable across renders, so the client (and
  // its forced-logout callback) can be created once and still flip the latest
  // state when refresh/reuse fails.
  const client = useMemo(
    () =>
      createApiClient({
        onForcedLogout: () => {
          setUser(null)
          setStatus('unauthenticated')
        },
      }),
    []
  )

  const bootstrap = useCallback(async () => {
    try {
      const id = await getOrCreateInstallId()
      setInstallId(id)
    } catch {
      // Install-id provisioning is non-fatal for session probing — continue.
    }

    const access = await client.tokens.getAccess().catch(() => null)
    if (!access) {
      setStatus('unauthenticated')
      return
    }

    // Verify the stored session. A real auth failure surfaces as an ApiError
    // (the client already cleared tokens on 401) → land on login. A transport
    // error must NOT discard a still-valid session, so retry a few times before
    // giving up rather than bouncing a healthy user to the login form.
    for (let attempt = 0; attempt < SESSION_PROBE_ATTEMPTS; attempt++) {
      try {
        const profile = await apiMe(client)
        if (!isPatientRole(profile.role)) {
          await apiLogout(client)
          setUser(null)
          setStatus('unauthenticated')
          return
        }
        setUser(profile)
        setStatus('authenticated')
        return
      } catch (err) {
        if (err instanceof ApiError) {
          setUser(null)
          setStatus('unauthenticated')
          return
        }
        if (attempt < SESSION_PROBE_ATTEMPTS - 1) {
          await delay(SESSION_PROBE_BACKOFF_MS * (attempt + 1))
        }
      }
    }

    // Sustained transport failure: tokens remain in SecureStore for the next
    // launch, but we cannot verify now — show login instead of hanging.
    setUser(null)
    setStatus('unauthenticated')
  }, [client])

  useEffect(() => {
    // Run-once async session restore on mount; setState lands after awaits,
    // not synchronously — the canonical init-effect pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void bootstrap()
  }, [bootstrap])

  // Reject a non-patient account on this patient-only app: revoke the session
  // that was just issued, drop to unauthenticated, and signal the screen.
  const enforcePatient = useCallback(
    async (profile: UserResponse): Promise<void> => {
      if (isPatientRole(profile.role)) return
      await apiLogout(client)
      setUser(null)
      setStatus('unauthenticated')
      throw new NotPatientError()
    },
    [client]
  )

  const login = useCallback(
    async (email: string, password: string) => {
      await apiLogin(client, { email, password })
      const profile = await apiMe(client)
      await enforcePatient(profile)
      setUser(profile)
      setStatus('authenticated')
    },
    [client, enforcePatient]
  )

  const register = useCallback(
    async (email: string, password: string, fullName?: string) => {
      await apiRegister(client, { email, password }, fullName)
      const profile = await apiMe(client)
      await enforcePatient(profile)
      setUser(profile)
      setStatus('authenticated')
    },
    [client, enforcePatient]
  )

  const logout = useCallback(async () => {
    await apiLogout(client)
    // Account unlink → mint a fresh install identity next boot (ADR-03).
    await unlinkInstallId()
    setUser(null)
    setStatus('unauthenticated')
  }, [client])

  const refreshUser = useCallback(async () => {
    const profile = await apiMe(client)
    setUser(profile)
  }, [client])

  const hasStoredSession = useCallback(async () => {
    return (await client.tokens.getRefresh()) != null
  }, [client])

  const restoreSession = useCallback(async () => {
    try {
      const access = await client.tokens.getAccess()
      const refresh = await client.tokens.getRefresh()
      if (!access && !refresh) return false
      const profile = await apiMe(client)
      await enforcePatient(profile)
      setUser(profile)
      setStatus('authenticated')
      return true
    } catch {
      setUser(null)
      setStatus('unauthenticated')
      return false
    }
  }, [client, enforcePatient])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      installId,
      client,
      login,
      register,
      logout,
      refreshUser,
      hasStoredSession,
      restoreSession,
    }),
    [
      status,
      user,
      installId,
      client,
      login,
      register,
      logout,
      refreshUser,
      hasStoredSession,
      restoreSession,
    ]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
