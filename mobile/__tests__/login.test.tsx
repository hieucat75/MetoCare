import React from 'react'
import { render, fireEvent, waitFor } from '@testing-library/react-native'

// eslint-disable-next-line no-var
var mockLogin: jest.Mock
// eslint-disable-next-line no-var
var mockReplace: jest.Mock

jest.mock('expo-router', () => {
  const React = require('react')
  const { Text } = require('react-native')
  mockReplace = jest.fn()
  return {
    Link: ({ children }: { children: React.ReactNode }) =>
      React.createElement(Text, null, children),
    router: { replace: mockReplace },
  }
})

jest.mock('../src/auth/AuthContext', () => {
  mockLogin = jest.fn(async () => undefined)
  return {
    useAuth: () => ({
      login: mockLogin,
      hasStoredSession: jest.fn(async () => false),
      restoreSession: jest.fn(async () => false),
    }),
  }
})

import LoginScreen from '../app/(auth)/login'
import { vi } from '../src/i18n/vi'

describe('LoginScreen', () => {
  beforeEach(() => {
    mockLogin.mockClear().mockResolvedValue(undefined)
    mockReplace.mockClear()
  })

  it('renders Vietnamese title and CTA', async () => {
    const view = await render(<LoginScreen />)
    expect(view.getByText(vi.auth.loginTitle)).toBeTruthy()
    expect(view.getByTestId('login-submit')).toBeTruthy()
  })

  it('shows validation errors and does not call login when fields are empty', async () => {
    const view = await render(<LoginScreen />)
    await fireEvent.press(view.getByTestId('login-submit'))
    await waitFor(() => {
      expect(view.getByText(vi.errors.emailRequired)).toBeTruthy()
      expect(view.getByText(vi.errors.passwordRequired)).toBeTruthy()
    })
    expect(mockLogin).not.toHaveBeenCalled()
  })

  it('rejects a malformed email', async () => {
    const view = await render(<LoginScreen />)
    await fireEvent.changeText(view.getByTestId('login-email'), 'not-an-email')
    await fireEvent.changeText(view.getByTestId('login-password'), 'secret6')
    await fireEvent.press(view.getByTestId('login-submit'))
    await waitFor(() => {
      expect(view.getByText(vi.errors.emailInvalid)).toBeTruthy()
    })
    expect(mockLogin).not.toHaveBeenCalled()
  })

  it('submits valid credentials and navigates to dashboard', async () => {
    const view = await render(<LoginScreen />)
    await fireEvent.changeText(view.getByTestId('login-email'), 'p@metocare.me')
    await fireEvent.changeText(view.getByTestId('login-password'), 'secret6')
    await fireEvent.press(view.getByTestId('login-submit'))
    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('p@metocare.me', 'secret6')
    })
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('renders an error banner when login fails', async () => {
    const { ApiError } = require('../src/api/client')
    mockLogin.mockRejectedValueOnce(new ApiError(401, 'bad'))
    const view = await render(<LoginScreen />)
    await fireEvent.changeText(view.getByTestId('login-email'), 'p@metocare.me')
    await fireEvent.changeText(view.getByTestId('login-password'), 'secret6')
    await fireEvent.press(view.getByTestId('login-submit'))
    await waitFor(() => {
      expect(view.getByTestId('login-error')).toHaveTextContent(vi.errors.invalidCredentials)
    })
  })
})
