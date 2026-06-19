const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('meto_access')
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('meto_refresh')
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem('meto_access', access)
  localStorage.setItem('meto_refresh', refresh)
}

export function clearTokens(): void {
  localStorage.removeItem('meto_access')
  localStorage.removeItem('meto_refresh')
}

// Singleton in-flight refresh promise.
// Prevents multiple concurrent 401s from each triggering a refresh and
// triggering the backend's single-use reuse-detection, which would revoke
// the entire token family and log the user out.
let _refreshingPromise: Promise<boolean> | null = null

async function _doRefreshTokens(): Promise<boolean> {
  const refresh = getRefreshToken()
  if (!refresh) return false
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    })
    if (!res.ok) {
      clearTokens()
      return false
    }
    const data = await res.json()
    setTokens(data.access_token, data.refresh_token)
    return true
  } catch {
    clearTokens()
    return false
  }
}

async function tryRefreshTokens(): Promise<boolean> {
  if (_refreshingPromise) return _refreshingPromise
  _refreshingPromise = _doRefreshTokens().finally(() => {
    _refreshingPromise = null
  })
  return _refreshingPromise
}

type FetchOptions = Omit<RequestInit, 'headers'> & {
  headers?: Record<string, string>
  skipAuth?: boolean
}

export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { skipAuth = false, headers: extraHeaders = {}, ...rest } = options
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...extraHeaders,
  }

  if (!skipAuth) {
    const token = getAccessToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  let res = await fetch(`${API_BASE}${path}`, { headers, ...rest })

  if (res.status === 401 && !skipAuth) {
    const refreshed = await tryRefreshTokens()
    if (refreshed) {
      const newToken = getAccessToken()
      if (newToken) headers['Authorization'] = `Bearer ${newToken}`
      res = await fetch(`${API_BASE}${path}`, { headers, ...rest })
    }
    if (!refreshed || res.status === 401) {
      clearTokens()
      if (typeof window !== 'undefined') {
        window.location.href = '/login'
      }
      throw new ApiError(401, 'Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.')
    }
  }

  if (!res.ok) {
    let detail = `Lỗi ${res.status}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((e: { msg?: string }) => e.msg).join('; ')
    } catch {}
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
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
