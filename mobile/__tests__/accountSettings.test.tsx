/**
 * WS11-F5 regression. `0da0f06` shipped the backend GDPR endpoints
 * (`GET /patients/{id}/export`, `DELETE /patients/{id}/account`) but touched
 * zero mobile files, so a patient could not initiate deletion from inside the
 * app — a hard Google Play policy gate and Apple Guideline 5.1.1(v) blocker.
 *
 * These tests pin: the endpoints the screen calls, and that deletion is
 * irreversible-by-confirmation (a single tap can never delete the account).
 */
import React from 'react'
import { act, fireEvent, render, renderHook, waitFor } from '@testing-library/react-native'

// eslint-disable-next-line no-var
var mockGet: jest.Mock
// eslint-disable-next-line no-var
var mockDel: jest.Mock
// eslint-disable-next-line no-var
var mockLogout: jest.Mock
// eslint-disable-next-line no-var
var mockReplace: jest.Mock

jest.mock('expo-router', () => {
  mockReplace = jest.fn()
  return { router: { push: jest.fn(), replace: mockReplace, back: jest.fn() } }
})

jest.mock('../src/auth/AuthContext', () => {
  mockGet = jest.fn()
  mockDel = jest.fn()
  mockLogout = jest.fn(async () => undefined)
  // Stable identities — a fresh object per render changes hook deps.
  const client = {
    get: mockGet,
    post: jest.fn(),
    patch: jest.fn(),
    put: jest.fn(),
    del: mockDel,
    apiFetch: jest.fn(),
    tokens: {},
  }
  const user = { id: 'u1', email: 'a@b.vn', role: 'patient', patient_profile_id: 'p-1' }
  return { useAuth: () => ({ client, user, logout: mockLogout }) }
})

import SettingsScreen from '../app/(app)/settings'
import type { ApiClient } from '../src/api/client'
import { useAccountActions } from '../src/features/account/useAccountActions'
import { vi } from '../src/i18n/vi'

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

beforeEach(() => {
  mockGet.mockReset()
  mockDel.mockReset()
  mockLogout.mockClear()
  mockReplace.mockClear()
})

describe('useAccountActions', () => {
  it('exports the caller’s own data from the patient-scoped export endpoint', async () => {
    const get = jest.fn(async () => ({
      generated_at: '2026-08-04T00:00:00Z',
      patient_id: 'p-1',
      profile: { email: 'a@b.vn' },
      health_metrics: [{ id: 'm1' }, { id: 'm2' }],
      lab_results: [],
      medications: [{ id: 'x' }],
      documents: [],
    }))
    // Stable identity across renders.
    const client = fakeClient({ get })
    const { result } = await renderHook(() => useAccountActions(client, 'p-1'))

    await act(async () => {
      await result.current.exportData()
    })

    expect(get).toHaveBeenCalledWith('/patients/p-1/export')
    expect(result.current.exportSummary).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'health_metrics', count: 2 }),
        expect.objectContaining({ key: 'medications', count: 1 }),
      ])
    )
  })

  it('deletes the account through the patient-scoped delete endpoint', async () => {
    const del = jest.fn(async () => ({ status: 'deleted', patient_id: 'p-1' }))
    const client = fakeClient({ del })
    const { result } = await renderHook(() => useAccountActions(client, 'p-1'))

    let ok = false
    await act(async () => {
      ok = await result.current.deleteAccount()
    })

    expect(ok).toBe(true)
    expect(del).toHaveBeenCalledWith('/patients/p-1/account')
  })

  it('surfaces a failure instead of pretending the account was deleted', async () => {
    const del = jest.fn(async () => {
      throw new Error('boom')
    })
    const client = fakeClient({ del })
    const { result } = await renderHook(() => useAccountActions(client, 'p-1'))

    let ok = true
    await act(async () => {
      ok = await result.current.deleteAccount()
    })

    expect(ok).toBe(false)
    expect(result.current.errorMsg).toBeTruthy()
  })
})

describe('SettingsScreen account deletion (WS11-F5)', () => {
  it('never deletes on a single tap — an explicit typed confirmation is required', async () => {
    const view = await render(<SettingsScreen />)

    await act(async () => {
      fireEvent.press(view.getByTestId('settings-delete-account'))
    })
    expect(mockDel).not.toHaveBeenCalled()
    // The irreversible-action warning must be visible before confirming.
    expect(view.getByText(vi.account.deleteWarning)).toBeTruthy()

    // Confirming without typing the word does nothing.
    await act(async () => {
      fireEvent.press(view.getByTestId('settings-delete-confirm'))
    })
    expect(mockDel).not.toHaveBeenCalled()
    expect(view.getByTestId('settings-delete-error')).toHaveTextContent(
      vi.account.deleteConfirmMismatch
    )
  })

  it('deletes, clears the session and returns to login once confirmed', async () => {
    mockDel.mockResolvedValue({ status: 'deleted', patient_id: 'p-1' })
    const view = await render(<SettingsScreen />)

    await act(async () => {
      fireEvent.press(view.getByTestId('settings-delete-account'))
    })
    await act(async () => {
      fireEvent.changeText(view.getByTestId('settings-delete-input'), vi.account.deleteConfirmWord)
    })
    await act(async () => {
      fireEvent.press(view.getByTestId('settings-delete-confirm'))
    })

    expect(mockDel).toHaveBeenCalledWith('/patients/p-1/account')
    await waitFor(() => expect(mockLogout).toHaveBeenCalled())
    expect(mockReplace).toHaveBeenCalledWith('/login')
  })

  it('exports data on request', async () => {
    mockGet.mockResolvedValue({
      generated_at: '2026-08-04T00:00:00Z',
      patient_id: 'p-1',
      profile: {},
      health_metrics: [{ id: 'm1' }],
    })
    const view = await render(<SettingsScreen />)

    await act(async () => {
      fireEvent.press(view.getByTestId('settings-export'))
    })

    expect(mockGet).toHaveBeenCalledWith('/patients/p-1/export')
    expect(await view.findByTestId('settings-export-summary')).toBeTruthy()
  })
})
