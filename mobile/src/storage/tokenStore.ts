import { secureStorage, type SecureStorageAdapter } from './secureStore'

/**
 * Access/refresh token persistence in secure storage.
 *
 * Storage keys mirror the web client (`meto_access` / `meto_refresh`) so the
 * two clients speak the same contract. The store is dependency-injectable
 * (default = real SecureStore adapter) to keep rotation logic unit-testable.
 */

export const ACCESS_TOKEN_KEY = 'meto_access'
export const REFRESH_TOKEN_KEY = 'meto_refresh'

export interface TokenPair {
  access: string
  refresh: string
}

export interface TokenStore {
  getAccess(): Promise<string | null>
  getRefresh(): Promise<string | null>
  setTokens(access: string, refresh: string): Promise<void>
  clear(): Promise<void>
}

export function createTokenStore(
  storage: SecureStorageAdapter = secureStorage
): TokenStore {
  return {
    getAccess: () => storage.getItem(ACCESS_TOKEN_KEY),
    getRefresh: () => storage.getItem(REFRESH_TOKEN_KEY),
    async setTokens(access: string, refresh: string): Promise<void> {
      await Promise.all([
        storage.setItem(ACCESS_TOKEN_KEY, access),
        storage.setItem(REFRESH_TOKEN_KEY, refresh),
      ])
    },
    async clear(): Promise<void> {
      await Promise.all([
        storage.removeItem(ACCESS_TOKEN_KEY),
        storage.removeItem(REFRESH_TOKEN_KEY),
      ])
    },
  }
}

export const tokenStore = createTokenStore()
