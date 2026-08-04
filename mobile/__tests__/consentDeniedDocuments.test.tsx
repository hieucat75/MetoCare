/**
 * PRIV-F1 follow-up regression. The backend now refuses the whole medical-document
 * pipeline with `403 {code: "CONSENT_DENIED", message: ...}` when the patient has
 * not granted the `documents` consent category. Before this fix the mobile app
 * (a) dropped the envelope's `message` and showed a bare "Lỗi 403", and (b) offered
 * no route to the toggle that governs the feature — so Journey A dead-ended for
 * every pilot patient who never opened the privacy screen.
 */
import React from 'react'
import { act, fireEvent, render, renderHook, waitFor } from '@testing-library/react-native'

// eslint-disable-next-line no-var
var mockRouterPush: jest.Mock
// eslint-disable-next-line no-var
var mockScreenPost: jest.Mock

jest.mock('expo-router', () => {
  mockRouterPush = jest.fn()
  return { router: { push: mockRouterPush, replace: jest.fn(), back: jest.fn() } }
})

jest.mock('../src/auth/AuthContext', () => {
  mockScreenPost = jest.fn()
  // One stable client identity — a fresh object per render would change the
  // hooks' useCallback deps on every render.
  const client = {
    get: jest.fn(),
    post: mockScreenPost,
    patch: jest.fn(),
    put: jest.fn(),
    del: jest.fn(),
    apiFetch: jest.fn(),
    tokens: {},
  }
  return { useAuth: () => ({ client }) }
})

jest.mock('expo-image-picker', () => ({
  requestCameraPermissionsAsync: jest.fn(async () => ({ granted: true })),
  launchCameraAsync: jest.fn(async () => ({
    canceled: false,
    assets: [{ uri: 'file://scan.jpg', mimeType: 'image/jpeg' }],
  })),
  launchImageLibraryAsync: jest.fn(async () => ({ canceled: true, assets: [] })),
}))

import AddDocumentScreen from '../app/(app)/add-document'
import type { ApiClient } from '../src/api/client'
import { ApiError, createApiClient, isConsentDenied } from '../src/api/client'
import { useAddDocument } from '../src/features/documents/useAddDocument'
import { useDocumentReview } from '../src/features/documents/useDocumentReview'
import { vi } from '../src/i18n/vi'

const CONSENT_MESSAGE = "Bạn cần bật quyền 'Tài liệu y tế' trong phần Quyền riêng tư."

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

function fakeClient(overrides: Partial<Record<keyof ApiClient, unknown>> = {}): ApiClient {
  return {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    put: jest.fn(),
    del: jest.fn(),
    apiFetch: jest.fn(),
    tokens: {} as ApiClient['tokens'],
    ...overrides,
  } as ApiClient
}

const consentDeniedError = () => new ApiError(403, CONSENT_MESSAGE, 'CONSENT_DENIED')

describe('ApiClient error envelope', () => {
  it('surfaces the {code, message} envelope instead of a bare status fallback', async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse(403, { code: 'CONSENT_DENIED', message: CONSENT_MESSAGE })
    )
    const client = createApiClient({
      baseUrl: 'https://api.test/api/v1',
      tokens: {
        getAccess: async () => 'token',
        getRefresh: async () => 'refresh',
        setTokens: async () => undefined,
        clear: async () => undefined,
      } as unknown as ApiClient['tokens'],
      fetchImpl,
    })

    await expect(client.get('/documents')).rejects.toMatchObject({
      status: 403,
      code: 'CONSENT_DENIED',
      detail: CONSENT_MESSAGE,
    })
  })

  it('isConsentDenied matches only the consent code', () => {
    expect(isConsentDenied(consentDeniedError())).toBe(true)
    expect(isConsentDenied(new ApiError(403, 'nope', 'PERMISSION_DENIED'))).toBe(false)
    expect(isConsentDenied(new ApiError(500, 'boom'))).toBe(false)
    expect(isConsentDenied(new Error('offline'))).toBe(false)
  })
})

describe('useAddDocument consent gate', () => {
  it('flags consentDenied when the upload session is refused', async () => {
    const post = jest.fn(async () => {
      throw consentDeniedError()
    })
    const client = fakeClient({ post })
    const { result } = await renderHook(() => useAddDocument(client))

    await act(async () => {
      await result.current.submit({ uri: 'file://x.jpg', mimeType: 'image/jpeg' }, 'prescription')
    })

    expect(result.current.phase).toBe('error')
    expect(result.current.consentDenied).toBe(true)
    expect(result.current.errorMsg).toBe(CONSENT_MESSAGE)
  })

  it('does not flag consentDenied for ordinary failures', async () => {
    const post = jest.fn(async () => {
      throw new ApiError(500, 'server error')
    })
    const client = fakeClient({ post })
    const { result } = await renderHook(() => useAddDocument(client))

    await act(async () => {
      await result.current.submit({ uri: 'file://x.jpg', mimeType: 'image/jpeg' }, 'prescription')
    })

    expect(result.current.consentDenied).toBe(false)
    expect(result.current.errorMsg).toBe('server error')
  })
})

describe('useDocumentReview consent gate', () => {
  it('flags consentDenied when candidate listing is refused', async () => {
    const get = jest.fn(async () => {
      throw consentDeniedError()
    })
    // Stable identity: the hook's reload effect depends on `client`.
    const client = fakeClient({ get })
    const { result } = await renderHook(() => useDocumentReview(client, 'doc-1'))

    await waitFor(() => expect(result.current.phase).toBe('error'))
    expect(result.current.consentDenied).toBe(true)
  })
})

describe('AddDocumentScreen consent CTA', () => {
  beforeEach(() => {
    mockRouterPush.mockClear()
    mockScreenPost.mockReset().mockRejectedValue(consentDeniedError())
  })

  it('shows the consent card (not a dead-end error) and routes to the privacy screen', async () => {
    const view = await render(<AddDocumentScreen />)

    await act(async () => {
      fireEvent.press(view.getByTestId('add-take-photo'))
    })

    const card = await view.findByTestId('add-consent-blocked')
    expect(card).toBeTruthy()
    expect(view.getByText(vi.documents.consentBlockedTitle)).toBeTruthy()
    // The generic error text must NOT be the only thing the patient sees.
    expect(view.queryByTestId('add-error')).toBeNull()

    fireEvent.press(view.getByTestId('add-consent-cta'))
    expect(mockRouterPush).toHaveBeenCalledWith('/consent')
  })
})
