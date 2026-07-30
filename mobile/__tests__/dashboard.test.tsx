import React from 'react'
import { render, fireEvent, waitFor } from '@testing-library/react-native'

// eslint-disable-next-line no-var
var mockRefreshUser: jest.Mock
// eslint-disable-next-line no-var
var mockLogout: jest.Mock

jest.mock('../src/auth/AuthContext', () => {
  mockRefreshUser = jest.fn(async () => undefined)
  mockLogout = jest.fn(async () => undefined)
  return {
    useAuth: () => ({
      user: { full_name: 'Người Dùng', role: 'patient' },
      refreshUser: mockRefreshUser,
      logout: mockLogout,
    }),
  }
})

import DashboardScreen from '../app/(app)/dashboard'
import { vi } from '../src/i18n/vi'

describe('DashboardScreen', () => {
  beforeEach(() => {
    mockRefreshUser.mockReset().mockResolvedValue(undefined)
    mockLogout.mockClear()
  })

  it('shows the ready dashboard with a greeting after loading', async () => {
    const view = await render(<DashboardScreen />)
    await waitFor(() => {
      expect(view.getByText(/Người Dùng/)).toBeTruthy()
    })
    expect(view.getByTestId('dashboard-empty')).toBeTruthy()
    expect(view.getByText(vi.dashboard.emptyTitle)).toBeTruthy()
  })

  it('renders an error view with retry when the load fails, then recovers', async () => {
    mockRefreshUser.mockRejectedValueOnce(new Error('boom'))
    const view = await render(<DashboardScreen />)

    await waitFor(() => {
      expect(view.getByTestId('error-view')).toBeTruthy()
    })

    await fireEvent.press(view.getByTestId('retry-button'))
    await waitFor(() => {
      expect(view.getByTestId('dashboard-empty')).toBeTruthy()
    })
    expect(mockRefreshUser).toHaveBeenCalledTimes(2)
  })

  it('calls logout when the logout button is pressed', async () => {
    const view = await render(<DashboardScreen />)
    await waitFor(() => {
      expect(view.getByTestId('dashboard-logout')).toBeTruthy()
    })
    await fireEvent.press(view.getByTestId('dashboard-logout'))
    expect(mockLogout).toHaveBeenCalled()
  })
})
