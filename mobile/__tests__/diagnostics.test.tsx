/**
 * WS4-F1 / WS4-F2 — operator retrieval path.
 *
 * The ring buffer is only useful if a pilot operator can get the (already
 * redacted) content off the device. This screen is that path.
 */
import React from 'react'
import { Share } from 'react-native'
import { render, fireEvent, waitFor } from '@testing-library/react-native'

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), replace: jest.fn(), back: jest.fn() },
}))

import DiagnosticsScreen from '../app/(app)/diagnostics'
import { _resetForTest, captureException, recordRequest } from '../src/lib/monitor'

describe('DiagnosticsScreen', () => {
  beforeEach(() => {
    _resetForTest()
    jest.restoreAllMocks()
  })

  it('shows an empty state when nothing has been captured', async () => {
    const view = await render(<DiagnosticsScreen />)
    expect(view.getByTestId('diagnostics-empty')).toBeTruthy()
  })

  it('lists buffered crash reports and recent requests', async () => {
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = false
    captureException(new Error('render exploded'))
    recordRequest({ requestId: 'rid-xyz', method: 'GET', path: '/documents', status: 500 })

    const view = await render(<DiagnosticsScreen />)

    expect(view.getByTestId('diagnostics-report-0')).toBeTruthy()
    expect(view.getByText(/render exploded/)).toBeTruthy()
    expect(view.getByText(/rid-xyz/)).toBeTruthy()
    expect(view.getByText(/\/documents/)).toBeTruthy()
  })

  it('never renders unredacted PHI or credentials', async () => {
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = false
    captureException(new Error('failed for user@example.com phone 0912345678'))

    const view = await render(<DiagnosticsScreen />)

    expect(view.queryByText(/user@example\.com/)).toBeNull()
    expect(view.queryByText(/0912345678/)).toBeNull()
    expect(view.getByText(/\[email\]/)).toBeTruthy()
  })

  it('exports the redacted diagnostics text through the share sheet', async () => {
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = false
    recordRequest({ requestId: 'rid-share', method: 'POST', path: '/documents', status: 422 })
    const shareSpy = jest.spyOn(Share, 'share').mockResolvedValue({ action: 'sharedAction' })

    const view = await render(<DiagnosticsScreen />)
    await fireEvent.press(view.getByTestId('diagnostics-share'))

    await waitFor(() => expect(shareSpy).toHaveBeenCalledTimes(1))
    const message = shareSpy.mock.calls[0]?.[0] as { message?: string }
    expect(message.message).toContain('rid-share')
  })

  it('clears the buffers on request', async () => {
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = false
    captureException(new Error('clear me'))

    const view = await render(<DiagnosticsScreen />)
    expect(view.getByTestId('diagnostics-report-0')).toBeTruthy()

    await fireEvent.press(view.getByTestId('diagnostics-clear'))

    expect(view.getByTestId('diagnostics-empty')).toBeTruthy()
  })
})
