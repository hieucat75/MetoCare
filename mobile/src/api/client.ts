import { API_BASE_URL } from '../config/env'
import { tokenStore as defaultTokenStore, type TokenStore } from '../storage/tokenStore'

/**
 * Typed fetch client mirroring the web contract
 * (frontend/src/lib/api/client.ts), adapted for React Native:
 *
 *  - tokens come from injectable async SecureStore-backed TokenStore
 *    (no synchronous localStorage),
 *  - forced logout is a callback (no window.location),
 *  - single-flight refresh prevents concurrent 401s from each rotating the
 *    refresh token and tripping the backend's reuse-detection (which revokes
 *    the whole token family),
 *  - one retry-after-refresh, then clear + forced logout on continued 401.
 *
 * Everything is injectable (tokens, fetch, callbacks) so the rotation flow is
 * unit-testable with a mocked fetch.
 */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

export interface PageError {
  code?: number
  title?: string
  message?: string
}

/** Map a caught error to page-level error props (Vietnamese copy). */
export function toPageError(err: unknown): PageError {
  if (err instanceof ApiError) {
    return { code: err.status, message: err.detail }
  }
  return {
    title: 'Không thể kết nối máy chủ',
    message: 'Vui lòng kiểm tra mạng và thử lại.',
  }
}

export type FetchOptions = Omit<RequestInit, 'headers'> & {
  headers?: Record<string, string>
  skipAuth?: boolean
}

/**
 * Narrowed fetch signature — the client only ever calls fetch with a string
 * URL, so tests can supply a simple `(url, init) => Promise<Response>` mock.
 * The global `fetch` (wider input) is assignable to this.
 */
export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>

export interface ApiClientConfig {
  baseUrl?: string
  tokens?: TokenStore
  fetchImpl?: FetchLike
  /**
   * Invoked when refresh fails / reuse is detected. May fire more than once if
   * several requests are in flight at the moment of failure, so the handler
   * must be idempotent (the AuthContext handler only sets state — safe).
   */
  onForcedLogout?: () => void
}

export interface ApiClient {
  apiFetch<T>(path: string, options?: FetchOptions): Promise<T>
  get<T>(path: string, opts?: FetchOptions): Promise<T>
  post<T>(path: string, body?: unknown, opts?: FetchOptions): Promise<T>
  patch<T>(path: string, body?: unknown, opts?: FetchOptions): Promise<T>
  put<T>(path: string, body?: unknown, opts?: FetchOptions): Promise<T>
  del<T>(path: string, opts?: FetchOptions): Promise<T>
  tokens: TokenStore
}

export function createApiClient(config: ApiClientConfig = {}): ApiClient {
  const baseUrl = config.baseUrl ?? API_BASE_URL
  const tokens = config.tokens ?? defaultTokenStore
  const doFetch = config.fetchImpl ?? fetch
  const onForcedLogout = config.onForcedLogout

  // Single in-flight refresh shared across concurrent 401s.
  let refreshingPromise: Promise<boolean> | null = null

  async function doRefresh(): Promise<boolean> {
    const refresh = await tokens.getRefresh()
    if (!refresh) return false
    try {
      const res = await doFetch(`${baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      })
      if (!res.ok) {
        await tokens.clear()
        return false
      }
      const data = (await res.json()) as {
        access_token: string
        refresh_token: string
      }
      await tokens.setTokens(data.access_token, data.refresh_token)
      return true
    } catch {
      await tokens.clear()
      return false
    }
  }

  async function tryRefresh(): Promise<boolean> {
    if (refreshingPromise) return refreshingPromise
    refreshingPromise = doRefresh().finally(() => {
      refreshingPromise = null
    })
    return refreshingPromise
  }

  async function parseErrorDetail(res: Response): Promise<string> {
    let detail = `Lỗi ${res.status}`
    try {
      const body = await res.json()
      if (body?.code === 'VALIDATION_ERROR' || body?.code === 'DUPLICATE_CANDIDATE') {
        detail = JSON.stringify(body)
      } else if (typeof body?.detail === 'string') {
        detail = body.detail
      } else if (Array.isArray(body?.detail)) {
        detail = body.detail.map((e: { msg?: string }) => e.msg).join('; ')
      }
    } catch {
      // Non-JSON body — keep the status-code fallback.
    }
    return detail
  }

  async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
    const { skipAuth = false, headers: extraHeaders = {}, ...rest } = options
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...extraHeaders,
    }

    if (!skipAuth) {
      const token = await tokens.getAccess()
      if (token) headers['Authorization'] = `Bearer ${token}`
    }

    let res = await doFetch(`${baseUrl}${path}`, { headers, ...rest })

    if (res.status === 401 && !skipAuth) {
      const refreshed = await tryRefresh()
      if (refreshed) {
        const newToken = await tokens.getAccess()
        if (newToken) headers['Authorization'] = `Bearer ${newToken}`
        res = await doFetch(`${baseUrl}${path}`, { headers, ...rest })
      }
      if (!refreshed || res.status === 401) {
        await tokens.clear()
        onForcedLogout?.()
        throw new ApiError(401, 'Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.')
      }
    }

    if (!res.ok) {
      throw new ApiError(res.status, await parseErrorDetail(res))
    }

    if (res.status === 204) return undefined as T
    return res.json() as Promise<T>
  }

  return {
    apiFetch,
    tokens,
    get: <T>(path: string, opts?: FetchOptions) =>
      apiFetch<T>(path, { method: 'GET', ...opts }),
    post: <T>(path: string, body?: unknown, opts?: FetchOptions) =>
      apiFetch<T>(path, {
        method: 'POST',
        body: body != null ? JSON.stringify(body) : undefined,
        ...opts,
      }),
    patch: <T>(path: string, body?: unknown, opts?: FetchOptions) =>
      apiFetch<T>(path, {
        method: 'PATCH',
        body: body != null ? JSON.stringify(body) : undefined,
        ...opts,
      }),
    put: <T>(path: string, body?: unknown, opts?: FetchOptions) =>
      apiFetch<T>(path, {
        method: 'PUT',
        body: body != null ? JSON.stringify(body) : undefined,
        ...opts,
      }),
    del: <T>(path: string, opts?: FetchOptions) =>
      apiFetch<T>(path, { method: 'DELETE', ...opts }),
  }
}
