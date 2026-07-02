'use client'

import * as React from 'react'
import {
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  me,
  type UserResponse,
  type TokenResponse,
  type AuthIdentifier,
  type ConsentPayload,
} from '@/lib/api/auth'
import { clearTokens, getAccessToken, getRefreshToken } from '@/lib/api/client'

interface AuthContextValue {
  user: UserResponse | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (identifier: AuthIdentifier, password: string, totpCode?: string) => Promise<TokenResponse>
  register: (
    identifier: AuthIdentifier,
    password: string,
    fullName?: string,
    consent?: ConsentPayload,
  ) => Promise<TokenResponse>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = React.createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<UserResponse | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)

  const refresh = React.useCallback(async () => {
    const token = getAccessToken()
    if (!token) {
      setUser(null)
      return
    }
    try {
      const u = await me()
      setUser(u)
    } catch {
      clearTokens()
      setUser(null)
    }
  }, [])

  React.useEffect(() => {
    refresh().finally(() => setIsLoading(false))
  }, [refresh])

  const login = React.useCallback(
    async (identifier: AuthIdentifier, password: string, totpCode?: string) => {
      const res = await apiLogin(identifier, password, totpCode)
      await refresh()
      return res
    },
    [refresh],
  )

  const register = React.useCallback(
    async (
      identifier: AuthIdentifier,
      password: string,
      fullName?: string,
      consent?: ConsentPayload,
    ) => {
      const res = await apiRegister(identifier, password, fullName, consent)
      await refresh()
      return res
    },
    [refresh],
  )

  const logout = React.useCallback(async () => {
    const refreshToken = getRefreshToken()
    if (refreshToken) {
      try {
        await apiLogout(refreshToken)
      } catch {
        clearTokens()
      }
    } else {
      clearTokens()
    }
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
