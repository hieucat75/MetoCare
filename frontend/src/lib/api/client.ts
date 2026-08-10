const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    /**
     * The backend's machine-readable error code when it sends one
     * (`PASSWORD_POLICY`, `VALIDATION_ERROR`, ...).
     *
     * Without it a caller can only branch on the HTTP status, and 422 means
     * "something in this request was rejected" — not "the phone was wrong".
     * On 2026-08-10 a real user registered with a valid number and a password
     * shorter than the production policy; both auth pages read that 422 as an
     * invalid phone and told them so, which is a false statement about input
     * they had entered correctly.
     */
    public readonly code?: string
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

/**
 * Maps a caught fetch error to page-level error props (ErrorState's `code` +
 * `message`). `ApiError` carries a real HTTP status; anything else (a plain
 * `TypeError` from a network-level `fetch()` failure) gets the standard
 * "can't reach the server" copy rather than a generic fallback.
 */
export function toPageError(err: unknown): PageError {
  if (err instanceof ApiError) {
    return { code: err.status, message: err.detail }
  }
  return {
    title: 'Không thể kết nối máy chủ',
    message: 'Vui lòng kiểm tra mạng và thử lại.',
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
    let code: string | undefined
    try {
      const body = await res.json()
      if (body?.code === 'VALIDATION_ERROR' || body?.code === 'DUPLICATE_CANDIDATE') {
        // Structured error: serialize full body so callers can render field-level
        // detail (VALIDATION_ERROR) or the dedup candidate (DUPLICATE_CANDIDATE,
        // M06 create-patient 409 — app/api/v1/routes/clinic_patients.py).
        detail = JSON.stringify(body)
      } else if (typeof body.detail === 'string') {
        detail = body.detail
      } else if (Array.isArray(body.detail)) {
        detail = body.detail.map((e: { msg?: string }) => e.msg).join('; ')
      } else if (typeof body.message === 'string') {
        // Several handlers answer with `message` rather than `detail` — the
        // password-policy one among them (main.py). Dropping it left the caller
        // with a bare "Lỗi 422" and no way to tell WHICH field the backend
        // rejected, which is how a short password came to be reported as an
        // invalid phone number.
        detail = body.message
      }
      code = typeof body.code === 'string' ? body.code : undefined
    } catch {}
    throw new ApiError(res.status, detail, code)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

/**
 * Multipart upload. Unlike {@link apiFetch} this does NOT set a JSON
 * Content-Type — the browser sets `multipart/form-data` with the correct
 * boundary itself. Auth header is attached; a single 401 retry-after-refresh is
 * performed (matching apiFetch) before redirecting to /login.
 */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getAccessToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  let res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: form })

  if (res.status === 401) {
    const refreshed = await tryRefreshTokens()
    if (refreshed) {
      const newToken = getAccessToken()
      if (newToken) headers['Authorization'] = `Bearer ${newToken}`
      res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: form })
    }
    if (!refreshed || res.status === 401) {
      clearTokens()
      if (typeof window !== 'undefined') window.location.href = '/login'
      throw new ApiError(401, 'Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.')
    }
  }

  if (!res.ok) {
    let detail = `Lỗi ${res.status}`
    let code: string | undefined
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail))
        detail = body.detail.map((e: { msg?: string }) => e.msg).join('; ')
      else if (typeof body.message === 'string') detail = body.message
      code = typeof body.code === 'string' ? body.code : undefined
    } catch {}
    throw new ApiError(res.status, detail, code)
  }
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string, opts?: FetchOptions) => apiFetch<T>(path, { method: 'GET', ...opts }),

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

  del: <T>(path: string, opts?: FetchOptions) => apiFetch<T>(path, { method: 'DELETE', ...opts }),
}
